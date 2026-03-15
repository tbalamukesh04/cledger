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
from app.models.raw_messages import RawMessages

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

def trigger_webhook(payload: dict) -> bool:
    payload_bytes = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    headers = {
        'Content-Type': 'application/json',
        'x-hub-signature-256': generate_signature(payload_bytes, APP_SECRET)
    }
    response = requests.post(WEBHOOK_URL, data=payload_bytes, headers=headers)
    
    # 1. Check for standard HTTP errors (like 403 Invalid Signature)
    if response.status_code != 200:
        print(f"❌ WEBHOOK REJECTED! Status: {response.status_code}, Body: {response.text}")
        return False
        
    # 2. NEW: Check for the silent internal FastAPI error!
    if "Error processing event" in response.text:
        print(f"❌ FASTAPI CRASHED INTERNALLY! (Check your uvicorn terminal for the exact SQL/Python error).")
        return False
        
    return True

def get_job_from_queue() -> WebhookJobPayload | None:
    time.sleep(0.5) 
    result = redis_client.brpop(WEBHOOK_QUEUE_NAME, timeout=5)
    if not result:
        return None
    _, payload_str = result
    return WebhookJobPayload(**json.loads(payload_str))

def create_payload(phone: str, msg_id: str, text: str, timestamp: str) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"value": {
            "contacts": [{"profile": {"name": "State Tester"}, "wa_id": phone}],
            "messages": [{
                "from": phone,
                "id": msg_id,
                "type": "text",
                "timestamp": timestamp,
                "text": {"body": text}
            }]
        }}]}]
    }

def run_state_management_tests():
    setup_logging()
    redis_client.delete(WEBHOOK_QUEUE_NAME)
    print("🧹 Redis queue cleared for pristine test environment.\n")
    
    run_id = str(int(time.time()))
    test_phone = f"26099900{run_id[-3:]}"
    fixed_time = str(int(time.time()))
    db = SessionLocal()

    # =====================================================================
    # TEST CASE 1: First-Time Message Processing
    # =====================================================================
    print(f"{'='*60}\n🚀 SCENARIO 1: First-Time Processing Lifecycle\n{'='*60}")
    wamid_1 = f"wamid.STATE_TEST_1_{run_id}"
    payload_1 = create_payload(test_phone, wamid_1, "State Test 1", fixed_time)

    print("-> Sending Webhook...")
    success = trigger_webhook(payload_1)
    assert success is True, "FastAPI rejected the webhook!"
    
    job_1 = get_job_from_queue()
    assert job_1 is not None, "Failed to retrieve job from Redis!"
    
    # Check Pre-Processing State
    msg_before = db.query(RawMessages).filter(RawMessages.id == job_1.raw_message_id).first()
    print(f"-> Pre-Processing State: processed={msg_before.processed}, status='{msg_before.processing_status}'")
    assert msg_before.processed is False
    assert msg_before.processing_status == "pending"
    assert msg_before.processing_started_at is None
    
    print("-> Processing Job...")
    process_webhook_job(job_1)
    
    # Check Post-Processing State
    db.expire_all() # Force refresh from DB
    msg_after = db.query(RawMessages).filter(RawMessages.id == job_1.raw_message_id).first()
    print(f"-> Post-Processing State: processed={msg_after.processed}, status='{msg_after.processing_status}'")
    assert msg_after.processed is True
    assert msg_after.processing_status == "success"
    assert msg_after.processing_started_at is not None
    assert msg_after.processing_completed_at is not None
    print("✅ SCENARIO 1 PASSED: Lifecycle successfully transitioned from 'pending' to 'success'.\n")
    
    original_completed_time = msg_after.processing_completed_at

    # =====================================================================
    # TEST CASE 2: Duplicate Job Retry (Idempotent Guard)
    # =====================================================================
    print(f"{'='*60}\n🚀 SCENARIO 2: Duplicate Job Retry State Integrity\n{'='*60}")
    print("-> Simulating Redis re-delivering the exact same job...")
    
    # Delay slightly to ensure time difference if bug exists
    time.sleep(1) 
    
    print("-> Processing Duplicate Job...")
    success = process_webhook_job(job_1)
    
    db.expire_all()
    msg_duplicate = db.query(RawMessages).filter(RawMessages.id == job_1.raw_message_id).first()
    
    print(f"-> Duplicate Processing State: processed={msg_duplicate.processed}, status='{msg_duplicate.processing_status}'")
    assert success is True # Worker should safely abort and return True to clear queue
    assert msg_duplicate.processing_status == "success" # Should NOT be overwritten to failure or unknown
    assert msg_duplicate.processing_completed_at == original_completed_time # Timestamps must NOT change
    
    print("✅ SCENARIO 2 PASSED: Duplicate run was safely aborted. Original completion state and timestamps remained untouched.\n")

    # =====================================================================
    # TEST CASE 3: Simulated Worker Restart (State Persistence)
    # =====================================================================
    print(f"{'='*60}\n🚀 SCENARIO 3: Worker Restart Persistence\n{'='*60}")
    print("-> Simulating worker shutdown, clearing session...")
    db.close()
    
    print("-> Worker restarting, acquiring new DB session...")
    db_new = SessionLocal()
    
    msg_persisted = db_new.query(RawMessages).filter(RawMessages.id == job_1.raw_message_id).first()
    print(f"-> Verifying database state persisted correctly offline...")
    assert msg_persisted.processed is True
    assert msg_persisted.processing_status == "success"
    
    print("✅ SCENARIO 3 PASSED: State changes are permanently committed to the database and survive session closures.\n")
    db_new.close()

if __name__ == "__main__":
    run_state_management_tests()