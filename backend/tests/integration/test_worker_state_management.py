import os
import json
import time
import hmac
import hashlib
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_app_state(mock_redis):
    app.state.redis = mock_redis
    from app.database.database import SessionLocal
    from app.models.businesses import Businesses
    db = SessionLocal()
    tenant = db.query(Businesses).filter_by(id=1).first()
    if not tenant:
        tenant = Businesses(id=1, name="Global Test", slug="global", is_active=True, meta_waba_id="waba_state", meta_phone_number_id="phone_state")
        db.add(tenant)
    else:
        tenant.meta_waba_id = "waba_state"
        tenant.meta_phone_number_id = "phone_state"
    db.commit()
    db.close()
    yield

import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database.redis_client import redis_client, WEBHOOK_QUEUE_NAME
from app.schemas.jobs import WebhookJobPayload
from app.workers.job_handler import process_webhook_batch
from app.config.logging_config import setup_logging
from app.database.database import SessionLocal
from app.models.raw_messages import RawMessages

WEBHOOK_URL = "/api/v1/webhook"
APP_SECRET = os.environ.get("WHATSAPP_APP_SECRET", "dummy_secret_for_testing")

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

    # 1. Check for standard HTTP errors (like 403 Invalid Signature)
    if response.status_code != 200:
        print(f"❌ WEBHOOK REJECTED! Status: {response.status_code}, Body: {response.text}")
        return False
        
    # 2. NEW: Check for the silent internal FastAPI error!
    if "Error processing event" in response.text:
        print(f"❌ FASTAPI CRASHED INTERNALLY! (Check your uvicorn terminal for the exact SQL/Python error).")
        return False
        
    return True

def get_job_from_queue(mock_redis_instance) -> WebhookJobPayload | None:
    time.sleep(0.5) 
    result = mock_redis_instance.brpop(WEBHOOK_QUEUE_NAME, timeout=5)
    if not result:
        return None
    _, payload_str = result
    return WebhookJobPayload(**json.loads(payload_str))

def create_payload(phone: str, msg_id: str, text: str, timestamp: str) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "waba_state",
            "changes": [{"value": {
                "metadata": {"display_phone_number": "1234567890", "phone_number_id": "phone_state"},
                "contacts": [{"profile": {"name": "State Tester"}, "wa_id": phone}],
                "messages": [{
                    "from": phone,
                    "id": msg_id,
                    "type": "text",
                    "timestamp": timestamp,
                    "text": {"body": text}
                }]
            }}]
        }]
    }

class MockExtractionResult:
    """A lightweight mock of the Pydantic extraction schema for pipeline testing."""
    def __init__(self, amount, confidence_score):
        self.id = "dummy_id"
        self.amount = amount
        self.currency = "ZMW"
        self.transaction_verb = "credit"
        self.transaction_date = "2026-03-24"
        self.description = "State management test"
        self.confidence_score = confidence_score
        self.confidence = confidence_score

    def model_dump(self, **kwargs):
        return {
            "id": self.id,
            "amount": self.amount,
            "currency": self.currency,
            "transaction_verb": self.transaction_verb,
            "transaction_date": self.transaction_date,
            "description": self.description,
            "confidence_score": self.confidence_score,
            "confidence": self.confidence
        }

@patch("app.workers.job_handler.get_cached_extractions_batch")
@patch("app.workers.job_handler.process_extraction_batch")
@patch("app.workers.job_handler.parse_batch_response")
def test_state_management_lifecycle(mock_parse, mock_process, mock_cache, mock_redis):
    setup_logging()
    
    # Bypass the network
    mock_cache.return_value = {}
    mock_process.return_value = "dummy_llm_response"
    
    mock_redis.delete(WEBHOOK_QUEUE_NAME)
    
    run_id = str(int(time.time()))
    test_phone = f"26099900{run_id[-3:]}"
    fixed_time = str(int(time.time()))
    db = SessionLocal()

    wamid_1 = f"wamid.STATE_TEST_1_{run_id}"
    payload_1 = create_payload(test_phone, wamid_1, "State Test 1", fixed_time)

    success = trigger_webhook(payload_1)
    assert success is True, "FastAPI rejected the webhook!"
    
    job_1 = get_job_from_queue(mock_redis)
    assert job_1 is not None, "Failed to retrieve job from Redis!"
    
    msg_before = db.query(RawMessages).filter(RawMessages.id == job_1.raw_message_id).first()
    assert msg_before.processed is False
    assert msg_before.processing_status == "pending"
    assert msg_before.processing_started_at is None
    
    # Inject the mock response mapped to the job's raw_message_id with a high confidence score
    mock_parse.return_value = {str(job_1.raw_message_id): MockExtractionResult(amount=500.0, confidence_score=0.95)}

        # 1. First Run (Processing the message)
    process_webhook_batch([job_1])
    
    db.expire_all()
    msg_after = db.query(RawMessages).filter(RawMessages.id == job_1.raw_message_id).first()
    assert msg_after.processed is True
    assert msg_after.processing_status == "success"
    assert msg_after.processing_started_at is not None
    assert msg_after.processing_completed_at is not None
    
    original_completed_time = msg_after.processing_completed_at

    time.sleep(1) 
    
    # 2. Second Run (Duplicate check)
    result_map = process_webhook_batch([job_1])
    success = result_map.get(job_1.job_id) == "success"
    
    db.expire_all()
    msg_duplicate = db.query(RawMessages).filter(RawMessages.id == job_1.raw_message_id).first()
    
    assert success is True
    assert msg_duplicate.processing_status == "success"
    assert msg_duplicate.processing_completed_at == original_completed_time

    db.close()
    db_new = SessionLocal()
    
    msg_persisted = db_new.query(RawMessages).filter(RawMessages.id == job_1.raw_message_id).first()
    assert msg_persisted.processed is True
    assert msg_persisted.processing_status == "success"
    
    db_new.close()
