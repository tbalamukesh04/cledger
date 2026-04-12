import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from datetime import datetime

# Adjust import paths based on your actual project structure
from app.main import app
from app.core.auth_dependencies import require_admin, get_current_user
from app.api.dependencies import get_db
from app.models.transactions import TransactionStatus, Transactions

client = TestClient(app)

# ---------------------------------------------------------
# Test Setup & Fixtures
# ---------------------------------------------------------

MOCK_ADMIN = {"sub": "admin_user", "tenant_id": 1, "role": "admin"}

def override_require_admin():
    return MOCK_ADMIN

def override_get_db():
    mock_db = MagicMock()
    yield mock_db

# Override authentication dependencies and database session
app.dependency_overrides[require_admin] = override_require_admin
app.dependency_overrides[get_current_user] = override_require_admin
app.dependency_overrides[get_db] = override_get_db

@pytest.fixture
def mock_review_needed_txn():
    """Fixture returning a mock transaction stuck in REVIEW_NEEDED."""
    txn = MagicMock()
    txn.id = 100
    txn.tenant_id = 1
    txn.status = TransactionStatus.REVIEW_NEEDED
    txn.amount = 100.0
    txn.raw_message = None  # Bypass Pydantic nested extraction
    return txn


# ---------------------------------------------------------
# Scenario 1 & 6: Correct Action & Audit Verification
# ---------------------------------------------------------
@patch("app.api.transactions.get_transaction_by_id")
@patch("app.api.transactions.correct_transaction_service")
@patch("app.api.transactions.get_transaction_audit_history")
def test_correct_action_and_audit(mock_audit, mock_correct_svc, mock_get_txn, mock_review_needed_txn):    
    # Setup mocks
    mock_get_txn.return_value = mock_review_needed_txn
    
    # Use an actual SQLAlchemy model so db.refresh() doesn't crash on a mock
    updated_txn = Transactions()
    updated_txn.id = 100
    updated_txn.tenant_id = 1
    updated_txn.status = TransactionStatus.CORRECTED
    updated_txn.amount = 120.0
    updated_txn.currency = "USD"
    updated_txn.remarks = "Corrected amount"        
    updated_txn.txn_date = datetime.now()
    updated_txn.confidence = 0.95
    updated_txn.created_at = datetime.now()        
    updated_txn.updated_at = datetime.now()        
    updated_txn.raw_message_id = None
    
    mock_correct_svc.return_value = updated_txn

    mock_audit.return_value = [
        {
            "id": 1,
            "action": "CORRECTED",
            "performed_by": "admin_user",
            "old_snapshot": {"amount": "100.0"},
            "created_at": datetime.now()
        }
    ]

    # Execute request dynamically resolving the route
    url = str(app.url_path_for("review_transaction", transaction_id=100))
    response = client.post(url, json={
        "action": "correct",
        "corrected_fields": {"amount": 120.0}
    })

    # Assert basic success
    assert response.status_code == 200
    data = response.json()

    # Verify service was invoked
    mock_correct_svc.assert_called_once()
    
    # Verify transaction status in response
    assert data["transaction"]["status"] == "corrected"
    
    # Verify Audit entries
    assert len(data["audit_history"]) == 1
    audit_entry = data["audit_history"][0]
    assert audit_entry["action"] == "CORRECTED"
    assert "old_snapshot" in audit_entry


# ---------------------------------------------------------
# Scenario 2 & 6: Invalidate Action & Audit Verification
# ---------------------------------------------------------
@patch("app.api.transactions.get_transaction_by_id")
@patch("app.api.transactions.invalidate_transaction_service")
@patch("app.api.transactions.get_transaction_audit_history")
def test_invalidate_action_and_audit(mock_audit, mock_invalidate_svc, mock_get_txn, mock_review_needed_txn):
    # Setup mocks
    mock_get_txn.return_value = mock_review_needed_txn
    
    # Use an actual SQLAlchemy model so db.refresh() doesn't crash on a mock
    updated_txn = Transactions()
    updated_txn.id = 100
    updated_txn.tenant_id = 1
    updated_txn.status = TransactionStatus.INVALIDATED
    updated_txn.amount = 100.0
    updated_txn.currency = "USD"
    updated_txn.remarks = "Invalidated transaction"
    updated_txn.txn_date = datetime.now()
    updated_txn.confidence = 0.95
    updated_txn.created_at = datetime.now()        
    updated_txn.updated_at = datetime.now()        
    updated_txn.raw_message_id = None
    
    mock_invalidate_svc.return_value = updated_txn

    mock_audit.return_value = [
        {
            "id": 2,
            "action": "INVALIDATED",
            "performed_by": "admin_user",
            "old_snapshot": {"status": "REVIEW_NEEDED"},
            "created_at": datetime.now()
        }
    ]

    url = str(app.url_path_for("review_transaction", transaction_id=100))
    response = client.post(url, json={
        "action": "invalidate"
    })

    assert response.status_code == 200
    data = response.json()

    # Verify service was invoked
    mock_invalidate_svc.assert_called_once()
    
    # Verify transaction status in response
    assert data["transaction"]["status"] == "invalidated"
    
    # Verify Audit entries
    assert data["audit_history"][0]["action"] == "INVALIDATED"


# ---------------------------------------------------------
# Scenario 3: Invalid Status (Not REVIEW_NEEDED)
# ---------------------------------------------------------
@patch("app.api.transactions.invalidate_transaction_service")
@patch("app.api.transactions.get_transaction_by_id")
def test_invalid_status_rejection(mock_get_txn, mock_invalidate_svc):
    # Mock a transaction that is already PARSED
    txn = MagicMock()
    txn.status = TransactionStatus.PARSED
    mock_get_txn.return_value = txn
    
    # Force the service layer to reject the operation, as it would in reality
    # since the status is not REVIEW_NEEDED
    mock_invalidate_svc.side_effect = ValueError("Transaction is not in REVIEW_NEEDED state")

    url = str(app.url_path_for("review_transaction", transaction_id=100))
    response = client.post(url, json={
        "action": "invalidate"
    })

    # Should reject the review action with a 400 Bad Request
    assert response.status_code == 400
    assert "not in REVIEW_NEEDED state" in response.text

# ---------------------------------------------------------
# Scenario 4: Missing Corrected Fields
# ---------------------------------------------------------
def test_missing_corrected_fields_for_correct_action():
    url = str(app.url_path_for("review_transaction", transaction_id=100))
    
    # Send action='correct' without 'corrected_fields'
    response = client.post(url, json={
        "action": "correct"
    })

    # FastAPI returns 422 for Pydantic Schema validations, or 400 for manual route validations
    assert response.status_code in [400, 422]


# ---------------------------------------------------------
# Scenario 5: Unauthorized Access
# ---------------------------------------------------------
def test_unauthorized_access():
    # Remove the mock admin overrides
    app.dependency_overrides.pop(require_admin, None)
    app.dependency_overrides.pop(get_current_user, None)

    url = str(app.url_path_for("review_transaction", transaction_id=100))
    response = client.post(url, json={
        "action": "invalidate"
    })

    # Should be rejected with a 401 Unauthorized
    assert response.status_code == 401

    # Restore overrides for safety in subsequent tests
    app.dependency_overrides[require_admin] = override_require_admin
    app.dependency_overrides[get_current_user] = override_require_admin