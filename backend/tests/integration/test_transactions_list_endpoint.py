import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.jwt_utils import create_access_token

client = TestClient(app)

@pytest.fixture(scope="module")
def auth_headers():
    """
    Generate valid authentication headers for a specific tenant.
    We use tenant_id=1 to ensure we only retrieve this organization's data.
    """
    token = create_access_token(user_id="test_user", tenant_id=1, role="user")
    return {"Authorization": f"Bearer {token}"}

def test_scenario_1_basic_retrieval(auth_headers):
    """Scenario 1: GET /transactions (Basic Retrieval)"""
    response = client.get("/api/v1/transactions/", headers=auth_headers)
    assert response.status_code == 200
    
    data = response.json()
    assert "limit" in data
    assert data["limit"] == 50 # Verifies default pagination limit
    assert "offset" in data
    assert data["offset"] == 0  # Verifies default offset
    assert isinstance(data["transactions"], list)

def test_scenario_2_filter_by_status(auth_headers):
    """Scenario 2: GET /transactions?status=parsed"""
    response = client.get("/api/v1/transactions/?status=parsed", headers=auth_headers)
    assert response.status_code == 200
    
    data = response.json()
    for txn in data["transactions"]:
        assert txn["status"] == "parsed"

def test_scenario_3_date_range_filtering(auth_headers):
    """Scenario 3: GET /transactions?date_from=...&date_to=..."""
    date_from = "2025-01-01T00:00:00Z"
    date_to = "2025-01-31T23:59:59Z"
    response = client.get(
        f"/api/v1/transactions/?date_from={date_from}&date_to={date_to}", 
        headers=auth_headers
    )
    assert response.status_code == 200
    
    data = response.json()
    for txn in data["transactions"]:
        if txn["txn_date"]:
            # Simple ISO string comparison works correctly for timezone-aware ISO formats
            assert txn["txn_date"] >= date_from
            assert txn["txn_date"] <= date_to

def test_scenario_4_amount_range_filtering(auth_headers):
    """Scenario 4: GET /transactions?amount_min=100&amount_max=500"""
    response = client.get("/api/v1/transactions/?amount_min=100&amount_max=500", headers=auth_headers)
    assert response.status_code == 200
    
    data = response.json()
    for txn in data["transactions"]:
        assert 100 <= txn["amount"] <= 500

def test_scenario_5_currency_filtering(auth_headers):
    """Scenario 5: GET /transactions?currency=USD"""
    response = client.get("/api/v1/transactions/?currency=USD", headers=auth_headers)
    assert response.status_code == 200
    
    data = response.json()
    for txn in data["transactions"]:
        assert txn["currency"] == "USD"

def test_scenario_6_pagination(auth_headers):
    """Scenario 6: GET /transactions?limit=20&offset=20"""
    response = client.get("/api/v1/transactions/?limit=20&offset=20", headers=auth_headers)
    assert response.status_code == 200
    
    data = response.json()
    assert data["limit"] == 20
    assert data["offset"] == 20
    assert len(data["transactions"]) <= 20

def test_scenario_7_sorting(auth_headers):
    """Scenario 7: GET /transactions?sort_by=amount&sort_order=desc"""
    response = client.get("/api/v1/transactions/?sort_by=amount&sort_order=desc", headers=auth_headers)
    assert response.status_code == 200
    
    data = response.json()
    transactions = data["transactions"]
    
    # Verify strict descending order of amount
    for i in range(len(transactions) - 1):
        assert transactions[i]["amount"] >= transactions[i+1]["amount"]

def test_scenario_8_combined_filters(auth_headers):
    """Scenario 8: GET /transactions?status=parsed&currency=USD&limit=10"""
    response = client.get(
        "/api/v1/transactions/?status=parsed&currency=USD&limit=10", 
        headers=auth_headers
    )
    assert response.status_code == 200
    
    data = response.json()
    assert data["limit"] == 10
    assert len(data["transactions"]) <= 10
    
    # Verify all combined constraints are satisfied
    for txn in data["transactions"]:
        assert txn["status"] == "parsed"
        assert txn["currency"] == "USD"