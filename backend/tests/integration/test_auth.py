import pytest
import datetime
from fastapi import HTTPException
from app.core.jwt_utils import create_access_token, verify_jwt_token

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

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

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

def test_scenario_3_and_4_valid_token_and_role_extraction():
    """Scenario 3 & 4: Verify valid token allows access and role is correctly extracted."""
    # We will encode a specific role here to verify extraction
    token = create_access_token(user_id="user_789", tenant_id=1, role="admin")
    headers = {"Authorization": f"Bearer {token}"}
    
    # We hit the /me endpoint because it returns the current_user context
    response = client.get("/api/v1/transactions/me", headers=headers)
    assert response.status_code == 200, response.text
    
    data = response.json()
    assert data["message"] == "Authenticated access granted"
    
    # Verifying Scenario 4 exactly: user identity and role are extracted
    assert data["current_user"]["user_id"] == "user_789"
    assert data["current_user"]["role"] == "admin"

def test_require_admin_rejects_normal_user():
    """Verify that an endpoint protected by require_admin rejects a standard user."""
    token = create_access_token(user_id="user_123", tenant_id=1, role="user")
    headers = {"Authorization": f"Bearer {token}"}
    
    response = client.get("/api/v1/transactions/admin-only", headers=headers)
    assert response.status_code == 403, response.text
    assert "Not enough permissions to access this resource" in response.text

def test_require_admin_allows_admin_user():
    """Verify that an endpoint protected by require_admin allows an admin user."""
    token = create_access_token(user_id="admin_456", tenant_id=1, role="admin")
    headers = {"Authorization": f"Bearer {token}"}
    
    response = client.get("/api/v1/transactions/admin-only", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["message"] == "Admin access granted"