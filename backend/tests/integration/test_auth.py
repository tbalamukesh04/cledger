import pytest
import datetime
from unittest.mock import patch
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.main import app
from app.core.jwt_utils import create_access_token, verify_jwt_token

client = TestClient(app)

def test_valid_token_decoding():
    """Verify that a freshly created token decodes correctly."""
    token = create_access_token(user_id="abc123", tenant_id=1, role="admin")
    payload = verify_jwt_token(token)
    
    assert payload["user_id"] == "abc123"
    assert payload["role"] == "admin"
    assert "exp" in payload

def test_expired_token_raises_exception():
    """Verify that an expired token correctly raises an HTTPException."""
    token = create_access_token(
        user_id="abc123", 
        tenant_id=1,
        expires_delta=datetime.timedelta(minutes=-1)
    )
    
    with pytest.raises(HTTPException) as exc_info:
        verify_jwt_token(token)
    
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Token expired"

def test_invalid_token_raises_exception():
    """Verify that a malformed or randomly generated string fails validation."""
    invalid_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.invalid.signature"
    
    with pytest.raises(HTTPException) as exc_info:
        verify_jwt_token(invalid_token)
    
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid token"

def test_scenario_1_access_without_token():
    """Scenario 1: Verify that a protected endpoint returns 401 when no token is provided."""
    response = client.get("/api/v1/transactions/health")
    assert response.status_code == 401, response.text
    assert "Not authenticated" in response.text

def test_scenario_2_access_with_invalid_token():
    """Scenario 2: Verify that an invalid token is rejected with 401 Unauthorized."""
    headers = {"Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.invalid.signature"}
    response = client.get("/api/v1/transactions/health", headers=headers)
    assert response.status_code == 401, response.text
    assert "Invalid token" in response.text

# ==============================================================================
# AUTH0 MULTI-TENANT ONBOARDING & IDEMPOTENCY TEST HARNESS SUITE (DAY 99)
# ==============================================================================

@patch("app.api.auth.verify_jwt_token")
def test_auth0_first_time_onboarding_flow(mock_verify):
    """
    Verify that an unrecognized valid Auth0 OIDC Organization token trigger 
    correctly and transactionally maps business tenant and application user entities.
    """
    mock_verify.return_value = {
        "sub": "auth0|test_user_99",
        "org_id": "org_acme_99",
        "org_name": "Acme Ventures",
        "email": "admin@acmeventures.com",
        "name": "Tejas Srinivasan",
        "role": "admin"
    }
    
    headers = {"Authorization": "Bearer mock-auth0-rs256-jwt-token"}
    response = client.post("/api/v1/auth/onboard", json={"additional_metadata": {}}, headers=headers)
    
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "success"
    assert "provisioned successfully" in data["message"]
    assert data["business"]["auth0_org_id"] == "org_acme_99"
    assert "acme-ventures" in data["business"]["slug"]
    assert data["user"]["auth0_user_id"] == "auth0|test_user_99"
    assert data["user"]["email"] == "admin@acmeventures.com"

@patch("app.api.auth.verify_jwt_token")
def test_auth0_onboarding_idempotency_repeat_login(mock_verify):
    """
    Verify that duplicate onboarding attempts with identical token attributes 
    resolve existing entries gracefully without row compilation crashes.
    """
    mock_verify.return_value = {
        "sub": "auth0|duplicate_user",
        "org_id": "org_idempotent_99",
        "org_name": "Idempotent Corp",
        "email": "user@idempotent.com",
        "name": "Idempotent Actor",
        "role": "user"
    }
    headers = {"Authorization": "Bearer mock-token"}
    
    # Run onboarding cycle 1
    resp1 = client.post("/api/v1/auth/onboard", json={}, headers=headers)
    assert resp1.status_code == 200
    data1 = resp1.json()
    
    # Run onboarding cycle 2 (Repeat Login simulation)
    resp2 = client.post("/api/v1/auth/onboard", json={}, headers=headers)
    assert resp2.status_code == 200
    data2 = resp2.json()
    
    assert data1["business"]["id"] == data2["business"]["id"]
    assert data1["user"]["id"] == data2["user"]["id"]

@patch("app.core.auth_dependencies.verify_jwt_token")
def test_deterministic_auth_middleware_rejection(mock_verify):
    """
    Verify that our pure middleware get_current_user dependency safely rejects unprovisioned 
    profiles with a 401 challenge and onboarding signals, without executing side effects.
    """
    mock_verify.return_value = {
        "sub": "auth0|unonboarded_actor",
        "org_id": "org_unonboarded_tenant",
        "email": "ghost@unonboarded.com"
    }
    headers = {"Authorization": "Bearer mock-token"}
    
    # Access a generic protected path
    response = client.get("/api/v1/transactions/health", headers=headers)
    assert response.status_code == 401
    assert "Onboarding" in response.text or "Not authenticated" in response.text