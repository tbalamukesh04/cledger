import logging
import hashlib
import json
from datetime import datetime, timezone
import os

from sqlalchemy.orm import joinedload
from sqlalchemy.exc import IntegrityError, OperationalError, DBAPIError
import redis.exceptions

from app.schemas.jobs import WebhookJobPayload
from app.schemas.preprocessing import PreprocessedPayload
from app.database.database import SessionLocal
from app.models.raw_messages import RawMessages
from app.models.groups import Groups
from app.models.participants import Participants
from app.utils.text_processing import normalize_whatsapp_text
from app.utils.datetime_utils import convert_epoch_to_utc_datetime
from app.utils.hashing import generate_content_hash
from app.ai.ai_parser import AIParser
from app.models.transactions import Transactions
from app.utils.date_normalization import normalize_extracted_date
from app.utils.financial_validation import validate_and_convert_amount, normalize_currency_code, normalize_transaction_verb
from app.ai.batch_request_builder import build_batch_request_payload
from app.parsing.scoring_engine import ScoringEngine
from typing import List, Dict

logger = logging.getLogger(__name__)

WORKER_IDENTIFIER = os.getenv("WORKER_IDENTIFIER", f"worker-{os.getpid()}")

RETRYABLE_EXCEPTIONS = (
    OperationalError,
    DBAPIError,
    redis.exceptions.ConnectionError,
    redis.exceptions.TimeoutError,
    ConnectionError,
    TimeoutError
)

def _extract_message_text(raw_json: dict) -> str|None:
    try:
        entries = raw_json.get("entry", [])
        if not entries:
            return None

        changes = entries[0].get("changes", [])
        if not changes:
            return None
        
        value = changes[0].get("value", {})
        messages = value.get("messages", [])
        if not messages:
            return None
        
        msg = messages[0]
        msg_type = msg.get("type")
        if msg_type == "text":
            return msg.get("text").get("body")

        return None

    except Exception as e:
        logger.warning(f"Payload traversal failed during text extraction: {e}")
        return None
        
def _extract_message_timestamp(raw_json: dict) -> str | None:
    try:
        entries = raw_json.get("entry", [])
        if not entries: return None
        
        changes = entries[0].get("changes", [])
        if not changes: return None
        
        value = changes[0].get("value", {})
        messages = value.get("messages", [])
        if not messages: return None
        
        msg = messages[0]
        return msg.get("timestamp")
        
    except (IndexError, AttributeError, TypeError) as e:
        logger.warning(f"Payload traversal failed during timestamp extraction: {e}")
        return None

def _parse_epoch_to_int(epoch_str: str | None) -> int | None:
    if not epoch_str:
        return None
    try:
        return int(epoch_str)
    except (ValueError, TypeError) as e:
        logger.warning(f"Failed to parse epoch timestamp '{epoch_str}'")
        return None

def _generate_content_hash(text: str | None, timestamp: datetime) -> str:
    base_string = f"{text or ''}|{timestamp.isoformat()}"
    return hashlib.sha256(base_string.encode('utf-8')).hexdigest()

def process_webhook_batch(jobs: List[WebhookJobPayload]) -> Dict[str, str]:
    """
    Processes a batch of webhook jobs in a single database transaction and a single AI API call.
    Returns a dictionary mapping job_id to the string status: "success", "retry", or "dlq".
    """
    db = SessionLocal()
    processing_started_at = datetime.now(timezone.utc)
    job_results = {job.job_id: "retry" for job in jobs} # Default to retry in case of crash

    try:
        # 1. Fetch all raw messages for the batch efficiently
        raw_msg_ids = [job.raw_message_id for job in jobs]
        raw_messages = db.query(RawMessages).options(
            joinedload(RawMessages.sender),
            joinedload(RawMessages.group)
        ).filter(RawMessages.id.in_(raw_msg_ids)).all()

        raw_msg_map = {msg.id: msg for msg in raw_messages}
        
        preprocessed_batch = []
        valid_jobs_map = {}

        # 2. Preprocess and filter duplicates locally
        for job in jobs:
            raw_msg = raw_msg_map.get(job.raw_message_id)
            if not raw_msg:
                logger.error(f"Job {job.job_id}: RawMessage {job.raw_message_id} not found.")
                job_results[job.job_id] = "dlq"
                continue

            raw_text = _extract_message_text(raw_msg.raw_json)
            normalized_text = normalize_whatsapp_text(raw_text)
            
            raw_epoch_str = _extract_message_timestamp(raw_msg.raw_json)
            parsed_epoch_int = _parse_epoch_to_int(raw_epoch_str)
            normalized_timestamp = convert_epoch_to_utc_datetime(parsed_epoch_int)
            final_timestamp = normalized_timestamp or raw_msg.received_at or job.message_timestamp
            
            content_hash = generate_content_hash(normalized_text, final_timestamp)
            is_native_wamid = raw_msg.message_id and raw_msg.message_id.startswith("wamid.")
            idempotency_key = raw_msg.message_id if is_native_wamid else f"idem_content_{content_hash}"

            if raw_msg.processed:
                logger.warning(f"Job {job.job_id}: Already processed. Skipping.")
                job_results[job.job_id] = "success"
                continue

            # Check DB Hash collision constraint locally
            if raw_msg.hash != idempotency_key:
                raw_msg.hash = idempotency_key # Staged for commit later

            sender_phone = raw_msg.sender.phone if raw_msg.sender else None
            sender_name = raw_msg.sender.displayname if raw_msg.sender else None
            group_whatsapp_id = raw_msg.group.group_id if raw_msg.group else None
            group_name = raw_msg.group.groupname if raw_msg.group else None
            
            preprocessed_data = PreprocessedPayload(
                raw_message_id=raw_msg.id,
                participant_id=raw_msg.sender_id,
                sender_phone=sender_phone,
                sender_name=sender_name,
                group_id=raw_msg.group_id,
                group_whatsapp_id=group_whatsapp_id,
                group_name=group_name,
                normalized_timestamp=final_timestamp, 
                message_id=raw_msg.message_id,
                message_type=job.webhook_event_type,
                normalized_text=normalized_text,
                message_hash=content_hash,
                idempotency_identifier=idempotency_key
            )
            preprocessed_batch.append(preprocessed_data)
            valid_jobs_map[job.raw_message_id] = job

        if not preprocessed_batch:
            db.commit()
            return job_results

        # 3. AI EXTRACTION (Batch Call)
        # 3. AI EXTRACTION (Batch Call)
        parser = AIParser()
        batch_request = build_batch_request_payload(preprocessed_batch)
        extraction_results = parser.parse_batch(batch_request)

        # Instantiate the Scoring Engine
        scoring_engine = ScoringEngine()

        # 4. Process Results and Stage DB Updates
        for idx, preprocessed_data in enumerate(preprocessed_batch):
            raw_msg = raw_msg_map[preprocessed_data.raw_message_id]
            job = valid_jobs_map[preprocessed_data.raw_message_id]
            extraction_result = extraction_results[idx]

            validated_amount = None
            normalized_currency = "ZMW"
            confidence_score = 0.0
            raw_extracted_date = None
            raw_extracted_verb = None

            # --- NEW PIPELINE STAGE: Scoring Engine ---
            is_transaction, total_score, scoring_meta = scoring_engine.evaluate(
                extraction=extraction_result,
                original_text=preprocessed_data.normalized_text or ""
            )

            if extraction_result:
                validated_amount = validate_and_convert_amount(extraction_result.amount)
                normalized_currency = normalize_currency_code(extraction_result.currency)
                confidence_score = extraction_result.confidence
                raw_extracted_date = extraction_result.date
                raw_extracted_verb = extraction_result.transaction_verb
                
            normalized_txn_verb = normalize_transaction_verb(raw_extracted_verb)
            normalized_txn_date = normalize_extracted_date(raw_extracted_date, preprocessed_data.normalized_timestamp)

            # Assign Status based on Scoring Engine Decision
            if not extraction_result:
                extraction_status = "AI_EXTRACTION_FAILED"
            elif is_transaction and validated_amount is not None and normalized_txn_verb is not None:
                extraction_status = "SUCCESS"
            else:
                # Fell below threshold or lacked critical normalized fields
                extraction_status = "NON_TRANSACTION" 

            if extraction_status == "SUCCESS":
                new_transaction = Transactions(
                    tenant_id=raw_msg.tenant_id,
                    raw_message_id=raw_msg.id,
                    amount=validated_amount,  
                    currency=normalized_currency,
                    txn_type=normalized_txn_verb,
                    txn_date=normalized_txn_date,
                    confidence=confidence_score,
                    status="PARSED", 
                    hash=preprocessed_data.message_hash,
                    # --- Inject Scoring Metadata into Database ---
                    parsing_meta={
                        "source": "gemini-2.5-flash", 
                        "batch_processed": True, 
                        "scoring_breakdown": scoring_meta,
                        "raw_ai_output": extraction_result.model_dump() if extraction_result else None
                    }
                )
                db.add(new_transaction)
                raw_msg.is_transaction = True

            processing_outcome = "success" if extraction_status in ["SUCCESS", "NON_TRANSACTION"] else "success_with_fallback"
            
            raw_msg.processed = True
            raw_msg.processing_status = processing_outcome
            raw_msg.processing_started_at = processing_started_at
            raw_msg.processing_completed_at = datetime.now(timezone.utc)
            
            job_results[job.job_id] = "success"

        # 5. Commit whole batch
        try:
            db.commit()
            logger.info(json.dumps({
                "event_type": "batch_processing_completed",
                "batch_size": len(preprocessed_batch),
                "worker_identifier": WORKER_IDENTIFIER
            }))
        except IntegrityError as e:
            db.rollback()
            logger.warning(f"Batch DB commit failed due to integrity error: {e}")
            # Fall back to retrying jobs individually or fail batch
            for job in jobs:
                job_results[job.job_id] = "retry"

        return job_results

    except RETRYABLE_EXCEPTIONS as e:
        db.rollback()
        logger.warning(f"Transient error in batch: {e}")
        return {job.job_id: "retry" for job in jobs}
    except Exception as e:
        db.rollback()
        logger.error(f"Fatal error in batch processing: {e}", exc_info=True)
        return {job.job_id: "dlq" for job in jobs}
    finally:
        db.close()