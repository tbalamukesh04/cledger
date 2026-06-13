import os
import json
import logging
from datetime import datetime, timezone
from fastapi.responses import PlainTextResponse
from fastapi import APIRouter, Request, HTTPException, Query, Response, Depends
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from redis import Redis

from app.api.dependencies import get_db, get_redis
from app.middleware.rate_limiter import RateLimiter
from app.database.redis_client import WEBHOOK_QUEUE_NAME
from app.schemas.jobs import WebhookJobPayload
from app.utils.security import verify_whatsapp_signature
from app.utils.idempotency import generate_idempotency_key
from app.models.raw_messages import RawMessages
from app.models.participants import Participants
from app.models.groups import Groups
from app.utils.logger import log_event, log_error, LogTimer
from app.core.log_events import LogEvent
from app.core.metrics import inc_metric
from app.middleware.ip_filter import IPFilter
from app.services.tenant_resolution_service import resolve_tenant_from_webhook

router = APIRouter()

@router.get("/webhook", tags=["Webhook"], dependencies=[
    Depends(RateLimiter(requests=15, window=60)),
    Depends(IPFilter(allowed_ips_env_key="WEBHOOK_ALLOWED_IPS"))
])
async def verify_webhook(
    hub_mode:str = Query(None, alias="hub.mode"),
    hub_challenge:str = Query(None, alias="hub.challenge"),
    hub_verify_token:str = Query(None, alias="hub.verify_token")
):
    verify_token = os.getenv("WEBHOOK_VERIFY_TOKEN")
    if hub_mode == "subscribe" and hub_verify_token == verify_token:
        log_event(LogEvent.WEBHOOK_RECEIVED, "Webhook verified successfully", status="success")
        return PlainTextResponse(content=hub_challenge, status_code=200)
    else:
        log_event(LogEvent.WEBHOOK_RECEIVED, "Webhook verification failed: Token Mismatch", level=logging.WARNING, status="failed")
        raise HTTPException(status_code=403, detail="Verification Failed")
    raise HTTPException(status_code=400, detail="Invalid Request")

@router.post("/webhook", tags=["Webhook"], dependencies=[
    Depends(RateLimiter(requests=15, window=60)),
    Depends(IPFilter(allowed_ips_env_key="WEBHOOK_ALLOWED_IPS"))
    ]
)

async def receive_webhook(
    request: Request, 
    db: Session = Depends(get_db),
    redis_client: Redis = Depends(get_redis)
):
    timer = LogTimer()
    client_ip = request.client.host if request.client else "unknown"
    try:
        raw_body = await request.body()
        signature = request.headers.get("x-hub-signature-256")
        
        # Enforce cryptographic signature validation globally except in explicit local development
        if os.getenv("ENVIRONMENT") != "development":
            if not signature:
                log_event(LogEvent.SYSTEM_ERROR, "Missing signature header", level=logging.WARNING, reason="missing_signature_header", source_ip=client_ip, status="rejected")
                raise HTTPException(status_code=403, detail="Missing signature header")
            
            if not verify_whatsapp_signature(raw_body, signature):
                log_event(LogEvent.SYSTEM_ERROR, "Invalid Signature", level=logging.WARNING, reason="signature_mismatch", source_ip=client_ip, status="rejected")
                raise HTTPException(status_code=403, detail="Invalid Signature")
        
        try:
            body = json.loads(raw_body)
            with open("/var/log/app/whatsapp_payload.json", "w") as dump_file:
                import json as _json
                dump_file.write(_json.dumps(body, indent=2))
        except json.JSONDecodeError:
            log_event(LogEvent.SYSTEM_ERROR, "Malformed JSON Payload", level=logging.WARNING, reason="malformed_json", source_ip=client_ip, status="rejected")
            raise HTTPException(status_code=400, detail="Malformed JSON Payload")
        
        idem_key = generate_idempotency_key(body)

        existing_msg = db.query(RawMessages).filter(RawMessages.hash == idem_key).first()
        if existing_msg:
            log_event(LogEvent.WEBHOOK_RECEIVED, "Duplicate webhook payload ignored", level=logging.WARNING, reason="duplicate_webhook", hash=idem_key, duration_ms=timer.get_duration_ms(), status="duplicate")
            return Response(content="DUPLICATE_IGNORED", status_code=200)

        if body.get("object") == "whatsapp_business_account":
            for entry in body.get("entry", []):
                waba_id = entry.get("id")
                
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    
                    # --- Tenant Resolution ---
                    phone_number_id = value.get("metadata", {}).get("phone_number_id")
                    tenant_id = resolve_tenant_from_webhook(db, phone_number_id=phone_number_id, waba_id=waba_id)
                    
                    if not tenant_id:
                        # Quarantine logic: Return 200 to prevent retry loops, but log heavily and do not process
                        log_event(
                            LogEvent.SYSTEM_ERROR, 
                            "Unmatched Webhook Quarantined", 
                            level=logging.WARNING, 
                            reason="tenant_resolution_failed", 
                            waba_id=waba_id, 
                            phone_number_id=phone_number_id,
                            status="quarantined"
                        )
                        return Response(content="UNMATCHED_WEBHOOK_QUARANTINED", status_code=200)

                    contacts = value.get("contacts", [])

                    if "messages" in value:
                        for message in value["messages"]:
                            msg_id = message.get("id", idem_key)
                            timestamp_str = message.get("timestamp")
                            dt_received = datetime.now(timezone.utc)

                            if timestamp_str:
                                try:
                                    dt_received = datetime.fromtimestamp(int(timestamp_str), tz=timezone.utc)
                                except (ValueError, TypeError):
                                    log_event(LogEvent.SYSTEM_ERROR, f"Invalid Meta timestamp fallback: {timestamp_str}", level=logging.WARNING)
                            
                            sender_phone = message.get("from")
                            sender_name = ""
                            sender_username = None

                            for contact in contacts:
                                if contact.get("wa_id") == sender_phone:
                                    sender_name = contact.get("profile", {}).get("name", "")
                                    sender_username = contact.get("profile", {}).get("username", None)
                                    break

                            group_id_str = message.get("context", {}).get("from", sender_phone)
                            msg_type = message.get("type")
                            media_id = message.get(msg_type, {}).get("id") if msg_type in ["image", "video", "audio", "file"] else None
                            raw_text = message.get("text", {}).get("body") if msg_type == "text" else None

                            log_event(LogEvent.WEBHOOK_RECEIVED, "Payload Extracted", phone_number=sender_phone, name=sender_name, msg_type=msg_type, raw_message_text=raw_text)

                            # Scope lookups and creation strictly to the resolved tenant boundary
                            participant = db.query(Participants).filter(Participants.phone == sender_phone, Participants.tenant_id == tenant_id).first()
                            if participant:
                                sender_db_id = participant.id
                            else:
                                try:
                                    new_participant = Participants(tenant_id=tenant_id, phone=sender_phone, displayname=sender_name, username=sender_username)
                                    db.add(new_participant)
                                    db.flush()
                                    sender_db_id = new_participant.id
                                except IntegrityError:
                                    db.rollback()
                                    sender_db_id = db.query(Participants).filter(Participants.phone == sender_phone, Participants.tenant_id == tenant_id).first().id                            
                            
                            group = db.query(Groups).filter(Groups.group_id == group_id_str, Groups.tenant_id == tenant_id).first()
                            if group:
                                group_db_id = group.id
                            else:
                                try:
                                    new_group = Groups(tenant_id=tenant_id, group_id=group_id_str, groupname="Direct Message" if group_id_str == sender_phone else "Unknown Group")
                                    db.add(new_group)
                                    db.flush()
                                    group_db_id = new_group.id
                                except IntegrityError:
                                    db.rollback()
                                    group_db_id = db.query(Groups).filter(Groups.group_id == group_id_str, Groups.tenant_id == tenant_id).first().id

                            new_message = RawMessages(
                                tenant_id=tenant_id, group_id=group_db_id, sender_id=sender_db_id, 
                                message_id=msg_id, received_at=dt_received, raw_json=body,
                                raw_text=raw_text, hash=idem_key                
                            )
                            db.add(new_message)
                            
                            try:
                                db.commit()
                                
                                job_payload = WebhookJobPayload(
                                    tenant_id=tenant_id,
                                    raw_message_id=new_message.id, 
                                    participant_id=sender_db_id, 
                                    group_id=group_db_id,
                                    message_timestamp=dt_received, 
                                    webhook_event_type=msg_type, 
                                    ingestion_time=datetime.now(timezone.utc)
                                )
                                
                                try:
                                    redis_client.lpush(WEBHOOK_QUEUE_NAME, job_payload.to_json())
                                    inc_metric("total_webhooks")
                                    log_event(LogEvent.JOB_STARTED, "Job Enqueued", job_id=job_payload.job_id, raw_message_id=str(new_message.id), queue_name=WEBHOOK_QUEUE_NAME, status="enqueued")
                                except Exception as e:
                                    log_error(LogEvent.JOB_FAILED, error=e, message="Failed to enqueue job", raw_message_id=str(new_message.id), queue_name=WEBHOOK_QUEUE_NAME, status="dlq")

                                log_event(LogEvent.WEBHOOK_RECEIVED, "Webhook ingestion successful", raw_message_id=msg_id, duration_ms=timer.get_duration_ms(), status="success")
                                
                            except IntegrityError:
                                db.rollback()
                                log_event(LogEvent.WEBHOOK_RECEIVED, "Duplicate webhook caught by DB", level=logging.WARNING, reason="duplicate_db_catch", hash=idem_key, duration_ms=timer.get_duration_ms(), status="duplicate")
                                return Response(content="DUPLICATE_IGNORED_BY_DB", status_code=200)

            return Response(content="EVENT_RECEIVED", status_code=200)
            
        else:
            return Response(content="Not a WhatsApp event", status_code=404)

    except HTTPException as he:
        raise he
    except Exception as e:
        log_error(LogEvent.SYSTEM_ERROR, error=e, message="Error processing webhook payload")
        return Response(content="Error processing event", status_code=200)