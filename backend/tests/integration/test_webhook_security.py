import os
import hmac
import hashlib
import json
import time
import requests
from dotenv import load_dotenv

# Load environment variables to get the App Secret
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

WEBHOOK_URL = "http://localhost:8000/api/v1/webhook"
APP_SECRET = os.getenv("WHATSAPP_APP_SECRET", os.getenv("WEBHOOK_VERIFY_TOKEN", "dummy_secret_for_testing"))

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

def test_missing_signature_header(security_payload):
    payload_bytes, _ = security_payload
    res = requests.post(WEBHOOK_URL, data=payload_bytes, headers={'Content-Type': 'application/json'})
    assert res.status_code == 403, f"Expected 403, got {res.status_code}"

def test_invalid_signature(security_payload):
    payload_bytes, _ = security_payload
    res = requests.post(
        WEBHOOK_URL, 
        data=payload_bytes, 
        headers={
            'Content-Type': 'application/json',
            'x-hub-signature-256': 'sha256=abcdef1234567890bogussignature'
        }
    )
    assert res.status_code == 403, f"Expected 403, got {res.status_code}"

def test_valid_signature_and_duplicate(security_payload):
    payload_bytes, valid_signature = security_payload
    headers = {
        'Content-Type': 'application/json',
        'x-hub-signature-256': valid_signature
    }
    
    res = requests.post(WEBHOOK_URL, data=payload_bytes, headers=headers)
    assert res.status_code == 200 and res.text == "EVENT_RECEIVED", f"Expected 200 OK EVENT_RECEIVED, got {res.status_code} - {res.text}"

    res_dup = requests.post(WEBHOOK_URL, data=payload_bytes, headers=headers)
    assert res_dup.status_code == 200 and res_dup.text == "DUPLICATE_IGNORED", f"Expected 200 OK DUPLICATE_IGNORED, got {res_dup.status_code} - {res_dup.text}"
