import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from datetime import datetime
from decimal import Decimal

# Adjust these imports based on your app's actual package structure
from app.main import app
from app.core.auth_dependencies import get_current_user
from app.crud.transaction_crud import get_transaction_by_id
from app.core.jwt_utils import create_access_token

client = TestClient(app)

# ---------------------------------------------------------
# Test Setup & Fixtures
# ---------------------------------------------------------

MOCK_TENANT_ID = 1

@pytest.fixture
def auth_headers():
    token = create_access_token(user_id="testuser", role="admin", tenant_id=MOCK_TENANT_ID)
    return {"Authorization": f"Bearer {token}"}

from app.models.transactions import Transactions, TransactionStatus
from app.models.raw_messages import RawMessages
from app.models.participants import Participants

@pytest.fixture
def mock_transaction():
    """Returns a dictionary to bypass the schema's ORM extraction and provide 'phone' directly."""
    return {
        "id": 100,
        "tenant_id": MOCK_TENANT_ID,
        "raw_message_id": 200,
        "amount": Decimal("150.50"),
        "currency": "USD",
        "remarks": "Lunch payment",
        "txn_date": datetime(2023, 10, 1),
        "status": TransactionStatus.PARSED,
        "confidence": 0.95,
        "created_at": datetime(2023, 10, 1, 12, 0),
        "phone": "+1234567890",
        "message_metadata": {
            "message_id": 200,
            "raw_text": "Paid 150.50 for lunch",
            "received_at": datetime(2023, 10, 1, 11, 55)
        },
        "participant": {
            "id": 300,
            "phone": "+1234567890",
            "displayname": "John Doe"
        }
    }

# ---------------------------------------------------------
# Scenario 1 & 3: Valid Retrieval and Response Structure
# ---------------------------------------------------------

@patch("app.api.transactions.get_transaction_by_id")
@patch("app.api.transactions.get_transaction_audit_history")
def test_valid_transaction_retrieval_and_structure(mock_audit, mock_get_txn, mock_transaction, auth_headers):
    # Setup mock returns
    mock_get_txn.return_value = mock_transaction
    mock_audit.return_value = []

    # Execute request dynamically resolving the prefixed route
    url = str(app.url_path_for("get_single_transaction", transaction_id=100))
    response = client.get(url, headers=auth_headers)

    # Assert basic success
    assert response.status_code == 200
    data = response.json()

    # Verify top-level structure
    assert "transaction" in data
    assert "audit_history" in data

    txn_data = data["transaction"]

    # Verify core transaction fields
    assert txn_data["id"] == 100
    assert txn_data["amount"] == "150.50"
    assert txn_data["currency"] == "USD"
    assert txn_data["remarks"] == "Lunch payment"
    assert txn_data["status"] == TransactionStatus.PARSED.value

    # Verify nested message metadata
    assert "message_metadata" in txn_data
    assert txn_data["message_metadata"]["message_id"] == 200

    # Verify nested participant
    assert "participant" in txn_data
    assert txn_data["participant"]["phone"] == "+1234567890"
    assert txn_data["participant"]["displayname"] == "John Doe"

# ---------------------------------------------------------
# Scenario 2: Transaction Not Found
# ---------------------------------------------------------

@patch("app.api.transactions.get_transaction_by_id")
def test_transaction_not_found(mock_get_txn, auth_headers):
    # Simulate DB returning no record
    mock_get_txn.return_value = None

    url = str(app.url_path_for("get_single_transaction", transaction_id=999))
    response = client.get(url, headers=auth_headers)

    # Assert 404 behavior
    assert response.status_code == 404
    assert response.json()["details"] == "Transaction not found"

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
    join_mock_1 = query_mock.join.return_value
    join_mock_2 = join_mock_1.join.return_value
    options_mock = join_mock_2.options.return_value
    filter_mock = options_mock.filter.return_value
    filter_mock.first.return_value = None

    # Call the repository function
    get_transaction_by_id(db_session_mock, transaction_id=1, tenant_id=1)

    # Ensure .options() was appended to the query (which applies joinedload)
    join_mock_2.options.assert_called_once()

# ---------------------------------------------------------
# Scenario 5: Authorization Placeholder
# ---------------------------------------------------------

def test_unauthorized_access():
    url = str(app.url_path_for("get_single_transaction", transaction_id=100))
    response = client.get(url)

    # Without a valid token in headers, it should return 401 Unauthorized
    assert response.status_code == 401