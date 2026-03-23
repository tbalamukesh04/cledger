import pytest
import uuid
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from app.database.database import SessionLocal
from app.models.raw_messages import RawMessages
from app.models.participants import Participants
from app.models.groups import Groups
from app.schemas.jobs import WebhookJobPayload
from app.workers.job_handler import process_webhook_batch

@pytest.fixture(scope="module")
def db_session():
    """Provides a transactional database session for the test."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.rollback()
        db.close()

@pytest.fixture
def setup_test_data(db_session):
    """Sets up prerequisite foreign key records (Participant, Group)."""
    tenant_id = 1
    
    # Create dummy group
    test_group_string_id = f"test_group_{uuid.uuid4().hex[:8]}"
    group = Groups(
        group_id=test_group_string_id, 
        tenant_id=tenant_id, 
        groupname="Test Ledger Group"
    )
    db_session.add(group)
    
    # Create dummy participant
    participant = Participants(
        tenant_id=tenant_id, 
        phone=f"+1{uuid.uuid4().hex[:10]}",
        displayname="Test User"
    )
    db_session.add(participant)
    
    db_session.commit()
    
    return {
        "tenant_id": tenant_id, 
        "group_id": group.id,         # DB integer ID for RawMessages.group_id
        "participant_id": participant.id   # DB integer ID for RawMessages.sender_id
    }

@patch("app.workers.job_handler.AIParser") 
def test_metadata_persistence_workflow(MockAIParser, db_session, setup_test_data):
    """
    Validates that the worker correctly scores messages, updates the is_transaction 
    flag, and persists the JSONB parsing_meta for both paths.
    """
    # 1. Setup Raw Messages in DB
    tx_msg_wamid = f"wamid.{uuid.uuid4().hex[:8]}"
    ntx_msg_wamid = f"wamid.{uuid.uuid4().hex[:8]}"
    
    current_time = datetime.now(timezone.utc)
    epoch_str = str(int(current_time.timestamp()))
    
    # High score candidate
    tx_text = "Paid 500 ZMW for the groceries"
    msg_tx = RawMessages(
        tenant_id=setup_test_data["tenant_id"],
        group_id=setup_test_data["group_id"],
        sender_id=setup_test_data["participant_id"],
        message_id=tx_msg_wamid,
        raw_text=tx_text, 
        received_at=current_time,
        raw_json={"entry": [{"changes": [{"value": {"messages": [{"type": "text", "text": {"body": tx_text}, "timestamp": epoch_str}]}}]}]},
        hash=f"hash_{tx_msg_wamid}"
    )
    
    # Low score candidate
    ntx_text = "Hey guys, what time are we meeting tomorrow?"
    msg_ntx = RawMessages(
        tenant_id=setup_test_data["tenant_id"],
        group_id=setup_test_data["group_id"],
        sender_id=setup_test_data["participant_id"],
        message_id=ntx_msg_wamid,
        raw_text=ntx_text, 
        received_at=current_time,
        raw_json={"entry": [{"changes": [{"value": {"messages": [{"type": "text", "text": {"body": ntx_text}, "timestamp": epoch_str}]}}]}]},
        hash=f"hash_{ntx_msg_wamid}"
    )
    
    db_session.add_all([msg_tx, msg_ntx])
    db_session.commit() # Commit to generate integer IDs
    db_session.refresh(msg_tx)
    db_session.refresh(msg_ntx)
    
    # 2. Setup Worker Jobs
    # 2. Setup Worker Jobs
    job_tx = WebhookJobPayload(
        job_id=f"job_{tx_msg_wamid}",
        raw_message_id=msg_tx.id,
        participant_id=msg_tx.sender_id,
        group_id=msg_tx.group_id,
        message_timestamp=msg_tx.received_at,
        webhook_event_type="messages",
        ingestion_time=current_time
    )
    
    job_ntx = WebhookJobPayload(
        job_id=f"job_{ntx_msg_wamid}",
        raw_message_id=msg_ntx.id,
        participant_id=msg_ntx.sender_id,
        group_id=msg_ntx.group_id,
        message_timestamp=msg_ntx.received_at,
        webhook_event_type="messages",
        ingestion_time=current_time
    )
    
    # Configure Mock AI to return a "failed extraction" list element 
    # to bypass the actual Transactions insert logic in this test
    mock_instance = MockAIParser.return_value
    mock_instance.parse_batch.return_value = [None]
    
    # 3. Execute Worker Pipeline
    results = process_webhook_batch([job_tx, job_ntx])
    
    # Refresh DB objects to check updated state
    db_session.refresh(msg_tx)
    db_session.refresh(msg_ntx)
    
    # 4. Assertions - Transaction Candidate
    assert results[job_tx.job_id] in ["success", "success_with_fallback"], "Transaction job should be processed successfully"
    assert msg_tx.is_transaction is True, "Valid financial message should be flagged as is_transaction=True"
    assert msg_tx.parsing_meta is not None, "parsing_meta JSONB should be populated"
    assert "score" in msg_tx.parsing_meta
    assert "threshold" in msg_tx.parsing_meta
    assert msg_tx.parsing_meta["score"] >= msg_tx.parsing_meta["threshold"]
    assert "rule_breakdown" in msg_tx.parsing_meta
    
    # 5. Assertions - Non-Transaction Candidate
    assert results[job_ntx.job_id] == "success", "Non-transaction job should be completed"
    assert msg_ntx.is_transaction is False, "Conversational message should be flagged as is_transaction=False"
    assert msg_ntx.parsing_meta is not None, "parsing_meta JSONB should be populated even for drops"
    assert msg_ntx.parsing_meta["score"] < msg_ntx.parsing_meta["threshold"]
    assert msg_ntx.processing_status == "NON_TRANSACTION", "Pipeline should immediately mark as NON_TRANSACTION"