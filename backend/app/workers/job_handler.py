import logging
import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
import os
from typing import List, Dict
from collections import defaultdict

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
from app.utils.hashing import generate_content_hash, generate_text_hash
from app.ai.ai_parser import AIParser
from app.models.transactions import Transactions, TransactionStatus
from app.models.audit_logs import AuditLog, EventType, ActorType
from app.utils.date_normalization import normalize_extracted_date
from app.utils.financial_validation import validate_and_convert_amount, normalize_currency_code, normalize_transaction_verb
from app.ai.batch_request_builder import build_batch_request_payload
from app.parsing.scoring_engine import TransactionScorer
from app.schemas.parsing_metadata import ParsingMetadata
from app.ai.llm_extraction.extraction_service import process_extraction_batch
from app.ai.batch_response_parser import parse_batch_response
from app.ai.extraction_cache import get_cached_extractions_batch, cache_extraction_result
from app.ai.config import EXTRACTION_CONFIDENCE_THRESHOLD, AUTO_PARSE_CONFIDENCE_THRESHOLD
from app.crud.transaction_crud import upsert_transaction
from app.services.transaction_correction_service import correct_transaction_service, invalidate_transaction_service

from app.utils.logger import log_event, log_error, LogTimer
from app.core.log_events import LogEvent
from app.core.metrics import inc_metric

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
        log_error(LogEvent.JOB_FAILED, error=e, message="Payload traversal failed during text extraction", level=logging.WARNING)
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
        log_error(LogEvent.JOB_FAILED, error=e, message="Payload traversal failed during timestamp extraction", level=logging.WARNING)
        return None

def _parse_epoch_to_int(epoch_str: str | None) -> int | None:
    if not epoch_str:
        return None
    try:
        return int(epoch_str)
    except (ValueError, TypeError) as e:
        log_error(LogEvent.JOB_FAILED, error=e, message=f"Failed to parse epoch timestamp '{epoch_str}'", level=logging.WARNING)
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
        mutation_context_map = {}

        # 2. Preprocess, Score, and Filter duplicates locally
        for job in jobs:
            raw_msg = raw_msg_map.get(job.raw_message_id)
            if not raw_msg:
                log_error(LogEvent.JOB_FAILED, error=ValueError("RawMessage not found"), message=f"RawMessage {job.raw_message_id} not found.", level=logging.WARNING)
                job_results[job.job_id] = "dlq"
                continue

            # ENFORCE TENANT BOUNDARY: Reject if RawMessage belongs to a different tenant
            if getattr(raw_msg, "tenant_id", None) != job.tenant_id:
                log_error(LogEvent.SECURITY_VIOLATION, error=ValueError("Cross-tenant contamination attempt"), message=f"RawMessage {job.raw_message_id} belongs to tenant {getattr(raw_msg, 'tenant_id')}, but job payload claims {job.tenant_id}", level=logging.CRITICAL)
                job_results[job.job_id] = "dlq"
                continue

            raw_text = _extract_message_text(raw_msg.raw_json)
            normalized_text = normalize_whatsapp_text(raw_text)
            
            raw_epoch_str = _extract_message_timestamp(raw_msg.raw_json)
            parsed_epoch_int = _parse_epoch_to_int(raw_epoch_str)
            normalized_timestamp = convert_epoch_to_utc_datetime(parsed_epoch_int)
            final_timestamp = normalized_timestamp or raw_msg.received_at or job.message_timestamp
            
            content_hash = generate_content_hash(normalized_text, final_timestamp)
            text_hash = generate_text_hash(normalized_text)
            is_native_wamid = raw_msg.message_id and raw_msg.message_id.startswith("wamid.")
            # Align format with webhook.py (idem_msg_wamid.xxx) to prevent unnecessary DB updates
            idempotency_key = f"idem_msg_{raw_msg.message_id}" if is_native_wamid else f"idem_content_{content_hash}"

            if raw_msg.processed:
                log_event(LogEvent.JOB_STARTED, message=f"RawMessage {job.raw_message_id} already processed. Replay/Duplicate safely skipped.", level=logging.WARNING, reason="replay_protection", status="success")
                job_results[job.job_id] = "success"
                continue

            # Check DB Hash collision constraint locally
            if raw_msg.hash != idempotency_key:
                raw_msg.hash = idempotency_key # Staged for commit later

            sender_phone = raw_msg.sender.phone if raw_msg.sender else None
            sender_name = raw_msg.sender.displayname if raw_msg.sender else None
            group_whatsapp_id = raw_msg.group.group_id if raw_msg.group else None
            group_name = raw_msg.group.groupname if raw_msg.group else None
            
            # Message Mutation Detection (Edit/Revoke)
            msg_obj = raw_msg.raw_json.get("entry", [{}])[0].get("changes", [{}])[0].get("value", {}).get("messages", [{}])[0]
            context_obj = msg_obj.get("context", {})
            is_edit = context_obj.get("edit") is True
            original_wamid = context_obj.get("id")
            
            is_revoke = msg_obj.get("type") == "unsupported" or (msg_obj.get("type") == "system" and msg_obj.get("system", {}).get("type") == "revoke")

            if is_revoke:
                target_wamid = original_wamid or raw_msg.message_id
                orig_raw = db.query(RawMessages).filter(RawMessages.message_id == target_wamid, RawMessages.tenant_id == job.tenant_id).first()
                if orig_raw:
                    orig_txn = db.query(Transactions).filter(Transactions.raw_message_id == orig_raw.id, Transactions.tenant_id == job.tenant_id).first()
                    if orig_txn:
                        invalidate_transaction_service(db, orig_txn.id, tenant_id=job.tenant_id, reason="Message revoked on WhatsApp", actor_identifier=WORKER_IDENTIFIER)
                raw_msg.processed = True
                raw_msg.processing_status = "REVOKED"
                raw_msg.processing_started_at = processing_started_at
                raw_msg.processing_completed_at = datetime.now(timezone.utc)
                job_results[job.job_id] = "success"
                continue
            
            if is_edit:
                mutation_context_map[raw_msg.id] = {"type": "edit", "original_wamid": original_wamid}

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
                text_hash=text_hash,
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

            log_event(
                LogEvent.JOB_STARTED,
                "Message classification metadata generated",
                raw_message_id=str(job.raw_message_id),
                score=context.scoring.total_score,
                threshold=scorer.threshold,
                is_transaction=context.scoring.is_transaction_candidate,
                db_update_status="pending_commit"
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
        batch_id = str(uuid.uuid4()) # Define at the outer scope to prevent UnboundLocalError on 100% cache hits
        candidates_for_ai_misses = []
        extracted_data_map = {}

        text_hashes = [c.text_hash for c in candidates_for_ai]
        cache_lookups = get_cached_extractions_batch(text_hashes)

        for preprocessed_data in candidates_for_ai:
            cached_schema = cache_lookups.get(preprocessed_data.text_hash)
            if cached_schema:
                log_event(LogEvent.JOB_STARTED, "Extraction Cache Hit", raw_message_id=str(preprocessed_data.raw_message_id), cache_status="hit")
                extracted_data_map[str(preprocessed_data.raw_message_id)] = cached_schema
            else:
                log_event(LogEvent.JOB_STARTED, "Extraction Cache Miss", raw_message_id=str(preprocessed_data.raw_message_id), cache_status="miss")
                candidates_for_ai_misses.append(preprocessed_data)
                
        batch_failed = False

        if candidates_for_ai_misses:
            misses_by_tenant = defaultdict(list)
            for c in candidates_for_ai_misses:
                c_job = valid_jobs_map[c.raw_message_id]
                c.tenant_id = c_job.tenant_id  # Inject for validation in AI extraction service
                misses_by_tenant[c_job.tenant_id].append(c)

            for tenant_id, tenant_misses in misses_by_tenant.items():
                batch_id = str(uuid.uuid4())
                candidate_miss_ids = [str(c.raw_message_id) for c in tenant_misses]
                miss_hash_map = {str(c.raw_message_id): c.text_hash for c in tenant_misses}

                timer = LogTimer()
                gemini_response_status = "success"

                try:
                    raw_llm_response = process_extraction_batch(tenant_misses, tenant_id=tenant_id)
                    llm_extracted_data = parse_batch_response(raw_llm_response, candidate_miss_ids, batch_id)
                    extracted_data_map.update(llm_extracted_data)
                    
                    for msg_id, ext_result in llm_extracted_data.items():
                        if ext_result:
                            text_hash = miss_hash_map.get(msg_id)
                            if text_hash:
                                cache_extraction_result(text_hash, ext_result)
                                log_event(LogEvent.JOB_STARTED, "Extraction Result Cached", raw_message_id=msg_id)

                except RETRYABLE_EXCEPTIONS as e:
                    raise e
                
                except Exception as e:
                    gemini_response_status = "failed"
                    log_error(LogEvent.LLM_ERROR, error=e, message="AI Batch extraction failed completely for tenant", batch_id=batch_id, tenant_id=tenant_id)

                log_event(
                    LogEvent.JOB_STARTED,
                    "Batch extraction routine completed",
                    batch_id=batch_id,
                    batch_size=len(tenant_misses),
                    tenant_id=tenant_id,
                    duration_ms=timer.get_duration_ms(),
                    status=gemini_response_status
                )

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
                confidence_score = extraction_result.confidence_score
                raw_extracted_date = getattr(extraction_result, "transaction_date", getattr(extraction_result, "date", None))
                raw_extracted_verb = extraction_result.transaction_verb
                
            normalized_txn_verb = normalize_transaction_verb(raw_extracted_verb)
            
            # AI Natural Language Reversal Detection
            is_ai_reversal = False
            if raw_extracted_verb and str(raw_extracted_verb).lower() in ["reversal", "undo", "reverse", "cancel"]:
                is_ai_reversal = True
                extraction_status = "REVERSAL_PROCESSED"
                normalized_txn_verb = "reversal"
            else:
                extraction_status = "SUCCESS" if (validated_amount is not None and normalized_txn_verb is not None) else ("NON_TRANSACTION" if extraction_result else "AI_EXTRACTION_FAILED")
            
            normalized_txn_date = normalize_extracted_date(raw_extracted_date, preprocessed_data.normalized_timestamp)
            current_meta = raw_msg.parsing_meta or {}
            
            # --- STAGE 4 & 5: CONFIDENCE EVALUATION & ROUTING DECISION ---
            txn_db_status = None
            routing_action = None

            if extraction_status == "REVERSAL_PROCESSED":
                last_txn = db.query(Transactions).join(RawMessages).filter(
                    RawMessages.group_id == preprocessed_data.group_id,
                    Transactions.tenant_id == job.tenant_id,
                    Transactions.status != TransactionStatus.INVALIDATED
                ).order_by(Transactions.created_at.desc()).first()
                if last_txn:
                    invalidate_transaction_service(db, last_txn.id, tenant_id=job.tenant_id, reason="AI Reversal Intent Detected", actor_identifier=WORKER_IDENTIFIER)
                raw_msg.is_transaction = True

            elif extraction_status == "SUCCESS":
                if confidence_score >= AUTO_PARSE_CONFIDENCE_THRESHOLD:
                    txn_db_status = TransactionStatus.PARSED
                    routing_action = "auto_accepted"
                elif confidence_score >= EXTRACTION_CONFIDENCE_THRESHOLD:
                    txn_db_status = TransactionStatus.REVIEW_NEEDED
                    routing_action = "flagged_for_review"
                else:
                    # Hard reject on low confidence. Safely bypass Transactions table insertion.
                    extraction_status = "REJECTED_LOW_CONFIDENCE"
                    txn_db_status = None
                    routing_action = "rejected_low_confidence"

            current_meta["ai_extraction"] = {
                "source": "gemini-2.5-flash",
                "model": "gemini-2.5-flash", 
                "batch_processed": True,
                "batch_id": batch_id,
                "status": extraction_status,
                "confidence": confidence_score if extraction_result else 0.0,
                "prompt_version": getattr(extraction_result, "prompt_version", None) if extraction_result else None,
                "routing_status": txn_db_status.value if txn_db_status else None,
                "routing_action": routing_action,
                "extraction_timestamp": datetime.now(timezone.utc).isoformat(),
                "raw_ai_output": extraction_result.model_dump() if extraction_result else None
            }

            log_event(
                LogEvent.TRANSACTION_CREATED,
                "Confidence Routing Decision Made",
                raw_message_id=str(preprocessed_data.raw_message_id),
                confidence=confidence_score if extraction_result else 0.0,
                status=txn_db_status.value if txn_db_status else "rejected"
            )

            raw_msg.parsing_meta = current_meta

            if extraction_status == "SUCCESS":
                mutation_ctx = mutation_context_map.get(raw_msg.id)
                remarks_text = getattr(extraction_result, "description", getattr(extraction_result, "remarks", None))
                
                if mutation_ctx and mutation_ctx.get("type") == "edit" and mutation_ctx.get("original_wamid"):
                    orig_raw = db.query(RawMessages).filter(RawMessages.message_id == mutation_ctx["original_wamid"], RawMessages.tenant_id == job.tenant_id).first()
                    if orig_raw:
                        orig_txn = db.query(Transactions).filter(Transactions.raw_message_id == orig_raw.id, Transactions.tenant_id == job.tenant_id).first()
                        if orig_txn:
                            correction_data = {
                                "amount": validated_amount,
                                "currency": normalized_currency,
                                "txn_type": normalized_txn_verb,
                                "txn_date": normalized_txn_date,
                                "remarks": remarks_text
                            }
                            correct_transaction_service(db, orig_txn.id, tenant_id=job.tenant_id, correction_data=correction_data, actor_identifier=WORKER_IDENTIFIER)
                            txn_db_status = TransactionStatus.CORRECTED
                            log_event(LogEvent.TRANSACTION_UPDATED, "Transaction Corrected via Webhook Edit", transaction_id=orig_txn.id)
                
                if txn_db_status in [TransactionStatus.PARSED, TransactionStatus.REVIEW_NEEDED]:
                    txn_data = {
                        "tenant_id": job.tenant_id,
                        "raw_message_id": raw_msg.id,
                        "amount": validated_amount,  
                        "currency": normalized_currency,
                        "txn_type": normalized_txn_verb,
                        "txn_date": normalized_txn_date,
                        "confidence": confidence_score,
                        "status": txn_db_status, 
                        "hash": preprocessed_data.message_hash,
                        "parsing_meta": current_meta,
                        "remarks": remarks_text
                    }
                    try: 
                        upsert_transaction(db=db, txn_data=txn_data, commit=False, actor_identifier=WORKER_IDENTIFIER)
                        inc_metric("total_transactions")
                        raw_msg.is_transaction = True
                    except ValueError as e:
                        log_event(LogEvent.SYSTEM_ERROR, f"Duplicate transaction skipped: {e}", level=logging.WARNING)

            processing_outcome = "success" if extraction_status in ["SUCCESS", "NON_TRANSACTION", "REVERSAL_PROCESSED"] else "review_needed"
            
            raw_msg.processed = True
            raw_msg.processing_status = processing_outcome
            raw_msg.processing_started_at = processing_started_at
            raw_msg.processing_completed_at = datetime.now(timezone.utc)

            if processing_outcome == "review_needed":
                audit_reason = "LOW_CONFIDENCE" if extraction_status == "REJECTED_LOW_CONFIDENCE" else (
                    "AI_EXTRACTION_FAILED" if extraction_status == "AI_EXTRACTION_FAILED" else "LLM_SCHEMA_INVALID"
                )
                audit = AuditLog(
                    entity_type="raw_message",
                    entity_id=str(raw_msg.id),
                    event_type=EventType.UPDATE,
                    actor_type=ActorType.SYSTEM,
                    actor_identifier=WORKER_IDENTIFIER,
                    old_state=None,
                    new_state={"status": "review_needed", "reason": audit_reason}
                )
                db.add(audit)
            
            # Message is processed and safely routed to human review database state. No DLQ necessary.
            job_results[job.job_id] = "success"

        # 5. Commit whole batch
        try:
            db.commit()
            log_event(
                LogEvent.JOB_STARTED, 
                "Batch processing completed successfully", 
                status="completed", 
                total_jobs_processed=len(jobs)
            )
        except IntegrityError as e:
            db.rollback()
            log_error(LogEvent.JOB_FAILED, error=e, message="Batch DB commit failed due to integrity error")
            for job in jobs:
                job_results[job.job_id] = "retry"

        return job_results

    except RETRYABLE_EXCEPTIONS as e:
        db.rollback()
        log_error(LogEvent.JOB_FAILED, error=e, message="Transient error in batch. Will retry.")
        return {job.job_id: "retry" for job in jobs}
    except Exception as e:
        db.rollback()
        log_error(LogEvent.JOB_FAILED, error=e, message="Fatal error in batch processing. Routing to DLQ.")
        return {job.job_id: "dlq" for job in jobs}
    finally:
        db.close()