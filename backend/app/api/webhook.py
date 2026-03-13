import os
import json
import logging
import time
from datetime import datetime, timezone
from fastapi.responses import PlainTextResponse
from fastapi import APIRouter, Request, HTTPException, Query, Response, Depends
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from redis import Redis

from app.api.dependencies import get_db, get_redis
from app.database.redis_client import WEBHOOK_QUEUE_NAME
from app.schemas.jobs import WebhookJobPayload
from app.utils.security import verify_whatsapp_signature
from app.utils.idempotency import generate_idempotency_key
from app.api.dependencies import get_db
from app.models.raw_messages import RawMessages
from app.models.participants import Participants
from app.models.groups import Groups

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/webhook", tags=["Webhook"])
async def verify_webhook(
    hub_mode:str = Query(None, alias="hub.mode"),
    hub_challenge:str = Query(None, alias="hub.challenge"),
    hub_verify_token:str = Query(None, alias="hub.verify_token")
):
    verify_token = os.getenv("WEBHOOK_VERIFY_TOKEN")
    if hub_mode == "subscribe" and hub_verify_token == verify_token:
        logger.info("Webhook verified successfully")
        return PlainTextResponse(content=hub_challenge, status_code=200)
    else:
        logger.warning("Webhook verification failed: Token Mismatch")
        raise HTTPException(status_code=403, detail="Verification Failed")
    raise HTTPException(status_code=400, detail="Invalid Request")

@router.post("/webhook", tags=["Webhook"])
async def receive_webhook(
    request: Request, 
    db: Session = Depends(get_db),
    redis_client: Redis = Depends(get_redis)
):
    start_time = time.perf_counter()
    client_ip = request.client.host if request.client else "unknown"
    try:
        raw_body = await request.body()
        signature = request.headers.get("x-hub-signature-256")
        
        if not signature:
            logger.warning(json.dumps({
                "event_type": "security_alert",
                "reason": "missing_signature_header",
                "source_ip": client_ip,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }))
            raise HTTPException(status_code=403, detail="Missing signature header")
        
        if not verify_whatsapp_signature(raw_body, signature):
            logger.warning(json.dumps({
                "event_type": "security_alert",
                "reason": "signature_mismatch",
                "source_ip": client_ip,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }))
            raise HTTPException(status_code=403, detail="Invalid Signature")
        
        try:
            body = json.loads(raw_body)
        except json.JSONDecodeError:
            logger.warning(json.dumps({
                "event_type": "security_alert",
                "reason": "malformed_json",
                "source_ip": client_ip,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }))
            raise HTTPException(status_code=400, detail="Malformed JSON Payload")
        
        idem_key = generate_idempotency_key(body)

        existing_msg = db.query(RawMessages).filter(RawMessages.hash == idem_key).first()
        if existing_msg:
            process_time_ms = (time.perf_counter() - start_time) * 1000
            logger.warning(json.dumps({
                "event_type": "security_alert",
                "reason": "duplicate_webhook",
                "source_ip": client_ip,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }))
            return Response(content="DUPLICATE_IGNORED", status_code=200)

        if body.get("object") == "whatsapp_business_account":
            for entry in body.get("entry", []):
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    contacts = value.get("contacts", [])

                    if "messages" in value:
                        for message in value["messages"]:
                            msg_id = message.get("id", idem_key)
                            timestamp_str = message.get("timestamp")
                            dt_received = datetime.fromtimestamp(int(timestamp_str), tz=timezone.utc) if timestamp_str else datetime.now(timezone.utc)
                            
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
                            media_id = None
                            raw_text = None

                            if msg_type == "text":
                                raw_text = message.get("text", {}).get("body")
                            elif msg_type in ["image", "video", "audio", "file"]:
                                media_id = message.get(msg_type, {}).get("id")
                            
                            logger.info(
                                f"Extracted Payload - Phone: {sender_phone}, Name: {sender_name}, Group ID: {group_id_str}, Type: {msg_type}, Media ID: {media_id}, Text: {raw_text}"
                            )
                            participant = db.query(Participants).filter(Participants.phone == sender_phone).first()

                            if participant:
                                sender_db_id = participant.id
                            else:
                                try:
                                    new_participant = Participants(
                                        tenant_id=1,
                                        phone=sender_phone,
                                        displayname=sender_name,
                                        username=sender_username
                                    )
                                    db.add(new_participant)
                                    db.flush()
                                    sender_db_id = new_participant.id
                                    logger.debug(f"Created New participant: {sender_phone} ID {sender_db_id}")
                                except IntegrityError as e:
                                    db.rollback()
                                    logger.warning(json.dumps({
                                        "event_type": "security_alert",
                                        "reason": "duplicate_user",
                                        "source_ip": client_ip,
                                        "timestamp": datetime.now(timezone.utc).isoformat()
                                    }))
                                    participant = db.query(Participants).filter(Participants.phone == sender_phone).first()
                                    sender_db_id = participant.id                            
                            
                            group = db.query(Groups).filter(Groups.group_id == group_id_str).first()
                            
                            if group:
                                group_db_id = group.id
                            else:
                                try:
                                    is_direct_message = (group_id_str == sender_phone)
                                    default_group_name = "Direct Message" if is_direct_message else "Unknown Group"
                                    new_group = Groups(
                                        tenant_id=1,
                                        group_id=group_id_str,
                                        groupname=default_group_name
                                        
                                    )
                                    db.add(new_group)
                                    db.flush()
                                    group_db_id = new_group.id
                                    logger.debug(f"Created New Group: {group_id_str} ID {group_db_id}")
                                except IntegrityError as e:
                                    db.rollback()
                                    logger.warning(json.dumps({
                                        "event_type": "security_alert",
                                        "reason": "duplicate_group",
                                        "source_ip": client_ip,
                                        "timestamp": datetime.now(timezone.utc).isoformat()
                                    }))
                                    group = db.query(Groups).filter(Groups.group_id == group_id_str).first()
                                    group_db_id = group.id

                            new_message = RawMessages(
                                tenant_id=1, 
                                group_id=group_db_id, 
                                sender_id=sender_db_id, 
                                message_id=msg_id,           
                                received_at=dt_received,
                                raw_json=body,
                                raw_text=raw_text,
                                hash=idem_key                
                            )
                            db.add(new_message)
                            
                            try:
                                db.commit()
                                
                                # --- Step 3: Job Serialization Logic ---
                                job_payload = WebhookJobPayload(
                                    raw_message_id=new_message.id,
                                    participant_id=sender_db_id,
                                    group_id=group_db_id,
                                    message_timestamp=dt_received,
                                    webhook_event_type=msg_type,
                                    ingestion_time=datetime.now(timezone.utc)
                                )
                                # ... [Previous Serialization Logic] ...
                                serialized_job = job_payload.to_json()
                                
                                try:
                                    redis_client.lpush(WEBHOOK_QUEUE_NAME, serialized_job)
                                    
                                    # --- NEW: Step 7 Queue Monitoring Log ---
                                    logger.info(json.dumps({
                                        "event_type": "queue_enqueue_success",
                                        "job_id": job_payload.job_id,
                                        "raw_message_id": job_payload.raw_message_id,
                                        "queue_name": WEBHOOK_QUEUE_NAME,
                                        "enqueue_timestamp": datetime.now(timezone.utc).isoformat()
                                    }))
                                    # ----------------------------------------
                                    
                                except Exception as e:
                                    # Update error log to be structured as well
                                    logger.error(json.dumps({
                                        "event_type": "queue_enqueue_failed",
                                        "raw_message_id": new_message.id,
                                        "queue_name": WEBHOOK_QUEUE_NAME,
                                        "error": str(e),
                                        "timestamp": datetime.now(timezone.utc).isoformat()
                                    }), exc_info=True)

                                # Calculate Latency for the primary success path
                                process_time_ms = (time.perf_counter() - start_time) * 1000
                                # ... [Keep existing webhook_ingestion_success log] ...
                                logger.info(json.dumps({
                                    "event_type": "webhook_ingestion_success",
                                    "message_id": msg_id,
                                    "participant_id": sender_db_id,
                                    "group_id": group_db_id,
                                    "enqueued_to_redis": True,
                                    "latency_ms": round(process_time_ms, 2), # <-- Log latency here
                                    "insertion_timestamp": datetime.now(timezone.utc).isoformat()
                                }))
                                
                            except IntegrityError as e:
                                db.rollback()
                                # --- Latency Log (DB Duplicate Path) ---
                                process_time_ms = (time.perf_counter() - start_time) * 1000
                                logger.warning(json.dumps({
                                    "event_type": "security_alert",
                                    "reason": "duplicate_webhook_db_catch",
                                    "hash": idem_key,
                                    "latency_ms": round(process_time_ms, 2)
                                }))
                                return Response(content="DUPLICATE_IGNORED_BY_DB", status_code=200)

            # Final return for standard successful processing
            return Response(content="EVENT_RECEIVED", status_code=200)
            
        else:
            return Response(content="Not a WhatsApp event", status_code=404)

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error processing webhook payload: {str(e)}", exc_info=True)
        return Response(content="Error processing event", status_code=200)