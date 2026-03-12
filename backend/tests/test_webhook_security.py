import os
import hmac
import hashlib
import json
import time
import requests
from dotenv import load_dotenv

# Load environment variables to get the App Secret
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

WEBHOOK_URL = "http://localhost:8000/api/v1/webhook"
APP_SECRET = os.getenv("WEBHOOK_VERIFY_TOKEN", "dummy_secret_for_testing")

def generate_signature(payload_bytes: bytes, secret: str) -> str:
    """Generates the HMAC SHA256 signature as Meta does."""
    signature = hmac.new(
        key=secret.encode('utf-8'),
        msg=payload_bytes,
        digestmod=hashlib.sha256
    ).hexdigest()
    return f"sha256={signature}"

def run_security_tests():
    print(f"--- Starting Webhook Security Validation ---")
    print(f"Target URL: {WEBHOOK_URL}\n")

    # 1. Create a mock payload with a unique ID to avoid clashing with older tests
    unique_id = f"wamid.SEC_TEST_{int(time.time())}"
    mock_payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "from": "260999999999",
                        "id": unique_id,
                        "timestamp": str(int(time.time())),
                        "type": "text",
                        "text": {"body": "Security test message"}
                    }]
                }
            }]
        }]
    }

    # IMPORTANT: We must manually serialize to bytes so we know EXACTLY what we are hashing and sending.
    payload_bytes = json.dumps(mock_payload, separators=(',', ':')).encode('utf-8')
    valid_signature = generate_signature(payload_bytes, APP_SECRET)

    # --- TEST 1: Missing Signature Header ---
    print("Test 1: Missing Signature Header")
    res1 = requests.post(
        WEBHOOK_URL, 
        data=payload_bytes, 
        headers={'Content-Type': 'application/json'}
    )
    if res1.status_code == 403:
        print("✅ Passed: Request rejected with 403 Forbidden.\n")
    else:
        print(f"❌ Failed: Expected 403, got {res1.status_code}\n")

    # --- TEST 2: Invalid Signature ---
    print("Test 2: Invalid Signature Mismatch")
    res2 = requests.post(
        WEBHOOK_URL, 
        data=payload_bytes, 
        headers={
            'Content-Type': 'application/json',
            'x-hub-signature-256': 'sha256=abcdef1234567890bogussignature'
        }
    )
    if res2.status_code == 403:
        print("✅ Passed: Request rejected with 403 Forbidden.\n")
    else:
        print(f"❌ Failed: Expected 403, got {res2.status_code}\n")

    # --- TEST 3: Valid Signature (First Delivery) ---
    print("Test 3: Valid Signature (Initial Delivery)")
    res3 = requests.post(
        WEBHOOK_URL, 
        data=payload_bytes, 
        headers={
            'Content-Type': 'application/json',
            'x-hub-signature-256': valid_signature
        }
    )
    if res3.status_code == 200 and res3.text == "EVENT_RECEIVED":
        print("✅ Passed: Valid request accepted (200 OK).\n")
    else:
        print(f"❌ Failed: Expected 200 OK EVENT_RECEIVED, got {res3.status_code} - {res3.text}\n")

    # --- TEST 4: Duplicate Payload (Replay Attack) ---
    print("Test 4: Duplicate Payload (Replay Attempt)")
    res4 = requests.post(
        WEBHOOK_URL, 
        data=payload_bytes, 
        headers={
            'Content-Type': 'application/json',
            'x-hub-signature-256': valid_signature
        }
    )
    if res4.status_code == 200 and res4.text == "DUPLICATE_IGNORED":
        print("✅ Passed: Duplicate ignored safely (200 OK to stop Meta retries).\n")
    else:
        print(f"❌ Failed: Expected 200 OK DUPLICATE_IGNORED, got {res4.status_code} - {res4.text}\n")
        
    print("--- Security Validation Complete ---")

if __name__ == "__main__":
    run_security_tests()