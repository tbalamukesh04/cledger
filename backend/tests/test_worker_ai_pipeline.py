# backend/tests/test_worker_ai_pipeline.py
import os
import json
import time
import requests
import hmac
import hashlib
from dotenv import load_dotenv

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

def run_ai_pipeline_scenario(scenario_name: str, message_text: str, expected_type: str):
    print(f"\n{'='*70}")
    print(f"🚀 RUNNING SCENARIO: {scenario_name}")
    print(f"📝 Input Text: '{message_text}'")
    print(f"{'='*70}")
    
    # 1. Clear queue for isolated test
    redis_client.delete(WEBHOOK_QUEUE_NAME)
    
    run_id = str(int(time.time()))
    test_phone = f"26099988{run_id[-3:]}"
    
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"value": {
            "contacts": [{"profile": {"name": "AI Tester"}, "wa_id": test_phone}],
            "messages": [{
                "from": test_phone,
                "id": f"wamid.AI_TEST_{run_id}",
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
    
    # 4. Process Job (This triggers the AI extraction & DB storage)
    print("⏳ Processing job through AI pipeline (waiting for Gemini API)...")
    success = process_webhook_job(job)
    
    if not success:
        print("❌ Worker processing failed.")
        return

    # 5. Verify Database Extraction
    db = SessionLocal()
    try:
        transaction = db.query(Transactions).filter(Transactions.raw_message_id == job.raw_message_id).first()
        
        if expected_type == "non_transaction":
            if not transaction:
                print("✅ TEST PASSED: AI correctly identified this as a non-transaction. No record inserted.")
            else:
                print(f"❌ TEST FAILED: AI hallucinated a transaction! Output: {transaction.amount} {transaction.currency}")
        else:
            if transaction:
                print(f"✅ TEST PASSED: Transaction successfully extracted and stored!")
                print(f"   -> Amount: {transaction.amount}")
                print(f"   -> Currency: {transaction.currency}")
                print(f"   -> Verb: {transaction.txn_type}")
                print(f"   -> Confidence: {transaction.confidence}")
                print(f"   -> Status: {transaction.status}")
                print(f"   -> AI Output Meta: {json.dumps(transaction.parsing_meta['raw_ai_output'], indent=2)}")
            else:
                print("❌ TEST FAILED: Transaction record was not created in the database.")
    finally:
        db.close()

def run_all_tests():
    setup_logging()
    print("🧹 Initializing AI Pipeline Tests...")

    # Scenario 1: Standard Expense (Debit)
    run_ai_pipeline_scenario(
        scenario_name="Standard Expense",
        message_text="Paid 150.50 ZMW for the office supplies yesterday.",
        expected_type="transaction"
    )

    # Scenario 2: Standard Income (Credit)
    run_ai_pipeline_scenario(
        scenario_name="Standard Income",
        message_text="Received $500 from the client for the website design.",
        expected_type="transaction"
    )

    # Scenario 3: Slang / Implicit Currency (K means ZMW)
    run_ai_pipeline_scenario(
        scenario_name="Implicit Currency & Formatting",
        message_text="Just spent 50K on new tires",
        expected_type="transaction"
    )

    # Scenario 4: Non-Transaction Chat (Should be ignored)
    run_ai_pipeline_scenario(
        scenario_name="Non-Transaction Chatter",
        message_text="Hey, what time is the meeting tomorrow?",
        expected_type="non_transaction"
    )

if __name__ == "__main__":
    run_all_tests()