import logging
import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy.orm import joinedload
from sqlalchemy.exc import IntegrityError

from app.schemas.jobs import WebhookJobPayload
from app.schemas.preprocessing import PreprocessedPayload
from app.database.database import SessionLocal
from app.models.raw_messages import RawMessages
from app.models.groups import Groups
from app.models.participants import Participants
from app.utils.text_processing import normalize_whatsapp_text
from app.utils.datetime_utils import convert_epoch_to_utc_datetime
from app.utils.hashing import generate_content_hash

logger = logging.getLogger(__name__)

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
    
    try:
        logger.info(json.dumps({
            "event_type": "job_processing_started", 
            "job_id": job.job_id,
            "raw_message_id": job.raw_message_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }))

        raw_msg = db.query(RawMessages).options(
            joinedload(RawMessages.sender),
            joinedload(RawMessages.group)
        ).filter(RawMessages.id == job.raw_message_id).first()
        
        if not raw_msg:
            logger.error(json.dumps({
                "event_type": "job_processing_error",
                "extraction_status": "failed",
                "reason": "RawMessage record not found in database",
                "job_id": job.job_id,
                "raw_message_id": job.raw_message_id
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

        logger.info(json.dumps({
            "event_type": "idempotency_identifier_selected",
            "job_id": job.job_id,
            "raw_message_id": raw_msg.id,
            "whatsapp_message_id": raw_msg.message_id,
            "message_hash": content_hash,
            "idempotency_key": idempotency_key,
            "idempotency_source": idempotency_source,
            "message": "Hash generated and idempotency identifier selected."
        }))

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
                "message": "Duplicate detected. Aborting pipeline safely."
                }))

                return True

        if raw_msg.hash != idempotency_key:
            try:
                raw_msg.hash = idempotency_key
                db.commit()
            except IntegrityError:
                db.rollback()
                logger.warning(json.dumps({
                    "event_type": "duplicate_detected",
                    "job_id": job.job_id,
                    "raw_message_id": raw_msg.id,
                    "whatsapp_message_id": raw_msg.message_id,
                    "message_hash": content_hash,
                    "duplicate_status": "concurrent_abort",
                    "idempotency_key": idempotency_key,
                    "reason": "concurrent_hash_collision",
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

        logger.info(json.dumps({
            "event_type": "metadata_extraction_complete",
            "extraction_status": "success",
            "job_id": job.job_id,
            "raw_message_id": preprocessed_data.raw_message_id,
            "idempotency_key": preprocessed_data.idempotency_identifier,
            "message_hash": preprocessed_data.message_hash,
            "duplicate_status": "clear", 
            "idempotency_source": idempotency_source
        }))

        return True
    
    except Exception as e:
        logger.error(json.dumps({
            "event_type": "job_processing_failed",
            "extraction_status": "error",
            "job_id": job.job_id,
            "raw_message_id": job.raw_message_id,
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }), exc_info=True)
        return False
        
    finally:
        db.close()