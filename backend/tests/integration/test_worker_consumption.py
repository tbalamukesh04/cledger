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
from app.workers.job_handler import process_webhook_batch
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

def test_worker_consumption():
    setup_logging()
    redis_client.delete(WEBHOOK_QUEUE_NAME)
    
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
    
    response = requests.post(WEBHOOK_URL, data=payload_bytes, headers=headers)
    assert response.status_code == 200, f"Webhook failed: {response.text}"
    
    time.sleep(0.5)
    q_len = redis_client.llen(WEBHOOK_QUEUE_NAME)
    assert q_len > 0, "Job did not enter queue!"
    
    result = redis_client.brpop(WEBHOOK_QUEUE_NAME, timeout=5)
    assert result is not None, "Failed to pop job from queue."
        
    _, payload_str = result
    payload_dict = json.loads(payload_str)
    job = WebhookJobPayload(**payload_dict)
    
    result_map = process_webhook_batch([job])
    success = result_map.get(job.job_id) == "success"
    
    assert success is True, "Handler returned False or failed."
