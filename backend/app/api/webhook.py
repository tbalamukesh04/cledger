import os
import json
import logging
from fastapi.responses import PlainTextResponse
from fastapi import APIRouter, Request, HTTPException, Query, Response 

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
async def receive_webhook(request: Request):
    """
    Endpoint to receive incoming WhatsApp webhook events.
    Parses messages and status updates safely.
    """
    try:
        body = await request.json()
        logger.info(f"Received Webhook Payload: {body}")

        if body.get("object") == "whatsapp_business_account":
            for entry in body.get("entry", []):
                for change in entry.get("changes", []):
                    value = change.get("value", {})

                    if "messages" in value:
                        for message in value["messages"]:
                            event_meta = {
                                "event_type": f"message_{message.get('type')}",
                                "source_identifier": message.get("from"),
                                "event_timestamp": message.get("timestamp"),
                                "raw_payload": body
                            }
                            logger.info(f"Incoming Webhook: {json.dumps(event_meta)}")
                            
                    elif "statuses" in value:
                        for status in value["statuses"]:
                            event_meta = {
                                "event_type": f"status_{status.get('status')}",
                                "source_identifier": status.get("recipient_id"),
                                "event_timestamp": status.get("timestamp"),
                                "raw_payload": body
                            }
                        logger.info(f"Incoming Webhook: {json.dumps(event_meta)}")
            return Response(content="EVENT_RECEIVED", status_code=200)
        
        else:
            return Response(content="Not a WhatsApp event", status_code=404)

    except Exception as e:
        logger.error(f"Error processing webhook payload: {str(e)}", exc_info=True)
        return Response(content="Error processing event", status_code=200)