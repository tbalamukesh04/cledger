import os
import json
import time
import hmac
import hashlib
import concurrent.futures
import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

from app.main import app
from app.database.redis_client import WEBHOOK_QUEUE_NAME

client = TestClient(app)

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

WEBHOOK_URL = "/api/v1/webhook"
APP_SECRET = os.getenv("APP_SECRET", "dummy_secret_for_testing")

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
        response = client.post(WEBHOOK_URL, content=payload_bytes, headers=headers)
        latency_ms = (time.perf_counter() - start_time) * 1000
        return {
            "status": response.status_code,
            "text": response.text,
            "latency_ms": latency_ms,
            "error": None
        }
    except Exception as e:
        latency_ms = (time.perf_counter() - start_time) * 1000
        return {
            "status": 500,
            "text": "",
            "latency_ms": latency_ms,
            "error": str(e)
        }

def test_webhook_burst_performance(mock_redis):
    mock_redis.incr = MagicMock(return_value=1)
    app.state.redis = mock_redis

    total_requests = 250
    max_workers = 20
    run_id = str(int(time.time()))
    
    mock_redis.delete(WEBHOOK_QUEUE_NAME)
    initial_q_len = mock_redis.llen(WEBHOOK_QUEUE_NAME)
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

    final_q_len = mock_redis.llen(WEBHOOK_QUEUE_NAME)
    expected_growth = len(successes)
    actual_growth = final_q_len - initial_q_len
    
    assert actual_growth == expected_growth, "Queue growth mismatch! Possible race condition or Redis failure."
