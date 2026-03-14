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

def run_preprocessing_test():
    # 1. Initialize structured logging
    setup_logging()
    print("\n--- Starting Worker Preprocessing E2E Test ---")
    
    # 2. Clear the queue to ensure a clean test environment
    redis_client.delete(WEBHOOK_QUEUE_NAME)
    print("🧹 Redis queue cleared.")
    
    # 3. Trigger Webhook Ingestion with "Messy" Text
    run_id = str(int(time.time()))
    test_phone = f"26099900{run_id[-3:]}"
    
    # Notice the messy text: Markdown (*bold*, ~strikethrough~), extra spaces, and irregular newlines
    messy_text = "*Grocery Shopping* \n\n   500.00 ZMW  \r\n ~ignore this~"
    
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"value": {
            "contacts": [{"profile": {"name": "Preprocess Tester"}, "wa_id": test_phone}],
            "messages": [{
                "from": test_phone,
                "id": f"wamid.PREPROCESS_{run_id}",
                "timestamp": str(int(time.time())),
                "type": "text",
                "text": {"body": messy_text}
            }]
        }}]}]
    }
    
    payload_bytes = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    headers = {
        'Content-Type': 'application/json',
        'x-hub-signature-256': generate_signature(payload_bytes, APP_SECRET)
    }
    
    print("\n1. Triggering Webhook Event with messy formatted text...")
    response = requests.post(WEBHOOK_URL, data=payload_bytes, headers=headers)
    if response.status_code != 200:
        print(f"❌ Webhook failed: {response.text}")
        return
    print("✅ Webhook accepted by FastAPI and saved to DB.")
    
    # 4. Confirm job enters Redis queue
    time.sleep(0.5) 
    q_len = redis_client.llen(WEBHOOK_QUEUE_NAME)
    print(f"\n2. Checking Redis Queue...")
    
    if q_len == 0:
        print("❌ Job did not enter queue!")
        return
    print(f"✅ Job found! Current Queue Length: {q_len}")
    
    # 5. Worker Consumes Job
    print("\n3. Simulating Worker Consumption & Preprocessing...")
    result = redis_client.brpop(WEBHOOK_QUEUE_NAME, timeout=5)
    
    if not result:
        print("❌ Failed to pop job from queue.")
        return
        
    _, payload_str = result
    
    try:
        payload_dict = json.loads(payload_str)
        job = WebhookJobPayload(**payload_dict)
        print(f"✅ Job successfully dequeued (Job ID: {job.job_id})")
        
        # 6. Execute Job Handler (This triggers Steps 3-8 of our pipeline)
        print("\n4. Executing Pipeline (Watch for JSON logs below)...\n")
        print("-" * 60)
        
        success = process_webhook_job(job)
        
        print("-" * 60)
        if success:
            print("\n🏆 TEST PASSED: Pipeline successfully retrieved the raw message, normalized the text, mapped the metadata, and logged the result object!")
            print(f"Expected Normalized Output: 'Grocery Shopping\\n\\n500.00 ZMW\\nignore this'")
        else:
            print("\n❌ TEST FAILED: Handler returned False. Check logs for database or processing errors.")
            
    except Exception as e:
        print(f"❌ Worker simulation crashed: {e}")

if __name__ == "__main__":
    run_preprocessing_test()