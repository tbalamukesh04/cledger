import logging
import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
import os
from typing import List, Dict

from sqlalchemy.orm import joinedload, Session 
from sqlalchemy.exc import IntegrityError, OperationalError, DBAPIError
import redis.exceptions

from app.schemas.jobs import WebhookJobPayload
from app.schemas.preprocessing import PreprocessedPayload, ProcessingContext
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
from app.parsing.scoring_engine import TransactionScorer
from app.schemas.parsing_metadata import ParsingMetadata
from app.ai.llm_extraction.extraction_service import process_extraction_batch
from app.ai.batch_response_parser import parse_batch_response

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
        
        candidates_for_ai = []
        valid_jobs_map = {}
        scorer = TransactionScorer()
        scoring_context_map = {}

        # 2. Preprocess, Score, and Filter duplicates locally
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
            
            preprocessed_payload = PreprocessedPayload(
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
            
            # --- SCORING ENGINE INTEGRATION ---
            context = ProcessingContext(payload=preprocessed_payload)
            context = scorer.evaluate(context)

            parsing_meta_obj = ParsingMetadata(
                score=context.scoring.total_score,
                threshold=scorer.threshold,
                is_transaction=context.scoring.is_transaction_candidate,
                rule_breakdown=context.scoring.rule_breakdown
            )

            raw_msg.is_transaction = context.scoring.is_transaction_candidate
            raw_msg.parsing_meta = parsing_meta_obj.to_jsonb()

            logger.info(
                "Message classification metadata generated",
                extra={
                    "event_type": "classification_metadata_staged",
                    "raw_message_id": job.raw_message_id,
                    "score": context.scoring.total_score,
                    "threshold": scorer.threshold,
                    "is_transaction": context.scoring.is_transaction_candidate,
                    "db_update_status": "pending_commit"
                }
            )

            # --- ROUTING DECISION ---
            if context.scoring.is_transaction_candidate:
                # Passes threshold: Route to AI Extraction Batch
                candidates_for_ai.append(preprocessed_payload)
                valid_jobs_map[raw_msg.id] = job
            else:
                # Fails threshold: Bypass AI, mark as complete non-transaction
                raw_msg.processed = True
                raw_msg.processing_status = "NON_TRANSACTION"
                raw_msg.processing_started_at = processing_started_at
                raw_msg.processing_completed_at = datetime.now(timezone.utc)
                job_results[job.job_id] = "success"

        # If no messages passed the scoring threshold, commit and exit early
        if not candidates_for_ai:
            db.commit()
            return job_results

        # 3. AI EXTRACTION (Batch Call - Only for candidates)
        batch_id = str(uuid.uuid4())
        candidate_ids = [str(c.raw_message_id) for c in candidates_for_ai]
        
        logger.info(json.dumps({
            "event_type": "batch_extraction_started",
            "batch_id": batch_id,
            "batch_size": len(candidates_for_ai),
            "message_ids": candidate_ids
        }))

        extraction_start_time = time.time()
        gemini_response_status = "success"
        extracted_data_map = {}

        try:
            # Execute Batch LLM Request using the new function
            raw_llm_response = process_extraction_batch(candidates_for_ai)
            extraction_latency = round(time.time() - extraction_start_time, 3)
            
            # Parse Batch Response mapping strictly by ID
            extracted_data_map = parse_batch_response(raw_llm_response, candidate_ids)
            
        except Exception as e:
            extraction_latency = round(time.time() - extraction_start_time, 3)
            gemini_response_status = f"failed: {str(e)}"
            logger.error(f"Batch {batch_id} AI extraction failed completely: {e}")

        # STRUCTURED LOGGING FOR EXTRACTION LATENCY
        logger.info(json.dumps({
            "event_type": "batch_extraction_completed",
            "batch_id": batch_id,
            "batch_size": len(candidates_for_ai),
            "message_ids": candidate_ids,
            "extraction_latency_seconds": extraction_latency,
            "gemini_response_status": gemini_response_status
        }))

        # 4. Process Results and Stage DB Updates mapped securely by ID
        for preprocessed_data in candidates_for_ai:
            raw_msg = raw_msg_map[preprocessed_data.raw_message_id]
            job = valid_jobs_map[preprocessed_data.raw_message_id]
            
            # Safely fetch result via string ID
            extraction_result = extracted_data_map.get(str(preprocessed_data.raw_message_id))

            validated_amount = None
            normalized_currency = "ZMW"
            confidence_score = 0.0
            raw_extracted_date = None
            raw_extracted_verb = None

            if extraction_result:
                validated_amount = validate_and_convert_amount(extraction_result.amount)
                normalized_currency = normalize_currency_code(extraction_result.currency)
                confidence_score = extraction_result.confidence
                raw_extracted_date = getattr(extraction_result, "transaction_date", getattr(extraction_result, "date", None))
                raw_extracted_verb = extraction_result.transaction_verb
                
            normalized_txn_verb = normalize_transaction_verb(raw_extracted_verb)
            extraction_status = "SUCCESS" if (validated_amount is not None and normalized_txn_verb is not None) else ("NON_TRANSACTION" if extraction_result else "AI_EXTRACTION_FAILED")
            normalized_txn_date = normalize_extracted_date(raw_extracted_date, preprocessed_data.normalized_timestamp)
            current_meta = raw_msg.parsing_meta or {}
            
            current_meta["ai_extraction"] = {
                "source": "gemini-2.5-flash",
                "batch_processed": True,
                "batch_id": batch_id,
                "status": extraction_status,
                "raw_ai_output": extraction_result.model_dump() if extraction_result else None
            }

            raw_msg.parsing_meta = current_meta

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
                    parsing_meta=current_meta
                )
                db.add(new_transaction)
                raw_msg.is_transaction = True

            processing_outcome = "success" if extraction_status in ["SUCCESS", "NON_TRANSACTION"] else "success_with_fallback"
            
            raw_msg.processed = True
            raw_msg.processing_status = processing_outcome
            raw_msg.processing_started_at = processing_started_at
            raw_msg.processing_completed_at = datetime.now(timezone.utc)
            
            job_results[job.job_id] = "success" if extraction_status != "AI_EXTRACTION_FAILED" else "dlq"

        # 5. Commit whole batch
        try:
            db.commit()
            logger.info(json.dumps({
                "event_type": "batch_processing_completed",
                "batch_size_sent_to_ai": len(candidates_for_ai),
                "total_jobs_processed": len(jobs),
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