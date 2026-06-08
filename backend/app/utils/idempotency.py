import hashlib
import json
import logging

logger = logging.getLogger(__name__)

def generate_idempotency_key(payload: dict) -> str:
    """Generate a unique idempotency key based on the payload"""
    try:
        if payload.get("object") == "whatsapp_business_account":
            for entry in payload.get("entry", []):
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    if "messages" in value and len(value["messages"]) > 0:
                        msg_id = value["messages"][0].get("id")
                        if msg_id:
                            return f"idem_msg_{msg_id}"

                    elif "statuses" in value and len(value["statuses"]) > 0:
                        status_id = value["statuses"][0].get("id")
                        if status_id:
                            return f"idem_stat_{status_id}"
                            
    except Exception as e:
        logger.warning(f"Error extracting ID for idempotency key: {str(e)}")

    logger.info("Message ID not found, falling back to deterministic hash")

    payload_str = json.dumps(payload, sort_keys=True, separators=(',',':'))
    payload_hash = hashlib.sha256(payload_str.encode('utf-8')).hexdigest()

    return f"idem_hash_{payload_hash}"