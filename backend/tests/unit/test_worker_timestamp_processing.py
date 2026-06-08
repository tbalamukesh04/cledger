# backend/tests/test_worker_timestamp_processing.py
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

def run_scenario(scenario_name: str, timestamp_val: str | None, phone_suffix: str):
    print(f"\n{'='*60}")
    print(f"🚀 RUNNING SCENARIO: {scenario_name}")
    print(f"{'='*60}")
    
    test_phone = f"26099911{phone_suffix}"
    
    # Base message structure
    message_obj = {
        "from": test_phone,
        "id": f"wamid.TIME_TEST_{phone_suffix}_{int(time.time())}",
        "type": "text",
        "text": {"body": f"Testing scenario: {scenario_name}"}
    }
    
    # Inject specific timestamp based on scenario
    if timestamp_val is not None:
        message_obj["timestamp"] = timestamp_val

    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"value": {
            "contacts": [{"profile": {"name": f"Tester {phone_suffix}"}, "wa_id": test_phone}],
            "messages": [message_obj]
        }}]}]
    }
    
    payload_bytes = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    headers = {
        'Content-Type': 'application/json',
        'x-hub-signature-256': generate_signature(payload_bytes, APP_SECRET)
    }
    
    # 1. Ingest via Webhook
    response = requests.post(WEBHOOK_URL, data=payload_bytes, headers=headers)
    if response.status_code != 200:
        print(f"❌ Webhook failed: {response.text}")
        return

    # 2. Dequeue from Redis
    time.sleep(0.5)
    result = redis_client.brpop(WEBHOOK_QUEUE_NAME, timeout=5)
    if not result:
        print("❌ Failed to pop job from queue.")
        return
        
    _, payload_str = result
    
    # 3. Process Job
    try:
        job = WebhookJobPayload(**json.loads(payload_str))
        print(f"✅ Job dequeued. Executing Pipeline...\n")
        
        result_map = process_webhook_batch([job])
        success = result_map.get(job.job_id) == "success"
        
        if success:
            print(f"\n🏆 SCENARIO PASSED: Check logs above to verify fallback behavior and metadata extraction.")
        else:
            print(f"\n❌ SCENARIO FAILED: Handler returned False.")
            
    except Exception as e:
        print(f"❌ Worker simulation crashed: {e}")

def run_all_tests():
    setup_logging()
    redis_client.delete(WEBHOOK_QUEUE_NAME)
    print("🧹 Redis queue cleared for pristine test environment.")
    
    current_time = int(time.time())
    
    # Scenario 1: Valid Timestamp (Normal operating conditions)
    run_scenario(
        scenario_name="Valid Timestamp",
        timestamp_val=str(current_time),
        phone_suffix="001"
    )
    
    # Scenario 2: Malformed Timestamp (String that can't be parsed to int)
    run_scenario(
        scenario_name="Malformed Timestamp",
        timestamp_val="not_a_valid_time",
        phone_suffix="002"
    )
    
    # Scenario 3: Missing Timestamp (Field entirely omitted from Meta payload)
    run_scenario(
        scenario_name="Missing Timestamp",
        timestamp_val=None,
        phone_suffix="003"
    )
    
    # Scenario 4: Future Timestamp (1 hour in the future, triggering validation bounds)
    future_time = current_time + 3600
    run_scenario(
        scenario_name="Future Timestamp",
        timestamp_val=str(future_time),
        phone_suffix="004"
    )

if __name__ == "__main__":
    run_all_tests()
    