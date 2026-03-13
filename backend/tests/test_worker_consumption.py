import os
import json
import time
import requests
import hmac
import hashlib
from dotenv import load_dotenv

# Ensure we can import from the app module
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database.redis_client import redis_client, WEBHOOK_QUEUE_NAME
from app.schemas.jobs import WebhookJobPayload
from app.workers.job_handler import process_webhook_job
from app.config.logging_config import setup_logging

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

def run_consumption_test():
    # Initialize standard worker logging so we can see the handler's output
    setup_logging()
    
    print("\n--- Starting Worker Consumption E2E Test ---")
    
    # 1. Clear the queue to ensure a clean test environment
    redis_client.delete(WEBHOOK_QUEUE_NAME)
    print("🧹 Queue cleared.")
    
    # 2. Trigger webhook event
    run_id = str(int(time.time()))
    test_phone = f"26099900{run_id[-3:]}"
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"value": {
            "contacts": [{"profile": {"name": "Worker E2E Tester"}, "wa_id": test_phone}],
            "messages": [{
                "from": test_phone,
                "id": f"wamid.WORKER_TEST_{run_id}",
                "timestamp": str(int(time.time())),
                "type": "text",
                "text": {"body": "Test message for the background worker!"}
            }]
        }}]}]
    }
    
    payload_bytes = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    headers = {
        'Content-Type': 'application/json',
        'x-hub-signature-256': generate_signature(payload_bytes, APP_SECRET)
    }
    
    print("\n1. Triggering Webhook Event...")
    response = requests.post(WEBHOOK_URL, data=payload_bytes, headers=headers)
    if response.status_code != 200:
        print(f"❌ Webhook failed: {response.text}")
        return
    print("✅ Webhook accepted by FastAPI.")
    
    # 3. Confirm job enters Redis queue
    time.sleep(0.5) # Brief pause to allow async webhook to enqueue
    q_len = redis_client.llen(WEBHOOK_QUEUE_NAME)
    print(f"\n2. Checking Redis Queue...")
    
    if q_len == 0:
        print("❌ Job did not enter queue!")
        return
    print(f"✅ Job found! Current Queue Length: {q_len}")
    
    # 4. Simulate Worker Consumption (Popping the job)
    print("\n3. Simulating Worker Consumption...")
    result = redis_client.brpop(WEBHOOK_QUEUE_NAME, timeout=5)
    
    if not result:
        print("❌ Failed to pop job from queue.")
        return
        
    _, payload_str = result
    
    try:
        # Deserialization test
        payload_dict = json.loads(payload_str)
        job = WebhookJobPayload(**payload_dict)
        print(f"✅ Job successfully dequeued and deserialized (Job ID: {job.job_id})")
        
        # 5. Verify Job Handler Execution
        print("\n4. Executing Job Handler (Watch for JSON logs below)...\n")
        
        success = process_webhook_job(job)
        
        print("\n--------------------------------------------------")
        if success:
            print("🏆 TEST PASSED: Job successfully consumed, processed, and DB record fetched!")
        else:
            print("❌ TEST FAILED: Handler returned False. Check logs for database errors.")
            
    except Exception as e:
        print(f"❌ Worker simulation crashed: {e}")

if __name__ == "__main__":
    run_consumption_test()