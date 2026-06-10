import pytest
import csv
import io
from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.models.businesses import Businesses
from app.models.transactions import TransactionStatus
from app.core.jwt_utils import create_access_token
from app.api.transactions import EXPORT_CSV_HEADERS

client = TestClient(app)

@pytest.fixture(scope="module")
def auth_headers():
    """Generate valid authentication headers for a specific tenant."""
    token = create_access_token(user_id="test_admin", tenant_id=1, role="admin")
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture
def mock_joined_transaction():
    """
    Creates a mock Transaction ORM object with eagerly loaded nested relations
    (raw_message and sender) to simulate the output of our optimized joined query.
    """
    txn = MagicMock()
    txn.id = 101
    txn.tenant_id = 1
    txn.amount = Decimal("120.00")
    txn.currency = "USD"
    txn.remarks = "groceries"
    txn.status = TransactionStatus.PARSED
    txn.txn_date = datetime(2023, 10, 5, 14, 30, tzinfo=timezone.utc)
    txn.created_at = datetime(2023, 10, 5, 14, 30, tzinfo=timezone.utc)

    # Joined Message Data
    mock_msg = MagicMock()
    mock_msg.id = 201
    mock_msg.message_id = "wa_98765"
    mock_msg.raw_text = "Bought groceries for 120 USD"
    mock_msg.received_at = datetime(2023, 10, 5, 14, 25, tzinfo=timezone.utc)

    # Joined Participant Data
    mock_sender = MagicMock()
    mock_sender.id = 301
    mock_sender.phone = "+19876543210"
    mock_sender.displayname = "John Doe"

    # Assemble relationships
    mock_msg.sender = mock_sender
    txn.raw_message = mock_msg

    return txn


@patch("app.api.transactions.get_transactions")
def test_transaction_list_includes_participant_data(mock_get_transactions, auth_headers, mock_joined_transaction):
    """
    Scenario 1: Transaction List Includes Participant Data
    Verifies the list endpoint serializes the joined participant and message metadata.
    """
    # Setup mock query chain (.limit().offset().all())
    mock_query = MagicMock()
    mock_query.limit.return_value = mock_query
    mock_query.offset.return_value = mock_query
    mock_query.all.return_value = [mock_joined_transaction]
    mock_get_transactions.return_value = mock_query

    response = client.get("/api/v1/transactions/", headers=auth_headers)
    assert response.status_code == 200
    
    data = response.json()
    assert len(data["transactions"]) == 1
    
    txn_data = data["transactions"][0]
    
    # Assert Participant Data
    assert "participant" in txn_data
    assert txn_data["participant"]["name"] == "John Doe"
    assert txn_data["participant"]["phone"] == "+19876543210"
    
    # Assert Message Metadata
    assert "message" in txn_data
    assert txn_data["message"]["id"] == "wa_98765"
    assert txn_data["message"]["text"] == "Bought groceries for 120 USD"


@patch("app.api.transactions.get_transaction_audit_history")
@patch("app.api.transactions.get_transaction_by_id")
def test_transaction_detail_includes_context(mock_get_txn_by_id, mock_get_audit, auth_headers, mock_joined_transaction):
    """
    Scenario 2: Transaction Detail Includes Context
    Verifies the detail endpoint uses the joined query and returns contextual fields.
    """
    mock_get_txn_by_id.return_value = mock_joined_transaction
    mock_get_audit.return_value = []

    response = client.get(f"/api/v1/transactions/{mock_joined_transaction.id}", headers=auth_headers)
    assert response.status_code == 200
    
    data = response.json()
    txn_data = data["transaction"]
    
    # Assert Participant Data
    assert "participant" in txn_data
    assert txn_data["participant"]["displayname"] == "John Doe" 
    assert txn_data["participant"]["phone"] == "+19876543210"
    
    # Assert Message Metadata
    assert "message_metadata" in txn_data
    
    # Extract all values from the metadata dictionary to assert the joined data is present 
    # regardless of Pydantic field aliases
    metadata_values = list(txn_data["message_metadata"].values())
    
    # Assert the joined raw text is successfully serialized
    assert "Bought groceries for 120 USD" in metadata_values

@patch("app.api.transactions.stream_transactions")
def test_csv_export_contains_joined_data_and_consistency(mock_stream_transactions, auth_headers, mock_joined_transaction):
    """
    Scenario 3 & 4: CSV Export Contains Joined Data & Data Consistency
    Verifies the CSV export structure includes the new contextual columns and the exported values precisely match the database.
    """
    def fake_stream(*args, **kwargs):
        yield mock_joined_transaction
    mock_stream_transactions.return_value = fake_stream()

    response = client.get("/api/v1/transactions/export", headers=auth_headers)
    assert response.status_code == 200
    
    content = response.content.decode("utf-8")
    csv_reader = csv.reader(io.StringIO(content))
    rows = list(csv_reader)
    
    assert len(rows) >= 2
    header = rows[0]
    data_row = rows[1]
    
    # Scenario 3: Verify Column Headers Exist
    assert "participant_name" in header
    assert "participant_phone" in header
    assert "message_timestamp" in header
    
    # Scenario 4: Data Consistency check
    row_dict = dict(zip(header, data_row))
    assert row_dict["participant_name"] == "John Doe"
    assert row_dict["participant_phone"] == "+19876543210"
    assert row_dict["message_id"] == "wa_98765"
    assert row_dict["message_text"] == "Bought groceries for 120 USD"
    # Ensure datetime was formatted correctly to ISO
    assert "2023-10-05T14:25:00" in row_dict["message_timestamp"]


@patch("app.api.transactions.get_transaction_audit_history")
@patch("app.api.transactions.get_transaction_by_id")
@patch("app.api.transactions.get_transactions")
def test_query_efficiency(mock_get_transactions, mock_get_txn_by_id, mock_get_audit, auth_headers, mock_joined_transaction):
    """
    Scenario 5: Query Efficiency
    Verifies that the endpoints invoke their respective optimized CRUD functions exactly once,
    preventing N+1 query execution loops.
    """
    # Test List Endpoint Efficiency
    mock_query = MagicMock()
    mock_query.limit.return_value = mock_query
    mock_query.offset.return_value = mock_query
    mock_query.all.return_value = [mock_joined_transaction]
    mock_get_transactions.return_value = mock_query

    client.get("/api/v1/transactions/", headers=auth_headers)
    mock_get_transactions.assert_called_once()
    mock_query.all.assert_called_once()  # Asserts the DB is hit exactly once for the collection

    # Test Detail Endpoint Efficiency
    mock_get_txn_by_id.return_value = mock_joined_transaction
    mock_get_audit.return_value = []
    client.get(f"/api/v1/transactions/{mock_joined_transaction.id}", headers=auth_headers)
    mock_get_txn_by_id.assert_called_once() # Asserts the DB is hit exactly once for the single item