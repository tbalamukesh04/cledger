# backend/tests/test_worker_monetary_extraction.py
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
from app.workers.job_handler import process_webhook_job
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
    if response.status_code != 200:
        print(f"❌ Webhook failed: {response.text}")
        return

    # 3. Pop Job from Redis
    time.sleep(1) # Give the webhook a moment to queue
    result = redis_client.brpop(WEBHOOK_QUEUE_NAME, timeout=5)
    
    if not result:
        print("❌ Failed to pop job from queue. Is Redis running?")
        return
        
    _, payload_str = result
    job = WebhookJobPayload(**json.loads(payload_str))
    
    # 4. Process Job (Triggers AI extraction, numeric validation, & DB storage)
    print("⏳ Processing job through AI Monetary Pipeline...")
    success = process_webhook_job(job)
    
    if not success:
        print("❌ Worker processing failed.")
        return

    # 5. Verify Database Extraction & Numeric Types
    db = SessionLocal()
    try:
        transaction = db.query(Transactions).filter(Transactions.raw_message_id == job.raw_message_id).first()
        
        if transaction:
            actual_amount = float(transaction.amount) # Cast Decimal to float for easy comparison
            actual_currency = transaction.currency
            
            print(f"✅ Transaction extracted and stored successfully!")
            print(f"   -> DB Amount: {transaction.amount} (Type: {type(transaction.amount).__name__})")
            print(f"   -> DB Currency: {transaction.currency}")
            print(f"   -> DB Verb: {transaction.txn_type}")
            
            # Assertions
            amount_match = actual_amount == expected_amount
            currency_match = actual_currency == expected_currency
            
            if amount_match and currency_match:
                print("🎉 TEST PASSED: Monetary values match expected perfectly!")
            else:
                print("⚠️ TEST FAILED: Extracted values do not match expected bounds.")
                if not amount_match: print(f"   Expected Amount {expected_amount}, got {actual_amount}")
                if not currency_match: print(f"   Expected Currency {expected_currency}, got {actual_currency}")
                
        else:
            print("❌ TEST FAILED: Transaction record was not created in the database.")
    finally:
        db.close()

def run_all_tests():
    setup_logging()
    print("🧹 Initializing Monetary Extraction Tests...")

    # Scenario 1: Standard numeric amount
    run_monetary_test_scenario(
        scenario_name="Standard Numeric",
        message_text="paid 500 to Rahul",
        expected_amount=500.0,
        expected_currency="ZMW" # Default
    )

    # Scenario 2: Text-based numeric amount
    run_monetary_test_scenario(
        scenario_name="Text-Based Amount",
        message_text="sent him around five hundred yesterday",
        expected_amount=500.0,
        expected_currency="ZMW" # Default
    )

    # Scenario 3: Slang / Shorthand
    run_monetary_test_scenario(
        scenario_name="Slang (k)",
        message_text="paid 200k for the tickets",
        expected_amount=2000.0, 
        expected_currency="ZMW"
    )

    # Scenario 4: Foreign Currency Symbol
    run_monetary_test_scenario(
        scenario_name="Foreign Currency Symbol",
        message_text="transferred ₹1200 today",
        expected_amount=1200.0,
        expected_currency="INR"
    )

if __name__ == "__main__":
    run_all_tests()