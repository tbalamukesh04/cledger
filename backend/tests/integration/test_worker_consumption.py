import os
import json
import time
import pytest
import hmac
import hashlib
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_app_state(mock_redis):
    app.state.redis = mock_redis
    yield

# Ensure we can import from the app module
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database.redis_client import redis_client, WEBHOOK_QUEUE_NAME
from app.schemas.jobs import WebhookJobPayload
from app.workers.job_handler import process_webhook_batch
from app.config.logging_config import setup_logging

WEBHOOK_URL = "/api/v1/webhook"
APP_SECRET = os.environ.get("WHATSAPP_APP_SECRET", "dummy_secret_for_testing")

def generate_signature(payload_bytes: bytes, secret: str) -> str:
    signature = hmac.new(
        key=secret.encode('utf-8'),
        msg=payload_bytes,
        digestmod=hashlib.sha256
    ).hexdigest()
    return f"sha256={signature}"

def test_worker_consumption(mock_redis):
    setup_logging()
    mock_redis.delete(WEBHOOK_QUEUE_NAME)
    
    run_id = str(int(time.time()))
    test_phone = f"26099900{run_id[-3:]}"
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"value": {
            "contacts": [{"profile": {"name": "Worker E2E Tester"}, "wa_id": test_phone}],
            "messages": [{
                "from": test_phone,
                "id": f"wamid.WORKER_TEST_{run_id}",
                "timestamp": str(int(time.time())),
                "type": "text",
                "text": {"body": "Test message for the background worker!"}
            }]
        }}]}]
    }
    
    payload_bytes = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    headers = {
        'Content-Type': 'application/json',
        'x-hub-signature-256': generate_signature(payload_bytes, APP_SECRET)
    }
    
    response = client.post(WEBHOOK_URL, content=payload_bytes, headers=headers)
    assert response.status_code == 200, f"Webhook failed: {response.text}"
    
    time.sleep(0.5)
    q_len = mock_redis.llen(WEBHOOK_QUEUE_NAME)
    assert q_len > 0, "Job did not enter queue!"
    
    result = mock_redis.brpop(WEBHOOK_QUEUE_NAME, timeout=5)
    assert result is not None, "Failed to pop job from queue."
        
    _, payload_str = result
    payload_dict = json.loads(payload_str)
    job = WebhookJobPayload(**payload_dict)
    
    result_map = process_webhook_batch([job])
    success = result_map.get(job.job_id) == "success"
    
    assert success is True, "Handler returned False or failed."
