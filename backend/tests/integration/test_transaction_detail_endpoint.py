import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from datetime import datetime
from decimal import Decimal

# Adjust these imports based on your app's actual package structure
from app.main import app
from app.core.auth_dependencies import get_current_user
from app.crud.transaction_crud import get_transaction_by_id

client = TestClient(app)

# ---------------------------------------------------------
# Test Setup & Fixtures
# ---------------------------------------------------------

MOCK_TENANT_ID = 1
MOCK_USER = {"sub": "testuser", "tenant_id": MOCK_TENANT_ID}

def override_get_current_user():
    return MOCK_USER

# Override the authentication dependency for standard tests
app.dependency_overrides[get_current_user] = override_get_current_user


@pytest.fixture
def mock_transaction():
    """Creates a mock Transaction ORM object with nested relations."""
    txn = MagicMock()
    txn.id = 100
    txn.tenant_id = MOCK_TENANT_ID
    txn.raw_message_id = 200
    txn.amount = Decimal("150.50")
    txn.currency = "USD"
    txn.remarks = "Lunch payment"
    txn.txn_date = datetime(2023, 10, 1)
    txn.status = "COMPLETED"
    txn.confidence = 0.95
    txn.created_at = datetime(2023, 10, 1, 12, 0)
    txn.updated_at = None

    # Mock related RawMessage
    mock_msg = MagicMock()
    mock_msg.id = 200
    mock_msg.message_id = "wa_12345"
    mock_msg.received_at = datetime(2023, 10, 1, 11, 55)
    mock_msg.raw_text = "Paid 150.50 for lunch"

    # Mock related Participant (sender)
    mock_sender = MagicMock()
    mock_sender.id = 300
    mock_sender.phone = "+1234567890"
    mock_sender.displayname = "John Doe"

    mock_msg.sender = mock_sender
    txn.raw_message = mock_msg

    return txn

# ---------------------------------------------------------
# Scenario 1 & 3: Valid Retrieval and Response Structure
# ---------------------------------------------------------

@patch("app.api.transactions.get_transaction_by_id")
@patch("app.api.transactions.get_transaction_audit_history")
def test_valid_transaction_retrieval_and_structure(mock_audit, mock_get_txn, mock_transaction):
    # Setup mock returns
    mock_get_txn.return_value = mock_transaction
    mock_audit.return_value = []

    # Execute request dynamically resolving the prefixed route
    url = str(app.url_path_for("get_single_transaction", transaction_id=100))
    response = client.get(url)

    # Assert basic success
    assert response.status_code == 200
    data = response.json()

    # Verify top-level structure
    assert "transactions" in data
    assert "limit" in data

    txn_data = data["transaction"]

    # Verify core transaction fields
    assert txn_data["id"] == 100
    assert txn_data["amount"] == "150.50"
    assert txn_data["currency"] == "USD"
    assert txn_data["remarks"] == "Lunch payment"
    assert txn_data["status"] == "COMPLETED"

    # Verify nested message metadata
    assert "message_metadata" in txn_data
    assert txn_data["message_metadata"]["id"] == 200
    assert txn_data["message_metadata"]["whatsapp_message_id"] == "wa_12345"

    # Verify nested participant
    assert "participant" in txn_data
    assert txn_data["participant"]["id"] == 300
    assert txn_data["participant"]["phone"] == "+1234567890"
    assert txn_data["participant"]["displayname"] == "John Doe"

# ---------------------------------------------------------
# Scenario 2: Transaction Not Found
# ---------------------------------------------------------

@patch("app.api.transactions.get_transaction_by_id")
def test_transaction_not_found(mock_get_txn):
    # Simulate DB returning no record
    mock_get_txn.return_value = None

    url = str(app.url_path_for("get_single_transaction", transaction_id=999))
    response = client.get(url)

    # Assert 404 behavior
    assert response.status_code == 404
    assert response.json()["detail"] == "Transaction not found"

# ---------------------------------------------------------
# Scenario 4: Query Efficiency (Ensure joinedload is used)
# ---------------------------------------------------------

def test_query_efficiency_joinedload_used():
    """
    Verifies that the repository function explicitly uses joinedload options 
    to prevent N+1 DB queries when fetching a single transaction.
    """
    db_session_mock = MagicMock()
    
    # Mock the SQLAlchemy query chain
    query_mock = db_session_mock.query.return_value
    filter_mock = query_mock.filter.return_value
    options_mock = filter_mock.options.return_value
    options_mock.first.return_value = None

    # Call the repository function
    get_transaction_by_id(db_session_mock, transaction_id=1, tenant_id=1)

    # Ensure .options() was appended to the query (which applies joinedload)
    filter_mock.options.assert_called_once()

# ---------------------------------------------------------
# Scenario 5: Authorization Placeholder
# ---------------------------------------------------------

def test_unauthorized_access():
    # Temporarily remove the dependency override to test actual auth blocks
    app.dependency_overrides.pop(get_current_user, None)

    url = str(app.url_path_for("get_single_transaction", transaction_id=100))
    response = client.get(url)

    # Without a valid token in headers, it should return 401 Unauthorized
    assert response.status_code == 401

    # Restore the override so subsequent tests don't fail
    app.dependency_overrides[get_current_user] = override_get_current_user