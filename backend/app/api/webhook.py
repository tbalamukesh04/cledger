import os
import json
import logging
from datetime import datetime, timezone
from fastapi.responses import PlainTextResponse
from fastapi import APIRouter, Request, HTTPException, Query, Response, Depends
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

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
async def receive_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Endpoint to receive incoming WhatsApp webhook events.
    Parses messages and status updates safely, enforcing idempotency.
    """
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

                    if "messages" in value:
                        for message in value["messages"]:
                            msg_id = message.get("id", idem_key)
                            timestamp_str = message.get("timestamp")
                            dt_received = datetime.fromtimestamp(int(timestamp_str), tz=timezone.utc) if timestamp_str else datetime.now(timezone.utc)
                            
                            raw_text = None
                            if message.get("type") == "text":
                                raw_text = message.get("text", {}).get("body")

                            new_message = RawMessages(
                                tenant_id=1, 
                                group_id=1, 
                                sender_id=1, 
                                message_id=msg_id,           
                                received_at=dt_received,
                                raw_json=body,
                                raw_text=raw_text,
                                hash=idem_key                
                            )
                            db.add(new_message)
                            
                            try:
                                db.commit()
                                logger.info(f"✅ Successfully inserted new raw message: {idem_key}")
                            except IntegrityError as e:
                                db.rollback()
                                logger.warning(json.dumps({
                                    "event_type": "security_alert",
                                    "reason": "duplicate_webhook",
                                    "source_ip": client_ip,
                                    "timestamp": datetime.now(timezone.utc).isoformat()
                                }))
                                return Response(content="DUPLICATE_IGNORED_BY_DB", status_code=200)

            return Response(content="EVENT_RECEIVED", status_code=200)
        
        else:
            return Response(content="Not a WhatsApp event", status_code=404)

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error processing webhook payload: {str(e)}", exc_info=True)
        return Response(content="Error processing event", status_code=200)