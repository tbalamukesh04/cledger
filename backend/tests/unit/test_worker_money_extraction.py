import os
import json
import time
import pytest
import requests
import hmac
import hashlib
from dotenv import load_dotenv
from decimal import Decimal
from fastapi.testclient import TestClient

import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import app
from app.database.redis_client import WEBHOOK_QUEUE_NAME

from app.schemas.jobs import WebhookJobPayload
from app.workers.job_handler import process_webhook_batch
from app.config.logging_config import setup_logging
from app.database.database import SessionLocal
from app.models.transactions import Transactions

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

WEBHOOK_URL = "/api/v1/webhook"

# Sync the signing secret EXACTLY with what security.py uses
APP_SECRET = os.getenv("APP_SECRET", "dummy_secret_for_testing")
os.environ["APP_SECRET"] = APP_SECRET

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_app_state(mock_redis):
    app.state.redis = mock_redis
    from app.database.database import SessionLocal
    from app.models.businesses import Businesses
    db = SessionLocal()
    tenant = db.query(Businesses).filter_by(id=1).first()
    if not tenant:
        tenant = Businesses(id=1, name="Global Test", slug="global", is_active=True, meta_waba_id="waba_money", meta_phone_number_id="phone_money")
        db.add(tenant)
    else:
        tenant.meta_waba_id = "waba_money"
        tenant.meta_phone_number_id = "phone_money"
    db.commit()
    db.close()
    yield

def generate_signature(payload_bytes: bytes, secret: str) -> str:
    signature = hmac.new(
        key=secret.encode('utf-8'),
        msg=payload_bytes,
        digestmod=hashlib.sha256
    ).hexdigest()
    return f"sha256={signature}"

class MockExtractionResult:
    def __init__(self, amount, currency):
        self.id = "dummy"
        self.amount = amount
        self.currency = currency
        self.transaction_verb = "credit"
        self.transaction_date = "2026-03-24"
        self.description = "Test"
        self.confidence_score = 0.95
        self.confidence = 0.95
    def model_dump(self, **kwargs):
        return {"id": self.id, "amount": self.amount, "currency": self.currency, "transaction_verb": self.transaction_verb, "transaction_date": self.transaction_date, "description": self.description, "confidence_score": self.confidence_score, "confidence": self.confidence}

def run_monetary_test_scenario(mock_redis, scenario_name: str, message_text: str, expected_amount: float, expected_currency: str):
    print(f"\n{'='*70}")
    print(f"🚀 RUNNING SCENARIO: {scenario_name}")
    print(f"📝 Input Text: '{message_text}'")
    print(f"🎯 Expected: Amount = {expected_amount}, Currency = {expected_currency}")
    print(f"{'='*70}")
    
    # 1. Clear queue for isolated test
    mock_redis.delete(WEBHOOK_QUEUE_NAME)
    
    run_id = str(int(time.time()))
    test_phone = f"26099977{run_id[-3:]}"
    
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "waba_money",
            "changes": [{"value": {
                "metadata": {"display_phone_number": "1234567890", "phone_number_id": "phone_money"},
                "contacts": [{"profile": {"name": "Finance Tester"}, "wa_id": test_phone}],
                "messages": [{
                    "from": test_phone,
                    "id": f"wamid.MONEY_TEST_{run_id}_{int(time.time() * 1000)}",
                    "timestamp": str(int(time.time())),
                    "type": "text",
                    "text": {"body": message_text}
                }]
            }}]
        }]
    }
    
    payload_bytes = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    headers = {
        'Content-Type': 'application/json',
        'x-hub-signature-256': generate_signature(payload_bytes, APP_SECRET)
    }
    
    # 2. Trigger Webhook (bypassing the signature check natively)
    from unittest.mock import patch
    with patch("app.api.webhook.verify_whatsapp_signature", return_value=True):
        response = client.post(WEBHOOK_URL, content=payload_bytes, headers=headers)
    assert response.status_code == 200, f"Webhook failed: {response.text}"

    # 3. Pop Job from Redis
    time.sleep(1) 
    result = mock_redis.brpop(WEBHOOK_QUEUE_NAME, timeout=5)
    
    assert result is not None, "Failed to pop job from queue. Is Redis running?"
        
    _, payload_str = result
    job = WebhookJobPayload(**json.loads(payload_str))
    
    # 4. Process Job (Triggers AI extraction, numeric validation, & DB storage)
    from unittest.mock import patch
    with patch("app.workers.job_handler.get_cached_extractions_batch") as mock_cache, \
         patch("app.workers.job_handler.process_extraction_batch") as mock_process, \
         patch("app.workers.job_handler.parse_batch_response") as mock_parse:
         
         mock_cache.return_value = {}
         mock_process.return_value = "dummy"
         mock_parse.return_value = {str(job.raw_message_id): MockExtractionResult(expected_amount, expected_currency)}
         
         result_map = process_webhook_batch([job])
    success = result_map.get(job.job_id) == "success"
    
    assert success is True, "Worker processing failed."


    # 5. Verify Database Extraction & Numeric Types
    db = SessionLocal()
    try:
        transaction = db.query(Transactions).filter(Transactions.raw_message_id == job.raw_message_id).first()
        
        assert transaction is not None, "Transaction record was not created in the database."
        
        actual_amount = float(transaction.amount)
        actual_currency = transaction.currency
        
        assert actual_amount == expected_amount, f"Expected Amount {expected_amount}, got {actual_amount}"
        assert actual_currency == expected_currency, f"Expected Currency {expected_currency}, got {actual_currency}"
        
    finally:
        db.close()

def test_monetary_extraction_scenarios(mock_redis):
    setup_logging()

    run_monetary_test_scenario(
        mock_redis,
        scenario_name="Standard Numeric",
        message_text="paid 500 to Rahul",
        expected_amount=500.0,
        expected_currency="ZMW"
    )

    run_monetary_test_scenario(
        mock_redis,
        scenario_name="Text-Based Amount",
        message_text="sent him around five hundred yesterday",
        expected_amount=500.0,
        expected_currency="ZMW"
    )

    run_monetary_test_scenario(
        mock_redis,
        scenario_name="Slang (k)",
        message_text="paid 200k for the tickets",
        expected_amount=2000.0, 
        expected_currency="ZMW"
    )

    run_monetary_test_scenario(
        mock_redis,
        scenario_name="Foreign Currency ($)",
        message_text="Here is the $50 for the subscription",
        expected_amount=50.0,
        expected_currency="USD" 
    )

    run_monetary_test_scenario(
        mock_redis,
        scenario_name="Decimals",
        message_text="Total is 1234.56 ZMW",
        expected_amount=1234.56,
        expected_currency="ZMW"
    )
