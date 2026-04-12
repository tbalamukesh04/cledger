import pytest
import csv
import io
from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.models.transactions import Transactions, TransactionStatus
from app.core.jwt_utils import create_access_token
from app.api.transactions import EXPORT_CSV_HEADERS

client = TestClient(app)

@pytest.fixture(scope="module")
def auth_headers():
    """Generate valid authentication headers for a specific tenant."""
    token = create_access_token(user_id="test_user", tenant_id=1, role="user")
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture
def mock_transaction():
    """Creates a mock Transaction ORM object with nested relations to bypass db_session requirements."""
    txn = MagicMock()
    txn.id = 100
    txn.tenant_id = 1
    txn.raw_message_id = 200
    txn.amount = Decimal("50.00")
    txn.currency = "ZMW"
    txn.txn_type = "debit"
    txn.remarks = "supplies"
    txn.status = TransactionStatus.REVIEW_NEEDED
    txn.hash = "unique_hash_123"
    txn.txn_date = datetime(2023, 10, 1, 12, 0, tzinfo=timezone.utc)
    txn.created_at = datetime(2023, 10, 1, 12, 0, tzinfo=timezone.utc)

    mock_msg = MagicMock()
    mock_msg.id = 200
    mock_msg.message_id = "wa_12345"
    mock_msg.received_at = datetime(2023, 10, 1, 11, 55, tzinfo=timezone.utc)
    mock_msg.raw_text = "Paid 50 ZMW for supplies"

    mock_sender = MagicMock()
    mock_sender.id = 300
    mock_sender.phone = "+1234567890"
    mock_sender.displayname = "John Doe"

    mock_msg.sender = mock_sender
    txn.raw_message = mock_msg

    return txn

def test_basic_csv_export_and_structure(auth_headers):
    """
    Scenario 1 & 2: Basic CSV Export and Structure Validation
    Verifies the endpoint returns a valid CSV file with the exact required header structure.
    """
    response = client.get("/api/v1/transactions/export", headers=auth_headers)
    
    assert response.status_code == 200
    assert response.headers["Content-Type"] == "text/csv; charset=utf-8"
    assert "attachment; filename=transactions_export.csv" in response.headers["Content-Disposition"]

    # Read the response content as a CSV
    content = response.content.decode("utf-8")
    csv_reader = csv.reader(io.StringIO(content))
    rows = list(csv_reader)

    # Verify header row exists and matches expected structure
    assert len(rows) > 0, "CSV should at least contain a header row"
    header_row = rows[0]
    
    assert header_row == EXPORT_CSV_HEADERS

@patch("app.api.transactions.stream_transactions")
def test_batch_streaming_verification(mock_stream_transactions, auth_headers):
    """
    Scenario 3: Batch Streaming Verification
    Verifies that the endpoint requests database records in memory-safe batches.
    """
    # Mock the generator to return nothing, we just want to inspect how it was called
    mock_stream_transactions.return_value = (txn for txn in [])
    
    client.get("/api/v1/transactions/export", headers=auth_headers)
    
    # Assert the repository function was called with the correct batch_size parameter
    mock_stream_transactions.assert_called_once()
    _, kwargs = mock_stream_transactions.call_args
    assert kwargs.get("batch_size") == 1000

@patch("app.api.transactions.generate_transaction_csv_rows")
def test_streaming_response_behavior(mock_generate_rows, auth_headers):
    """
    Scenario 4: Streaming Response Behavior
    Verifies that the endpoint properly wraps the generator in a StreamingResponse.
    """
    def fake_generator(*args, **kwargs):
        yield "chunk1,"
        yield "chunk2"
        
    mock_generate_rows.return_value = fake_generator()
    
    response = client.get("/api/v1/transactions/export", headers=auth_headers)
    
    assert response.status_code == 200
    assert "content-length" not in response.headers
    assert response.text == "chunk1,chunk2"

@patch("app.api.transactions.stream_transactions")
def test_data_integrity(mock_stream_transactions, auth_headers, mock_transaction):
    """
    Scenario 5: Data Integrity
    Verifies that the exported rows accurately match the values yielded by the DB.
    """
    # Make the mocked stream_transactions yield our fake transaction
    def fake_stream(*args, **kwargs):
        yield mock_transaction
    mock_stream_transactions.return_value = fake_stream()

    response = client.get("/api/v1/transactions/export", headers=auth_headers)
    assert response.status_code == 200
    
    content = response.content.decode("utf-8")
    csv_reader = csv.reader(io.StringIO(content))
    rows = list(csv_reader)
    
    assert len(rows) >= 2
    header = rows[0]
    data_row = rows[1]
    
    # Zip the header and row together for easy dictionary-style assertions
    row_dict = dict(zip(header, data_row))
    
    assert row_dict["transaction_id"] == str(mock_transaction.id)
    assert row_dict["amount"] == "50.0" # Decimal formatted to float/string
    assert row_dict["currency"] == "ZMW"
    assert row_dict["remarks"] == "supplies"
    assert row_dict["status"] == TransactionStatus.REVIEW_NEEDED.value
    
    # Handle dynamic CSV headers based on export format
    if "participant" in row_dict:
        assert row_dict["participant"] == "John Doe (+1234567890)"
    elif "sender" in row_dict:
        assert row_dict["sender"] == "John Doe (+1234567890)"
    
    # Ensure dates are exported in ISO format
    assert mock_transaction.txn_date.isoformat() in row_dict["transaction_date"]