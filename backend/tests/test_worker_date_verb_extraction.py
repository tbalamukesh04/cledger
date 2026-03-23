# backend/tests/test_worker_date_verb_extraction.py
import os
import json
import time
from datetime import datetime, timedelta, timezone
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

def run_date_verb_test_scenario(scenario_name: str, message_text: str, expected_verb: str, expected_date_offset_days: int):
    print(f"\n{'='*70}")
    print(f"🚀 RUNNING SCENARIO: {scenario_name}")
    print(f"📝 Input Text: '{message_text}'")
    print(f"🎯 Expected: Verb = '{expected_verb}', Date Offset = ~{expected_date_offset_days} days")
    print(f"{'='*70}")
    
    # 1. Clear queue for isolated test
    redis_client.delete(WEBHOOK_QUEUE_NAME)
    
    run_id = str(int(time.time()))
    test_phone = f"26099955{run_id[-3:]}"
    current_unix_time = int(time.time())
    
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"value": {
            "contacts": [{"profile": {"name": "Time Tester"}, "wa_id": test_phone}],
            "messages": [{
                "from": test_phone,
                "id": f"wamid.TIME_TEST_{run_id}_{int(time.time() * 1000)}",
                "timestamp": str(current_unix_time),
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
    
    # 4. Process Job (Triggers AI extraction, date/verb normalization, & DB storage)
    print("⏳ Processing job through AI Date & Verb Pipeline...")
    success = process_webhook_job(job)
    
    if not success:
        print("❌ Worker processing failed.")
        return

    # 5. Verify Database Extraction & Normalized Types
    db = SessionLocal()
    try:
        transaction = db.query(Transactions).filter(Transactions.raw_message_id == job.raw_message_id).first()
        
        if transaction:
            actual_verb = transaction.txn_type
            actual_date = transaction.txn_date
            
            print(f"✅ Transaction extracted and stored successfully!")
            print(f"   -> DB Verb: {actual_verb}")
            print(f"   -> DB Date: {actual_date.isoformat()}")
            print(f"   -> AI Raw Output: {json.dumps(transaction.parsing_meta['raw_ai_output'], indent=2)}")
            
            # Assertions
            verb_match = actual_verb == expected_verb
            
            # Check date match (allowing 1 day of flexibility for LLM logic or strict UTC overlap)
            expected_target_date = datetime.now(timezone.utc) + timedelta(days=expected_date_offset_days)
            date_diff_days = abs((actual_date.date() - expected_target_date.date()).days)
            date_match = date_diff_days <= 1
            
            if verb_match and date_match:
                print("🎉 TEST PASSED: Transaction Verb and Date matched expectations!")
            else:
                print("⚠️ TEST FAILED: Extracted values do not match expected bounds.")
                if not verb_match: print(f"   Expected Verb '{expected_verb}', got '{actual_verb}'")
                if not date_match: print(f"   Expected Date ~{expected_target_date.date()}, got {actual_date.date()}")
                
        else:
            print("❌ TEST FAILED: Transaction record was not created in the database.")
    finally:
        db.close()

def run_all_tests():
    setup_logging()
    print("🧹 Initializing Date & Verb Extraction Tests...")

    # Scenario 1: Relative Past + Debit
    run_date_verb_test_scenario(
        scenario_name="Relative Past (Yesterday)",
        message_text="paid him 100 yesterday",
        expected_verb="debit",
        expected_date_offset_days=-1
    )

    # Scenario 2: Explicit Today + Debit
    run_date_verb_test_scenario(
        scenario_name="Explicit Today",
        message_text="transfer 200 completed today",
        expected_verb="debit", # 'transfer' normalizes to debit
        expected_date_offset_days=0
    )

    # Scenario 3: Implied Today + Credit
    run_date_verb_test_scenario(
        scenario_name="Implied Today / Fallback",
        message_text="received the money 300",
        expected_verb="credit", # 'received' normalizes to credit
        expected_date_offset_days=0
    )

    # Scenario 4: Natural Language Offset + Debit
    run_date_verb_test_scenario(
        scenario_name="Natural Language Offset (Last Week)",
        message_text="sent 500 last week",
        expected_verb="debit", # 'sent' normalizes to debit
        expected_date_offset_days=-7
    )

    run_date_verb_test_scenario(
        scenario_name="Invalid Testing",
        message_text="500 needs to be paid for security",
        expected_verb=None, # 'sent' normalizes to debit
        expected_date_offset_days=0
    )
if __name__ == "__main__":
    run_all_tests()