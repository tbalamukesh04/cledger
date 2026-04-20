from tests.conftest import mock_redis
import os
import json
import time
import hmac
import hashlib
import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

from app.main import app

client = TestClient(app)

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

def test_webhook_latency(mock_redis):
    mock_redis.incr = MagicMock(return_value=1)
    app.state.redis = mock_redis
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

    start_time = time.perf_counter()
    response = client.post(WEBHOOK_URL, content=payload_bytes, headers=headers)
    end_time = time.perf_counter()

    latency_ms = (end_time - start_time) * 1000

    assert response.status_code == 200, f"Endpoint rejected the payload: {response.text}"
    assert latency_ms < 1000, f"Latency test failed. Processing took {latency_ms:.2f} ms (blocking main thread)."
