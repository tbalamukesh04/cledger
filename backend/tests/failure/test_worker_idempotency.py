import os
import json
import time
import hmac
import hashlib
import pytest
from fastapi.testclient import TestClient

import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import app
from app.database.redis_client import WEBHOOK_QUEUE_NAME
from app.schemas.jobs import WebhookJobPayload
from app.workers.job_handler import process_webhook_batch
from app.config.logging_config import setup_logging
from app.database.database import SessionLocal
from app.models.raw_messages import RawMessages

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_app_state(mock_redis):
    app.state.redis = mock_redis
    yield

WEBHOOK_URL = "/api/v1/webhook"
APP_SECRET = os.getenv("APP_SECRET", "dummy_secret_for_testing")

def generate_signature(payload_bytes: bytes, secret: str) -> str:
    signature = hmac.new(
        key=secret.encode('utf-8'),
        msg=payload_bytes,
        digestmod=hashlib.sha256
    ).hexdigest()
    return f"sha256={signature}"

def trigger_webhook(payload: dict) -> bool:
    payload_bytes = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    headers = {
        'Content-Type': 'application/json',
        'x-hub-signature-256': generate_signature(payload_bytes, APP_SECRET)
    }
    response = client.post(WEBHOOK_URL, content=payload_bytes, headers=headers)
    
    if response.status_code != 200:
        print(f"❌ WEBHOOK REJECTED! Status: {response.status_code}, Body: {response.text}")
        return False
        
    if "Error processing event" in response.text:
        print(f"❌ FASTAPI CRASHED INTERNALLY!")
        return False
        
    return True

def get_job_from_queue(mock_redis) -> WebhookJobPayload | None:
    # Use a non-blocking polling loop to avoid socket TimeoutErrors
    for _ in range(10):
        time.sleep(0.1)
        result = mock_redis.rpop(WEBHOOK_QUEUE_NAME)
        if result:
            return WebhookJobPayload(**json.loads(result))
    return None

def create_payload(phone: str, msg_id: str | None, text: str, timestamp: str) -> dict:
    msg_obj = {
        "from": phone,
        "type": "text",
        "timestamp": timestamp,
        "text": {"body": text}
    }
    if msg_id:
        msg_obj["id"] = msg_id

    return {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"value": {
            "contacts": [{"profile": {"name": "Idemp Tester"}, "wa_id": phone}],
            "messages": [msg_obj]
        }}]}]
    }

def test_exact_wamid_duplicate(mock_redis):
    setup_logging()
    mock_redis.delete(WEBHOOK_QUEUE_NAME)
    
    run_id = str(int(time.time()))
    test_phone = f"26099900{run_id[-3:]}"
    fixed_time = str(int(time.time()))

    wamid = f"wamid.IDEMP_TEST_1_{run_id}"
    payload_1 = create_payload(test_phone, wamid, "Test WAMID Dup", fixed_time)

    success = trigger_webhook(payload_1)
    assert success is True, "FastAPI rejected the initial webhook!"
    
    job_1a = get_job_from_queue(mock_redis)
    assert job_1a is not None, "Failed to retrieve job from Redis!"
    
    process_webhook_batch([job_1a])
    
    db = SessionLocal()
    db.query(RawMessages).filter(RawMessages.id == job_1a.raw_message_id).update({"processed": True})
    db.commit()
    db.close()

    trigger_webhook(payload_1)
    job_1b = get_job_from_queue(mock_redis)
    
    assert job_1b is None, "Webhook Router failed to block duplicate WAMID."

def test_content_hash_duplicate(mock_redis):
    setup_logging()
    mock_redis.delete(WEBHOOK_QUEUE_NAME)
    
    run_id = str(int(time.time()))
    test_phone = f"26099900{run_id[-3:]}"
    fixed_time = str(int(time.time()))

    payload_2 = create_payload(test_phone, None, "Test Hash Dup", fixed_time)

    success = trigger_webhook(payload_2)
    assert success is True, "FastAPI rejected the webhook!"
    
    job_2a = get_job_from_queue(mock_redis)
    assert job_2a is not None, "Failed to retrieve job from Redis!"
    
    process_webhook_batch([job_2a])
    
    db = SessionLocal()
    db.query(RawMessages).filter(RawMessages.id == job_2a.raw_message_id).update({"processed": True})
    db.commit()
    db.close()

    payload_2b = create_payload(test_phone, None, "Test Hash Dup", fixed_time)
    payload_2b["entry"][0]["changes"][0]["value"]["contacts"][0]["profile"]["name"] = "Sneaky Duplicate"
    
    trigger_webhook(payload_2b)
    job_2b = get_job_from_queue(mock_redis)
    
    if job_2b:
        result_map = process_webhook_batch([job_2b])
        # The DB unique constraint safely catches the duplicate content hash and triggers a retry/failure
        assert result_map.get(job_2b.job_id) in ["retry", "failed"], "Worker did not safely abort hash duplicate."

def test_worker_job_retry(mock_redis):
    setup_logging()
    mock_redis.delete(WEBHOOK_QUEUE_NAME)
    
    run_id = str(int(time.time()))
    test_phone = f"26099900{run_id[-3:]}"
    fixed_time = str(int(time.time()))

    wamid_3 = f"wamid.RETRY_TEST_{run_id}"
    payload_3 = create_payload(test_phone, wamid_3, "Test Retry", fixed_time)

    success = trigger_webhook(payload_3)
    assert success is True, "FastAPI rejected the webhook!"
    
    job_3 = get_job_from_queue(mock_redis)
    assert job_3 is not None, "Failed to retrieve job from Redis!"
    
    db = SessionLocal()
    db.query(RawMessages).filter(RawMessages.id == job_3.raw_message_id).update({"processed": True})
    db.commit()
    db.close()

    result_map = process_webhook_batch([job_3])
    assert result_map.get(job_3.job_id) == "success", "Worker failed to gracefully handle previously processed job."
