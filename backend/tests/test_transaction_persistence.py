import pytest
from decimal import Decimal
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.database.database import SessionLocal

# 1. IMPORTANT: Import related models BEFORE RawMessages so SQLAlchemy can build the mapper registry
from app.models.participants import Participants
from app.models.groups import Groups
from app.models.raw_messages import RawMessages
from app.models.transactions import Transactions, TransactionStatus
from app.crud.transaction_crud import create_transaction, get_transaction_by_message

@pytest.fixture
def db_session():
    """
    Provides a database session for the test.
    Automatically rolls back after the test finishes so the database remains clean.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.rollback()
        db.close()

def test_transaction_persistence_flow(db_session: Session):
    # 1. Setup Foreign Keys: Create mock Participant and Group
    mock_participant = Participants(
        phone="1234567890_test",
        displayname="Test User"
    )
    mock_group = Groups(
        group_id="test_group_123",
        groupname="Test Group"
    )
    db_session.add(mock_participant)
    db_session.add(mock_group)
    db_session.flush() # Generate IDs for FKs

    # 2. Setup: Create a mock raw message with ALL required fields
    mock_msg = RawMessages(
        sender_id=mock_participant.id,
        group_id=mock_group.id,
        message_id="wamid.test_persistence_123",
        received_at=datetime.now(timezone.utc),
        raw_json={"test": "data"},
        processed=False,
        hash="test_hash_persistence_123"
    )
    db_session.add(mock_msg)
    db_session.flush() # Generate mock_msg.id

    # 3. Define the parsed transaction data payload
    txn_data = {
        "raw_message_id": mock_msg.id,
        "amount": Decimal("150.50"),
        "currency": "ZMW",
        "txn_type": "debit",
        "remarks": "Grocery shopping at Shoprite",
        "confidence": 0.85,
        "status": TransactionStatus.PARSED,
        "hash": "txn_hash_12345_persistence_test"
    }

    # 4. Execute: Create the transaction via our CRUD layer
    txn = create_transaction(db=db_session, txn_data=txn_data, commit=False)
    db_session.flush() # Generate txn.id

    # 5. Assertions: Verify successful creation and exact field mapping
    assert txn.id is not None
    assert txn.raw_message_id == mock_msg.id
    assert txn.amount == Decimal("150.50")
    assert txn.currency == "ZMW"
    assert txn.txn_type == "debit"
    assert txn.remarks == "Grocery shopping at Shoprite"
    assert txn.status == TransactionStatus.PARSED

    # 6. Assertions: Verify the transaction can be fetched by message ID
    fetched_txn = get_transaction_by_message(db_session, mock_msg.id)
    assert fetched_txn is not None
    assert fetched_txn.id == txn.id

    # 7. Validate duplicate rejection (Same raw_message_id)
    duplicate_txn_data = txn_data.copy()
    duplicate_txn_data["hash"] = "different_hash_to_bypass_hash_check"
    
    with pytest.raises(ValueError) as exc_info:
        create_transaction(db_session, duplicate_txn_data, commit=False)
    
    # Verify the error message matches our CRUD layer's safety check
    assert f"Transaction for raw_message_id {mock_msg.id} already exists." in str(exc_info.value)
