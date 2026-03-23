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
from app.workers.job_handler import process_webhook_batch
from app.config.logging_config import setup_logging
from app.database.database import SessionLocal
from app.models.raw_messages import RawMessages
from app.models.transactions import Transactions

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
    
    response = requests.post(WEBHOOK_URL, data=payload_bytes, headers=headers)
    if response.status_code != 200:
        print(f"❌ Webhook Rejected! Status: {response.status_code}, Body: {response.text}")
        return False
    return True

def run_pipeline_scoring_test():
    setup_logging()
    db = SessionLocal()
    
    print("\n==================================================================")
    print("🚀 E2E PIPELINE & SCORING ENGINE TEST (BATCH PROCESSING)")
    print("==================================================================")
    
    redis_client.delete(WEBHOOK_QUEUE_NAME)
    print("🧹 Cleared Redis queue for a clean test environment.\n")
    
    run_id = str(int(time.time()))
    test_phone = f"26099955{run_id[-3:]}"
    
    # --- Define Test Scenarios ---
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
    
    # 1. Send all webhooks
    print("-> 1. Ingesting Messages via Webhook...")
    for tc in test_cases:
        success = trigger_webhook(test_phone, tc["id"], tc["text"])
        assert success, f"Failed to ingest message: {tc['desc']}"
        time.sleep(0.1)
        
    # 2. Retrieve jobs from Redis to form a batch
    print(f"-> 2. Fetching batch from Redis Queue (Expected: {len(test_cases)} jobs)...")
    time.sleep(1) # Wait for async ingestion
    
    batch_jobs = []
    while True:
        result = redis_client.rpop(WEBHOOK_QUEUE_NAME)
        if not result:
            break
        batch_jobs.append(WebhookJobPayload(**json.loads(result)))
        
    assert len(batch_jobs) == len(test_cases), f"Expected {len(test_cases)} jobs, found {len(batch_jobs)}."
    
    # 3. Process the batch through the worker pipeline
    print(f"-> 3. Executing Worker Pipeline for Batch (Size: {len(batch_jobs)})...")
    print("   [Watch logs for 'scoring_decision' and AI batching output]")
    print("-" * 65)
    
    results = process_webhook_batch(batch_jobs)
    
    print("-" * 65)
    print("-> 4. Validating Database State & Scoring Accuracy...\n")
    
    # 4. Validate results against database
    passed_validations = 0
    for job in batch_jobs:
        # Match job back to our test case data
        raw_msg = db.query(RawMessages).filter(RawMessages.id == job.raw_message_id).first()
        tc = next(t for t in test_cases if t["id"] == raw_msg.message_id)
        
        print(f"Test Case: {tc['desc']}")
        print(f"Message:   '{tc['text']}'")
        
        # Check if transaction was created
        txn = db.query(Transactions).filter(Transactions.raw_message_id == raw_msg.id).first()
        
        if tc["expected_to_pass_scoring"]:
            # Expected to be a transaction
            assert raw_msg.processing_status == "success", f"Failed: Status is {raw_msg.processing_status}"
            assert raw_msg.is_transaction is True, "Failed: is_transaction flag not set."
            assert txn is not None, "Failed: Transaction record was not created by AI."
            print(f"✅ PASSED: Sent to AI and successfully extracted. (Amount: {txn.amount} {txn.currency})")
        else:
            # Expected to be rejected before AI
            assert raw_msg.processing_status == "NON_TRANSACTION", f"Failed: Status is {raw_msg.processing_status}"
            assert raw_msg.is_transaction is False, "Failed: is_transaction flag incorrectly set."
            assert txn is None, "Failed: A transaction record was erroneously created!"
            print(f"✅ PASSED: Accurately identified as Non-Transaction and bypassed AI.")
            
        print("")
        passed_validations += 1

    assert passed_validations == len(test_cases)
    print("🏆 ALL PIPELINE & SCORING VALIDATIONS PASSED SUCCESSFULLY!")
    
    db.close()

if __name__ == "__main__":
    run_pipeline_scoring_test()