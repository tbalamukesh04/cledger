import pytest
import hmac
import hashlib
import json
import time
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
APP_SECRET = "dummy_secret_for_testing" # Should match your test environment

def create_whatsapp_payload(phone="1234567890", message="Test"):
    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "12345",
            "changes": [{
                "value": {
                    "messages": [{
                        "from": phone,
                        "id": "wamid.HBgL",
                        "timestamp": str(int(time.time())),
                        "text": {"body": message},
                        "type": "text"
                    }]
                }
            }]
        }]
    }

def sign_payload(payload_bytes, secret):
    return "sha256=" + hmac.new(secret.encode('utf-8'), msg=payload_bytes, digestmod=hashlib.sha256).hexdigest()

def test_missing_webhook_signature():
    payload = create_whatsapp_payload()
    from app.main import app
    from fastapi.testclient import TestClient
    with TestClient(app) as active_client:
        response = active_client.post("/api/v1/webhook", json=payload)
        assert response.status_code in [403, 401]

def test_invalid_webhook_signature():
    payload = create_whatsapp_payload()
    payload_bytes = json.dumps(payload).encode('utf-8')
    headers = {"x-hub-signature-256": "sha256=invalidhash123"}
    
    from app.main import app
    from fastapi.testclient import TestClient
    with TestClient(app) as active_client:
        response = active_client.post("/api/v1/webhook", content=payload_bytes, headers=headers)
        assert response.status_code in [403, 401]

def test_admin_route_protection():
    response = client.get("/api/v1/transactions/review")
    assert response.status_code in [401, 403]
    
def test_metrics_protection():
    response = client.get("/metrics")
    assert response.status_code in [401, 403]

def test_webhook_rate_limiting():
    payload = create_whatsapp_payload()
    payload_bytes = json.dumps(payload).encode('utf-8')
    headers = {"x-hub-signature-256": "sha256=invalidhash123"} # Bypassing auth to just test rate limit
    
    responses = []
    from app.main import app
    from fastapi.testclient import TestClient
    with TestClient(app) as active_client:
        for _ in range(20):
            # We simulate hitting the endpoint rapidly
            resp = active_client.post("/api/v1/webhook", content=payload_bytes, headers=headers)
            responses.append(resp.status_code)
        
    # At least one request should have triggered the 429 Too Many Requests
    assert 429 in responses
