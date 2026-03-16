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
    """
    Safely navigates the nested Meta webhook payload to extract the exact message timestamp.
    Returns the Unix epoch timestamp as a string, or None if not found.
    """
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

def process_webhook_job(job: WebhookJobPayload) -> bool:
    """
    Core handler for processing webhook jobs dequeued from Redis.
    
    Args:
        job (WebhookJobPayload): The validated job payload.
        
    Returns:
        bool: True if processed successfully, False otherwise.
    """
    db = SessionLocal()

    processing_started_at = datetime.now(timezone.utc)
    processing_outcome = "unknown"
    
    try:
        logger.info(json.dumps({
            "event_type": "job_processing_started", 
            "job_id": job.job_id,
            "raw_message_id": job.raw_message_id,
            "timestamp": processing_started_at.isoformat()
        }))

        raw_msg = db.query(RawMessages).options(
            joinedload(RawMessages.sender),
            joinedload(RawMessages.group)
        ).filter(RawMessages.id == job.raw_message_id).first()
        
        if not raw_msg:
            processing_outcome = "failure"
            processing_completed_at = datetime.now(timezone.utc)
            processing_duration_ms = round((processing_completed_at - processing_started_at).total_seconds() * 1000, 2)
            
            logger.error(json.dumps({
                "event_type": "job_processing_error",
                "extraction_status": "failed",
                "reason": "RawMessage record not found in database",
                "job_id": job.job_id,
                "raw_message_id": job.raw_message_id,
                "processing_outcome": processing_outcome,
                "processing_duration_ms": processing_duration_ms,
                "worker_identifier": WORKER_IDENTIFIER,
                "timestamp": processing_completed_at.isoformat()
            }))
            return False

        raw_text = _extract_message_text(raw_msg.raw_json)
        normalized_text = normalize_whatsapp_text(raw_text)
        
        raw_epoch_str = _extract_message_timestamp(raw_msg.raw_json)
        parsed_epoch_int = _parse_epoch_to_int(raw_epoch_str)
        normalized_timestamp = convert_epoch_to_utc_datetime(parsed_epoch_int)
        final_message_timestamp = normalized_timestamp or raw_msg.received_at or job.message_timestamp
        
        content_hash = generate_content_hash(normalized_text, final_message_timestamp)

        is_native_wamid = raw_msg.message_id and raw_msg.message_id.startswith("wamid.")

        if is_native_wamid:
            idempotency_key = raw_msg.message_id
            idempotency_source = "whatsapp_message_id"

        else:
            idempotency_key = f"idem_content_{content_hash}"
            idempotency_source = "content_hash"

        duplicate_record = None
        
        if raw_msg.processed:
            duplicate_record = raw_msg
        
        else:
            if is_native_wamid:
                duplicate_record = db.query(RawMessages).filter(
                    RawMessages.message_id == idempotency_key,
                    RawMessages.id != raw_msg.id,
                    RawMessages.processed == True
                ).first()

            if not duplicate_record:
                duplicate_record = db.query(RawMessages).filter(
                    RawMessages.hash == idempotency_key,
                    RawMessages.id != raw_msg.id,
                    RawMessages.processed == True
                ).first()

        if duplicate_record:
            processing_outcome = "duplicate_detected"
            processing_completed_at = datetime.now(timezone.utc)
            processing_duration_ms = round((processing_completed_at - processing_started_at).total_seconds() * 1000, 2)
            
            logger.warning(json.dumps({
                "event_type": "duplicate_detected",
                "job_id": job.job_id,
                "raw_message_id": raw_msg.id,
                "whatsapp_message_id": raw_msg.message_id,
                "message_hash": content_hash,
                "duplicate_status": "aborted",
                "duplicate_of_id": duplicate_record.id,
                "idempotency_key": idempotency_key,
                "reason": "already_processed" if raw_msg.processed else "redundant_delivery",
                "processing_outcome": processing_outcome,
                "processing_duration_ms": processing_duration_ms, 
                "worker_identifier": WORKER_IDENTIFIER,            
                "timestamp": processing_completed_at.isoformat(),
                "message": "Duplicate detected. Aborting pipeline safely."
            }))
            return True

        if raw_msg.hash != idempotency_key:
            try:
                raw_msg.hash = idempotency_key
                db.commit()
            except IntegrityError:
                db.rollback()
                processing_outcome = "duplicate_detected"
                processing_completed_at = datetime.now(timezone.utc)
                processing_duration_ms = round((processing_completed_at - processing_started_at).total_seconds() * 1000, 2)
                
                logger.warning(json.dumps({
                    "event_type": "duplicate_detected",
                    "job_id": job.job_id,
                    "raw_message_id": raw_msg.id,
                    "whatsapp_message_id": raw_msg.message_id,
                    "message_hash": content_hash,
                    "duplicate_status": "concurrent_abort",
                    "idempotency_key": idempotency_key,
                    "reason": "concurrent_hash_collision",
                    "processing_outcome": processing_outcome,
                    "processing_duration_ms": processing_duration_ms, # <-- Added duration
                    "worker_identifier": WORKER_IDENTIFIER,           # <-- Added worker ID
                    "timestamp": processing_completed_at.isoformat(),
                    "message": "Race condition caught. Duplicate hash insertion prevented."
                }))
                return True

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
            normalized_timestamp=final_message_timestamp, 
            message_id=raw_msg.message_id,
            message_type=job.webhook_event_type,
            normalized_text=normalized_text,
            message_hash = content_hash,
            idempotency_identifier = idempotency_key
        )

        processing_outcome = "success"
         
        processing_completed_at = datetime.now(timezone.utc)
        processing_duration_ms = round((processing_completed_at - processing_started_at).total_seconds() * 1000, 2)
      
        
        updated_rows = db.query(RawMessages).filter(
            RawMessages.id == raw_msg.id,
            RawMessages.processed == False
        ).update({
            RawMessages.processed: True,
            RawMessages.processing_status: processing_outcome,
            RawMessages.processing_started_at: processing_started_at,
            RawMessages.processing_completed_at: processing_completed_at # <-- Stored exactly
        }, synchronize_session=False)
        
        if updated_rows == 0:
            db.rollback()
            processing_outcome = "duplicate_detected"
            processing_completed_at = datetime.now(timezone.utc)
            processing_duration_ms = round((processing_completed_at - processing_started_at).total_seconds() * 1000, 2)
            
            logger.warning(json.dumps({
                "event_type": "duplicate_detected",
                "job_id": job.job_id,
                "raw_message_id": raw_msg.id,
                "duplicate_status": "late_stage_concurrent_abort",
                "reason": "already_processed_during_execution",
                "processing_outcome": processing_outcome,
                "processing_duration_ms": processing_duration_ms,  
                "worker_identifier": WORKER_IDENTIFIER,            
                "timestamp": processing_completed_at.isoformat(),
                "message": "Message was completed by another worker during execution. Update aborted."
            }))
            return True

        parser = AIParser()
        extraction_result = parser.parse_single(
            text=normalized_text,
            timestamp=final_message_timestamp.isoformat()
        )

        if extraction_result and extraction_result.confidence > 0.0 and extraction_result.amount is not None:
            txn_date = final_message_timestamp
            if extraction_result.date:
                try:
                    txn_date = datetime.strptime(extraction_result.date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                except ValueError:
                    logger.warning(f"Could not parse LLM date output: {extraction_result.date}")

            new_transaction = Transactions(
                tenant_id = raw_msg.tenant_id,
                raw_message_id = raw_msg.id,
                amount=extraction_result.amount,
                currency=extraction_result.currency or "ZMW",
                txn_type=extraction_result.transaction_verb,
                txn_date=txn_date,
                confidence=extraction_result.confidence,
                status="PARSED",
                hash=content_hash,
                parsing_meta={
                    "source": "gemini-2.5-flash",
                    "raw_ai_output": extraction_result.model_dump()
                }
            )
            db.add(new_transaction)
            logger.info(json.dumps({
                "event_type": "transaction_extracted",
                "job_id": job.job_id,
                "amount": new_transaction.amount,
                "currency": new_transaction.currency,
                "confidence": new_transaction.confidence
            }))

            processing_outcome = "success"

            processing_completed_at = datetime.now(timezone.utc)
        db.commit()

        logger.info(json.dumps({
            "event_type": "job_processing_completed",
            "job_id": job.job_id,
            "raw_message_id": raw_msg.id,
            "processing_outcome": processing_outcome,
            "processing_duration_ms": processing_duration_ms,
            "worker_identifier": WORKER_IDENTIFIER,
            "timestamp": processing_completed_at.isoformat(),
            "message": "Job successfully processed and database state updated."
        }))

        return True

    except RETRYABLE_EXCEPTIONS as e:
        db.rollback()
        logger.warning(json.dumps({
            "event_type": "job_transient_failure",
            "job_id": job.job_id,
            "raw_message_id": job.raw_message_id,
            "error": str(e),
            "message": "Transient error encountered. Bubbling up to retry handler."
        }))
        raise  # Let the worker service catch this to trigger a retry!


    except Exception as e:
        db.rollback()
        processing_outcome = "failure"
        
        # --- Calculate duration on failure ---
        processing_completed_at = datetime.now(timezone.utc)
        processing_duration_ms = round((processing_completed_at - processing_started_at).total_seconds() * 1000, 2)
        # -------------------------------------
        
        try:
            db.query(RawMessages).filter(RawMessages.id == job.raw_message_id).update({
                RawMessages.processing_status: processing_outcome,
                RawMessages.processing_started_at: processing_started_at,
                RawMessages.processing_completed_at: processing_completed_at
            }, synchronize_session=False)
            db.commit()
        except Exception as inner_e:
            db.rollback()
            logger.error(f"Failed to save failure state to DB: {inner_e}")
        
        logger.error(json.dumps({
            "event_type": "job_processing_failed",
            "extraction_status": "error",
            "job_id": job.job_id,
            "raw_message_id": job.raw_message_id,
            "error": str(e),
            "processing_outcome": processing_outcome,
            "processing_duration_ms": processing_duration_ms, # <-- Added duration
            "worker_identifier": WORKER_IDENTIFIER,           # <-- Added worker ID
            "timestamp": processing_completed_at.isoformat()
        }), exc_info=True)
        return False
        
    finally:
        db.close()