import os
import json
import time
import requests
import hmac
import hashlib
from dotenv import load_dotenv
from decimal import Decimal

import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database.redis_client import redis_client, WEBHOOK_QUEUE_NAME
from app.schemas.jobs import WebhookJobPayload
from app.workers.job_handler import process_webhook_batch
from app.config.logging_config import setup_logging
from app.database.database import SessionLocal
from app.models.transactions import Transactions

# Load environment variables
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

def run_monetary_test_scenario(scenario_name: str, message_text: str, expected_amount: float, expected_currency: str):
    print(f"\n{'='*70}")
    print(f"🚀 RUNNING SCENARIO: {scenario_name}")
    print(f"📝 Input Text: '{message_text}'")
    print(f"🎯 Expected: Amount = {expected_amount}, Currency = {expected_currency}")
    print(f"{'='*70}")
    
    # 1. Clear queue for isolated test
    redis_client.delete(WEBHOOK_QUEUE_NAME)
    
    run_id = str(int(time.time()))
    test_phone = f"26099977{run_id[-3:]}"
    
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"value": {
            "contacts": [{"profile": {"name": "Finance Tester"}, "wa_id": test_phone}],
            "messages": [{
                "from": test_phone,
                "id": f"wamid.MONEY_TEST_{run_id}_{int(time.time() * 1000)}",
                "timestamp": str(int(time.time())),
                "type": "text",
                "text": {"body": message_text}
            }]
        }}]}]
    }
    
    payload_bytes = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    headers = {
        'Content-Type': 'application/json',
        'x-hub-signature-256': generate_signature(payload_bytes, APP_SECRET)
    }
    
    # 2. Trigger Webhook
    response = requests.post(WEBHOOK_URL, data=payload_bytes, headers=headers)
    assert response.status_code == 200, f"Webhook failed: {response.text}"

    # 3. Pop Job from Redis
    time.sleep(1) 
    result = redis_client.brpop(WEBHOOK_QUEUE_NAME, timeout=5)
    
    assert result is not None, "Failed to pop job from queue. Is Redis running?"
        
    _, payload_str = result
    job = WebhookJobPayload(**json.loads(payload_str))
    
    # 4. Process Job (Triggers AI extraction, numeric validation, & DB storage)
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

def test_monetary_extraction_scenarios():
    setup_logging()

    run_monetary_test_scenario(
        scenario_name="Standard Numeric",
        message_text="paid 500 to Rahul",
        expected_amount=500.0,
        expected_currency="ZMW"
    )

    run_monetary_test_scenario(
        scenario_name="Text-Based Amount",
        message_text="sent him around five hundred yesterday",
        expected_amount=500.0,
        expected_currency="ZMW"
    )

    run_monetary_test_scenario(
        scenario_name="Slang (k)",
        message_text="paid 200k for the tickets",
        expected_amount=2000.0, 
        expected_currency="ZMW"
    )

    run_monetary_test_scenario(
        scenario_name="Foreign Currency ($)",
        message_text="Here is the $50 for the subscription",
        expected_amount=50.0,
        expected_currency="USD" 
    )

    run_monetary_test_scenario(
        scenario_name="Decimals",
        message_text="Total is 1234.56 ZMW",
        expected_amount=1234.56,
        expected_currency="ZMW"
    )
