from tests.conftest import mock_redis
import os
import json
import time
import pytest
import requests
import hmac
import hashlib
from dotenv import load_dotenv
from fastapi.testclient import TestClient

import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import app
from app.database.redis_client import WEBHOOK_QUEUE_NAME

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_app_state(mock_redis):
    app.state.redis = mock_redis
    from app.database.database import SessionLocal
    from app.models.businesses import Businesses
    db = SessionLocal()
    tenant = db.query(Businesses).filter_by(id=1).first()
    if not tenant:
        tenant = Businesses(id=1, name="Global Test", slug="global", is_active=True, meta_waba_id="waba_preproc", meta_phone_number_id="phone_preproc")
        db.add(tenant)
    else:
        tenant.meta_waba_id = "waba_preproc"
        tenant.meta_phone_number_id = "phone_preproc"
    db.commit()
    db.close()
    yield

from app.schemas.jobs import WebhookJobPayload
from app.workers.job_handler import process_webhook_batch
from app.config.logging_config import setup_logging

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

WEBHOOK_URL = "/api/v1/webhook"

# Sync the signing secret EXACTLY with what security.py uses
APP_SECRET = os.getenv("APP_SECRET", "dummy_secret_for_testing")
os.environ["APP_SECRET"] = APP_SECRET

def generate_signature(payload_bytes: bytes, secret: str) -> str:
    signature = hmac.new(
        key=secret.encode('utf-8'),
        msg=payload_bytes,
        digestmod=hashlib.sha256
    ).hexdigest()
    return f"sha256={signature}"

def test_worker_preprocessing(mock_redis):
    setup_logging()
    mock_redis.delete(WEBHOOK_QUEUE_NAME)
    
    run_id = str(int(time.time()))
    test_phone = f"26099900{run_id[-3:]}"
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "waba_preproc",
            "changes": [{"value": {
                "metadata": {"display_phone_number": "1234567890", "phone_number_id": "phone_preproc"},
                "contacts": [{"profile": {"name": "Worker Preprocessing Tester"}, "wa_id": test_phone}],
                "messages": [{
                    "from": test_phone,
                    "id": f"wamid.PREPROC_TEST_{run_id}",
                    "timestamp": str(int(time.time())),
                    "type": "text",
                    "text": {"body": "   Grocery Shopping\n\n500.00 ZMW\nignore this   "}
                }]
            }}]
        }]
    }
    
    payload_bytes = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    headers = {
        'Content-Type': 'application/json',
        'x-hub-signature-256': generate_signature(payload_bytes, APP_SECRET)
    }
    
    from unittest.mock import patch
    with patch("app.api.webhook.verify_whatsapp_signature", return_value=True):
        response = client.post(WEBHOOK_URL, content=payload_bytes, headers=headers)
    assert response.status_code == 200, f"Webhook failed: {response.text}"
    time.sleep(0.5)
    q_len = mock_redis.llen(WEBHOOK_QUEUE_NAME)
    assert q_len > 0, "Job did not enter queue!"
    
    result = mock_redis.brpop(WEBHOOK_QUEUE_NAME, timeout=5)
    assert result is not None, "Failed to pop job from queue."
        
    _, payload_str = result
    
    payload_dict = json.loads(payload_str)
    job = WebhookJobPayload(**payload_dict)
    
    result_map = process_webhook_batch([job])
    success = result_map.get(job.job_id) == "success"
    
    assert success is True, "Handler returned False. Pipeline preprocessing failed."
