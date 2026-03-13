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
APP_SECRET = os.getenv("WEBHOOK_VERIFY_TOKEN")

if not APP_SECRET:
    print("❌ ERROR: WEBHOOK_VERIFY_TOKEN is missing in .env")
    exit(1)

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

def run_ingestion_tests():
    print("--- Starting End-to-End Webhook Ingestion Tests ---\n")
    
    # Generate unique IDs for this test run to prevent clashing with older database data
    run_id = str(int(time.time()))
    phone_a = f"260999000{run_id[-3:]}"
    phone_b = f"260999111{run_id[-3:]}"
    group_x = f"group_x_{run_id}"
    group_y = f"group_y_{run_id}"

    # --- TEST 1: New Participant & New Group ---
    print("Test 1: Sending message from NEW Participant in NEW Group...")
    payload_1 = create_mock_payload(f"msg_1_{run_id}", phone_a, "Alice New", group_x, "Hello Group X!")
    res_1 = send_webhook(payload_1)
    if res_1.status_code == 200 and res_1.text == "EVENT_RECEIVED":
        print("✅ Passed: Ingested successfully.\n")
    else:
        raise Exception(f"❌ Failed: {res_1.status_code} - {res_1.text}\n")
         

    # --- TEST 2: Duplicate Message (Idempotency Check) ---
    print("Test 2: Resending the EXACT SAME payload (Duplicate Check)...")
    res_2 = send_webhook(payload_1)  # Sending payload_1 again
    if res_2.status_code == 200 and res_2.text == "DUPLICATE_IGNORED":
        print("✅ Passed: Duplicate caught and safely ignored.\n")
    else:
        raise Exception(f"❌ Failed: {res_2.status_code} - {res_2.text}\n")

    # --- TEST 3: Known Participant & New Group ---
    print("Test 3: Sending message from KNOWN Participant in NEW Group...")
    payload_3 = create_mock_payload(f"msg_3_{run_id}", phone_a, "Alice New", group_y, "Hello Group Y!")
    res_3 = send_webhook(payload_3)
    if res_3.status_code == 200 and res_3.text == "EVENT_RECEIVED":
        print("✅ Passed: Ingested successfully (Mapped to existing user).\n")
    else:
        raise Exception(f"❌ Failed: {res_3.status_code} - {res_3.text}\n")

    # --- TEST 4: New Participant & Known Group ---
    print("Test 4: Sending message from NEW Participant in KNOWN Group...")
    payload_4 = create_mock_payload(f"msg_4_{run_id}", phone_b, "Bob New", group_x, "I joined Group X!")
    res_4 = send_webhook(payload_4)
    if res_4.status_code == 200 and res_4.text == "EVENT_RECEIVED":
        print("✅ Passed: Ingested successfully (Mapped to existing group).\n")
    else:
        raise Exception(f"❌ Failed: {res_4.status_code} - {res_4.text}\n")

    # --- TEST 5: Direct Message (1-on-1, No Group) ---
    print("Test 5: Sending DIRECT 1-on-1 Message (No Group Context)...")
    # Group ID is explicitly None here
    payload_5 = create_mock_payload(f"msg_5_{run_id}", phone_b, "Bob New", group_id=None, text="Direct message to bot")
    res_5 = send_webhook(payload_5)
    if res_5.status_code == 200 and res_5.text == "EVENT_RECEIVED":
        print("✅ Passed: Direct message ingested successfully.\n")
    else:
        raise Exception(f"❌ Failed: {res_5.status_code} - {res_5.text}\n")

    print("--- 🏁 Ingestion Tests Complete! ---")
    print("👉 Check your FastAPI server logs to verify the structured JSON logging output!")

if __name__ == "__main__":
    run_ingestion_tests()