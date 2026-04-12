import os
import json
import time
import hmac
import hashlib
import requests
import concurrent.futures
from dotenv import load_dotenv

from app.database.redis_client import redis_client, WEBHOOK_QUEUE_NAME

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

# Use 127.0.0.1 to avoid localhost IPv6 DNS timeouts on Windows
WEBHOOK_URL = "http://127.0.0.1:8000/api/v1/webhook"
APP_SECRET = os.getenv("WEBHOOK_VERIFY_TOKEN", "dummy_secret")

def generate_signature(payload_bytes: bytes, secret: str) -> str:
    signature = hmac.new(
        key=secret.encode('utf-8'),
        msg=payload_bytes,
        digestmod=hashlib.sha256
    ).hexdigest()
    return f"sha256={signature}"

def send_single_webhook(run_id: str, index: int) -> dict:
    """Generates a unique payload and sends a single webhook, measuring latency."""
    # Ensure a unique message ID and Phone number to bypass idempotency 
    # and safely stress-test database insert locks.
    msg_id = f"wamid.BURST_{run_id}_{index}"
    phone = f"260999{index:04d}" 
    
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"value": {
            "contacts": [{"profile": {"name": f"Burst User {index}"}, "wa_id": phone}],
            "messages": [{
                "from": phone,
                "id": msg_id,
                "timestamp": str(int(time.time())),
                "type": "text",
                "text": {"body": f"Burst message {index}!"}
            }]
        }}]}]
    }

    payload_bytes = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    headers = {
        'Content-Type': 'application/json',
        'x-hub-signature-256': generate_signature(payload_bytes, APP_SECRET)
    }

    start_time = time.perf_counter()
    try:
        response = requests.post(WEBHOOK_URL, data=payload_bytes, headers=headers, timeout=5)
        latency_ms = (time.perf_counter() - start_time) * 1000
        return {
            "status": response.status_code,
            "text": response.text,
            "latency_ms": latency_ms,
            "error": None
        }
    except requests.RequestException as e:
        latency_ms = (time.perf_counter() - start_time) * 1000
        return {
            "status": 500,
            "text": "",
            "latency_ms": latency_ms,
            "error": str(e)
        }

def test_webhook_burst_performance(total_requests=250, max_workers=20):
    run_id = str(int(time.time()))
    
    redis_client.delete(WEBHOOK_QUEUE_NAME)
    initial_q_len = redis_client.llen(WEBHOOK_QUEUE_NAME)
    
    successes = []
    failures = []
    latencies = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(send_single_webhook, run_id, i) for i in range(total_requests)]
        
        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result()
                latencies.append(result["latency_ms"])
                if result["status"] == 200:
                    successes.append(result)
                else:
                    failures.append(result)
            except Exception as exc:
                failures.append({"status": 500, "error": str(exc), "latency_ms": 0})

    assert len(failures) == 0, f"Burst test encountered {len(failures)} failures."

    final_q_len = redis_client.llen(WEBHOOK_QUEUE_NAME)
    expected_growth = len(successes)
    actual_growth = final_q_len - initial_q_len
    
    assert actual_growth == expected_growth, "Queue growth mismatch! Possible race condition or Redis failure."
