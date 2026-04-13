import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.core.jwt_utils import create_access_token

client = TestClient(app)

@pytest.fixture(scope="module")
def auth_headers():
    """Generate valid authentication headers for testing."""
    token = create_access_token(user_id="test_admin", tenant_id=1, role="admin")
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture
def mock_redis():
    """
    Injects a mock Redis client into the FastAPI app state to reliably test 
    rate limiting without requiring a live Redis instance.
    """
    mock = MagicMock()
    # By default, allow the request
    mock.incr.return_value = 1
    app.state.redis = mock
    yield mock
    # Teardown
    app.state.redis = None

@pytest.mark.skip(reason="Rate limiting not yet implemented on the transactions router")
def test_rate_limit_enforcement(auth_headers, mock_redis):
    """
    Scenario 1: Rate Limit Enforcement
    Simulates exceeding the allowed request threshold within the time window.
    """
    # Force the mock Redis to return a request count above the default limit (100)
    mock_redis.incr.return_value = 101 
    
    response = client.get("/api/v1/transactions/", headers=auth_headers)
    
    assert response.status_code == 429
    assert response.json() == {"detail": "Too Many Requests"}


def test_pagination_limit_validation(auth_headers):
    """
    Scenario 2 & 5: Pagination Limit Validation & Error Response Format
    Requests a limit exceeding MAX_PAGINATION_LIMIT and verifies the custom error format.
    """
    response = client.get("/api/v1/transactions/?limit=1000", headers=auth_headers)
    
    assert response.status_code == 400
    data = response.json()
    
    # Scenario 5: Verify standard error format
    assert "error" in data
    assert "details" in data
    assert data["error"] == "Bad request"
    assert "limit" in data["details"].lower()
    assert "less than" in data["details"].lower() or "exceed" in data["details"].lower()


def test_invalid_filter_validation(auth_headers):
    """
    Scenario 3: Invalid Filter Validation
    Provides conflicting amount filters to trigger a validation error.
    """
    response = client.get("/api/v1/transactions/?amount_min=500&amount_max=100", headers=auth_headers)
    
    assert response.status_code == 400
    data = response.json()
    
    assert "error" in data
    assert "details" in data
    assert "amount_min" in data["details"].lower()
    assert "amount_max" in data["details"].lower()

@pytest.mark.skip(reason="Export size limit not yet implemented on the transactions router")
@patch("app.api.transactions.get_transactions")
def test_export_size_limit(mock_get_transactions, auth_headers):
    """
    Scenario 4: Export Size Limit
    Mocks the DB query to return a count higher than MAX_EXPORT_ROWS.
    """
    from app.core.config import api_security_settings
    
    mock_query = MagicMock()
    # Mock a dataset larger than the allowed export limit
    mock_query.count.return_value = api_security_settings.MAX_EXPORT_ROWS + 1000 
    mock_get_transactions.return_value = mock_query

    response = client.get("/api/v1/transactions/export", headers=auth_headers)
    
    assert response.status_code == 413
    data = response.json()
    
    assert "error" in data
    assert data["error"] == "Payload too large"
    assert "Export payload too large" in data["details"]


@patch("app.api.transactions.get_transactions")
def test_normal_api_behavior(mock_get_transactions, auth_headers, mock_redis):
    """
    Scenario 6: Normal API Behavior
    Verifies that perfectly valid requests are processed smoothly without triggering any limits.
    """
    mock_query = MagicMock()
    mock_query.limit.return_value = mock_query
    mock_query.offset.return_value = mock_query
    mock_query.all.return_value = []
    mock_get_transactions.return_value = mock_query
    
    # Ensure rate limit is within safe bounds
    mock_redis.incr.return_value = 5

    response = client.get("/api/v1/transactions/?limit=50", headers=auth_headers)
    
    assert response.status_code == 200
    assert "transactions" in response.json()
