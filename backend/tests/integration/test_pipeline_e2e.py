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
    yield

import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database.redis_client import redis_client, WEBHOOK_QUEUE_NAME
from app.schemas.jobs import WebhookJobPayload
from app.workers.job_handler import process_webhook_batch
from app.config.logging_config import setup_logging
from app.database.database import SessionLocal
from app.models.raw_messages import RawMessages
from app.models.transactions import Transactions

WEBHOOK_URL = "/api/v1/webhook"
APP_SECRET = os.environ.get("WHATSAPP_APP_SECRET", "dummy_secret_for_testing")

WEBHOOK_URL = "/api/v1/webhook"
APP_SECRET = os.environ.get("WHATSAPP_APP_SECRET", "dummy_secret_for_testing")

class MockExtractionResult:
    def __init__(self, msg_id):
        self.id = msg_id
        self.amount = 500.0
        self.currency = "ZMW"
        self.transaction_verb = "credit"
        self.transaction_date = "2026-03-24"
        self.description = "E2E pipeline test"
        self.confidence_score = 0.95
        self.confidence = 0.95

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

def generate_signature(payload_bytes: bytes, secret: str) -> str:
    signature = hmac.new(
        key=secret.encode('utf-8'),
        msg=payload_bytes,
        digestmod=hashlib.sha256
    ).hexdigest()
    return f"sha256={signature}"

def trigger_webhook(phone: str, msg_id: str, text: str) -> bool:
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"value": {
            "contacts": [{"profile": {"name": "Pipeline Tester"}, "wa_id": phone}],
            "messages": [{
                "from": phone,
                "id": msg_id,
                "type": "text",
                "timestamp": str(int(time.time())),
                "text": {"body": text}
            }]
        }}]}]
    }
    
    payload_bytes = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    headers = {
        'Content-Type': 'application/json',
        'x-hub-signature-256': generate_signature(payload_bytes, APP_SECRET)
    }
    
    response = client.post(WEBHOOK_URL, content=payload_bytes, headers=headers)
    if response.status_code != 200:
        print(f"❌ Webhook Rejected! Status: {response.status_code}, Body: {response.text}")
        return False
    return True

@patch("app.workers.job_handler.get_cached_extractions_batch")
@patch("app.workers.job_handler.process_extraction_batch")
@patch("app.workers.job_handler.parse_batch_response")
def test_pipeline_scoring_e2e(mock_parse, mock_process, mock_cache, mock_redis):
    setup_logging()
    db = SessionLocal()
    
    # Bypass the network
    mock_cache.return_value = {}
    mock_process.return_value = "dummy_llm_response"
    
    def mock_parse_side_effect(raw_resp, candidate_ids, batch_id):
        return {str(cid): MockExtractionResult(cid) for cid in candidate_ids}
    mock_parse.side_effect = mock_parse_side_effect
    
    mock_redis.delete(WEBHOOK_QUEUE_NAME)
    run_id = str(int(time.time()))
    test_phone = f"26099955{run_id[-3:]}"
    
    test_cases = [
        {
            "id": f"wamid.TXN_1_{run_id}",
            "text": "I paid John 500 ZMW for the groceries today.",
            "expected_to_pass_scoring": True,
            "desc": "Clear Transaction (Amount, Currency, Verb)"
        },
        {
            "id": f"wamid.RANDOM_1_{run_id}",
            "text": "Hey man, what time are we meeting tomorrow for the game?",
            "expected_to_pass_scoring": False,
            "desc": "Random Convo (No financial signals)"
        },
        {
            "id": f"wamid.RANDOM_2_{run_id}",
            "text": "How much should I pay you for the tickets?",
            "expected_to_pass_scoring": False,
            "desc": "Negative Context (Has 'pay', but asks 'how much')"
        },
        {
            "id": f"wamid.TXN_2_{run_id}",
            "text": "Received 100K from Alice.",
            "expected_to_pass_scoring": True,
            "desc": "Short Transaction (Verb, Amount, Currency shorthand)"
        }
    ]
    
    for tc in test_cases:
        success = trigger_webhook(test_phone, tc["id"], tc["text"])
        assert success, f"Failed to ingest message: {tc['desc']}"
        time.sleep(0.1)
        
    time.sleep(1) 
    
    batch_jobs = []
    while True:
        result = mock_redis.rpop(WEBHOOK_QUEUE_NAME)
        if not result:
            break
        batch_jobs.append(WebhookJobPayload(**json.loads(result)))
        
    assert len(batch_jobs) == len(test_cases), f"Expected {len(test_cases)} jobs, found {len(batch_jobs)}."
    
    process_webhook_batch(batch_jobs)
    
    for job in batch_jobs:
        raw_msg = db.query(RawMessages).filter(RawMessages.id == job.raw_message_id).first()
        tc = next(t for t in test_cases if t["id"] == raw_msg.message_id)
        
        txn = db.query(Transactions).filter(Transactions.raw_message_id == raw_msg.id).first()
        
        if tc["expected_to_pass_scoring"]:
            assert raw_msg.processing_status == "success", f"Failed: Status is {raw_msg.processing_status}"
            assert raw_msg.is_transaction is True, "Failed: is_transaction flag not set."
            assert txn is not None, "Failed: Transaction record was not created by AI."
        else:
            assert raw_msg.processing_status == "NON_TRANSACTION", f"Failed: Status is {raw_msg.processing_status}"
            assert raw_msg.is_transaction is False, "Failed: is_transaction flag incorrectly set."
            assert txn is None, "Failed: A transaction record was erroneously created!"

    db.close()
