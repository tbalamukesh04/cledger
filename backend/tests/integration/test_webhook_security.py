import os
import hmac
import hashlib
import json
import time
import requests
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_app_state(mock_redis):
    """Ensure app.state.redis exists for both middleware and dependencies during testing."""
    app.state.redis = mock_redis
    yield

WEBHOOK_URL = "/api/v1/webhook"
# Dynamically fetch the EXACT secret the app uses to guarantee signatures match
APP_SECRET = os.getenv("APP_SECRET", "dummy_secret_for_testing")

def generate_signature(payload_bytes: bytes, secret: str) -> str:
    """Generates the HMAC SHA256 signature as Meta does."""
    signature = hmac.new(
        key=secret.encode('utf-8'),
        msg=payload_bytes,
        digestmod=hashlib.sha256
    ).hexdigest()
    return f"sha256={signature}"

import pytest

@pytest.fixture
def security_payload():
    unique_id = f"wamid.SEC_TEST_{int(time.time())}"
    mock_payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "from": "260999999999",
                        "id": unique_id,
                        "timestamp": str(int(time.time())),
                        "type": "text",
                        "text": {"body": "Security test message"}
                    }]
                }
            }]
        }]
    }
    payload_bytes = json.dumps(mock_payload, separators=(',', ':')).encode('utf-8')
    valid_signature = generate_signature(payload_bytes, APP_SECRET)
    return payload_bytes, valid_signature

def test_missing_signature_header(security_payload, mock_redis):
    payload_bytes, _ = security_payload
    res = client.post(WEBHOOK_URL, content=payload_bytes, headers={'Content-Type': 'application/json'})
    assert res.status_code == 403, f"Expected 403, got {res.status_code}"

def test_invalid_signature(security_payload, mock_redis):
    payload_bytes, _ = security_payload
    res = client.post(
        WEBHOOK_URL, 
        content=payload_bytes, 
        headers={
            'Content-Type': 'application/json',
            'x-hub-signature-256': 'sha256=abcdef1234567890bogussignature'
        }
    )
    assert res.status_code == 403, f"Expected 403, got {res.status_code}"

def test_valid_signature_and_duplicate(security_payload, mock_redis, db_session):
    payload_bytes, valid_signature = security_payload
    headers = {
        'Content-Type': 'application/json',
        'x-hub-signature-256': valid_signature
    }
    
    res = client.post(WEBHOOK_URL, content=payload_bytes, headers=headers)
    assert res.status_code == 200 and res.text == "EVENT_RECEIVED", f"Expected 200 OK EVENT_RECEIVED, got {res.status_code} - {res.text}"

    res_dup = client.post(WEBHOOK_URL, content=payload_bytes, headers=headers)
    assert res_dup.status_code == 200 and res_dup.text == "DUPLICATE_IGNORED", f"Expected 200 OK DUPLICATE_IGNORED, got {res_dup.status_code} - {res_dup.text}"