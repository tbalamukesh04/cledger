import os
import json
import time
import hmac
import hashlib
import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

WEBHOOK_URL = "http://127.0.0.1:8000/api/v1/webhook"
APP_SECRET = os.getenv("WEBHOOK_VERIFY_TOKEN", "dummy_secret")

def generate_signature(payload_bytes: bytes, secret: str) -> str:
    signature = hmac.new(
        key=secret.encode('utf-8'),
        msg=payload_bytes,
        digestmod=hashlib.sha256
    ).hexdigest()
    return f"sha256={signature}"

def test_latency():
    print("--- Measuring Webhook Async Flow Latency ---")
    
    # Create a unique payload
    run_id = str(time.time())
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"value": {
            "contacts": [{"profile": {"name": "Latency Tester"}, "wa_id": "1234567890"}],
            "messages": [{
                "from": "1234567890",
                "id": f"wamid.LATENCY_{run_id}",
                "timestamp": str(int(time.time())),
                "type": "text",
                "text": {"body": "Testing latency!"}
            }]
        }}]}]
    }

    payload_bytes = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    headers = {
        'Content-Type': 'application/json',
        'x-hub-signature-256': generate_signature(payload_bytes, APP_SECRET)
    }

    # Measure time
    start_time = time.perf_counter()
    response = requests.post(WEBHOOK_URL, data=payload_bytes, headers=headers)
    end_time = time.perf_counter()

    latency_ms = (end_time - start_time) * 1000

    print(f"Status Code: {response.status_code}")
    print(f"Response Body: {response.text}")
    print(f"⏱️ Webhook Round-Trip Latency: {latency_ms:.2f} ms")
    
    if response.status_code == 200 and latency_ms < 500:
        print("✅ SUCCESS: Webhook returns almost instantly, proving async decoupling is working!")
    else:
        print("⚠️ WARNING: Latency is high. Check for blocking synchronous operations.")

if __name__ == "__main__":
    test_latency()