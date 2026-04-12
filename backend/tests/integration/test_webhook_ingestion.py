import os
import json
import time
import hmac
import hashlib
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

WEBHOOK_URL = "http://localhost:8000/api/v1/webhook"
APP_SECRET = os.getenv("WHATSAPP_APP_SECRET", os.getenv("WEBHOOK_VERIFY_TOKEN", "dummy_secret"))

def generate_signature(payload_bytes: bytes, secret: str) -> str:
    """Generates the HMAC SHA256 signature as Meta does."""
    signature = hmac.new(
        key=secret.encode('utf-8'),
        msg=payload_bytes,
        digestmod=hashlib.sha256
    ).hexdigest()
    return f"sha256={signature}"

def send_webhook(payload: dict) -> requests.Response:
    """Helper to send the payload with the correct headers."""
    # Serialize tightly as Meta does
    payload_bytes = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    signature = generate_signature(payload_bytes, APP_SECRET)
    
    headers = {
        'Content-Type': 'application/json',
        'x-hub-signature-256': signature
    }
    return requests.post(WEBHOOK_URL, data=payload_bytes, headers=headers)

def create_mock_payload(msg_id, sender_phone, sender_name, group_id=None, text="Test"):
    """Helper to generate a Meta-compliant webhook payload."""
    message = {
        "from": sender_phone,
        "id": msg_id,
        "timestamp": str(int(time.time())),
        "type": "text",
        "text": {"body": text}
    }
    
    # Simulate a group message if group_id is provided
    if group_id:
        message["context"] = {"from": group_id}

    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "contacts": [{
                        "profile": {"name": sender_name},
                        "wa_id": sender_phone
                    }],
                    "messages": [message]
                }
            }]
        }]
    }

def test_webhook_ingestion_flow():
    run_id = str(int(time.time()))
    phone_a = f"260999000{run_id[-3:]}"
    phone_b = f"260999111{run_id[-3:]}"
    group_x = f"group_x_{run_id}"
    group_y = f"group_y_{run_id}"

    payload_1 = create_mock_payload(f"msg_1_{run_id}", phone_a, "Alice New", group_x, "Hello Group X!")
    res_1 = send_webhook(payload_1)
    assert res_1.status_code == 200 and res_1.text == "EVENT_RECEIVED", f"Failed: {res_1.status_code} - {res_1.text}"

    res_2 = send_webhook(payload_1) 
    assert res_2.status_code == 200 and res_2.text == "DUPLICATE_IGNORED", f"Failed: {res_2.status_code} - {res_2.text}"

    payload_3 = create_mock_payload(f"msg_3_{run_id}", phone_a, "Alice New", group_y, "Hello Group Y!")
    res_3 = send_webhook(payload_3)
    assert res_3.status_code == 200 and res_3.text == "EVENT_RECEIVED", f"Failed: {res_3.status_code} - {res_3.text}"

    payload_4 = create_mock_payload(f"msg_4_{run_id}", phone_b, "Bob New", group_x, "I joined Group X!")
    res_4 = send_webhook(payload_4)
    assert res_4.status_code == 200 and res_4.text == "EVENT_RECEIVED", f"Failed: {res_4.status_code} - {res_4.text}"

    payload_5 = create_mock_payload(f"msg_5_{run_id}", phone_b, "Bob New", group_id=None, text="Direct message to bot")
    res_5 = send_webhook(payload_5)
    assert res_5.status_code == 200 and res_5.text == "EVENT_RECEIVED", f"Failed: {res_5.status_code} - {res_5.text}"