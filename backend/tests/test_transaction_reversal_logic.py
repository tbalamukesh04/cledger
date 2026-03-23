import pytest
import uuid
from decimal import Decimal
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from app.main import app
from app.database.database import SessionLocal
from app.models.transactions import Transactions, TransactionStatus
from app.models.transaction_audit import TransactionAudit, TransactionAuditAction
from app.models.raw_messages import RawMessages
from app.models.groups import Groups
from app.models.participants import Participants
from app.crud.transaction_crud import upsert_transaction

client = TestClient(app)

@pytest.fixture(scope="module")
def db_session():
    db = SessionLocal()
    yield db
    db.close()

def create_base_data(db):
    """Helper to create fresh base data for each test scenario."""
    test_run_id = str(uuid.uuid4())[:8]
    
    participant = Participants(tenant_id=1, phone=f"+1000{test_run_id}", displayname="Tester")
    db.add(participant)
    
    group = Groups(tenant_id=1, group_id=f"grp_{test_run_id}", groupname="Test Group")
    db.add(group)
    db.commit()

    raw_msg = RawMessages(
        tenant_id=1,
        sender_id=participant.id,
        group_id=group.id,
        message_id=f"msg_{test_run_id}",
        hash=f"raw_hash_{test_run_id}",
        received_at=datetime.now(timezone.utc),
        raw_json={"test": "data"}
    )
    db.add(raw_msg)
    db.commit()

    txn = Transactions(
        tenant_id=1,
        raw_message_id=raw_msg.id,
        amount=Decimal("100.00"),
        currency="USD",
        txn_type="credit",
        status=TransactionStatus.REVIEW_NEEDED,
        hash=f"txn_hash_{test_run_id}"
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)
    
    return txn, raw_msg

def test_transaction_correction_and_snapshot_integrity(db_session):
    """Tests Scenarios 1 & 4: Correction workflow and Snapshot Integrity"""
    txn, _ = create_base_data(db_session)
    txn_id = txn.id
    
    correct_payload = {
        "amount": 150.00,
        "remarks": "Admin corrected amount"
    }
    
    # Scenario 1: Admin edits amount
    response = client.post(f"/api/v1/transactions/{txn_id}/correct", json=correct_payload)
    assert response.status_code == 200
    
    # Verify DB State updated correctly
    db_session.expire_all()
    updated_txn = db_session.query(Transactions).filter(Transactions.id == txn_id).first()
    assert updated_txn.status == TransactionStatus.CORRECTED
    assert updated_txn.amount == Decimal("150.00")
    
    # Verify Audit log was created
    audit_logs = db_session.query(TransactionAudit).filter(TransactionAudit.transaction_id == txn_id).all()
    assert len(audit_logs) >= 1
    
    latest_audit = audit_logs[-1]
    assert latest_audit.action == TransactionAuditAction.CORRECTED
    
    # Scenario 4: Snapshot Integrity Validation
    assert latest_audit.old_value is not None
    assert latest_audit.new_value is not None
    assert float(latest_audit.old_value["amount"]) == 100.0  # Original Snapshot
    assert float(latest_audit.new_value["amount"]) == 150.0  # Corrected Snapshot
    assert latest_audit.old_value != latest_audit.new_value

def test_worker_protection_rule(db_session):
    """Tests Scenario 3: Worker cannot overwrite CORRECTED/INVALIDATED transactions"""
    # 1. Setup: Create a transaction and correct it
    txn, raw_msg = create_base_data(db_session)
    txn_id = txn.id
    
    correct_payload = {"amount": 200.00, "remarks": "Manual correction"}
    client.post(f"/api/v1/transactions/{txn_id}/correct", json=correct_payload)
    
    db_session.expire_all()
    corrected_txn = db_session.query(Transactions).filter(Transactions.id == txn_id).first()
    assert corrected_txn.status == TransactionStatus.CORRECTED
    
    # 2. Worker attempts to reprocess the same message with a different amount
    worker_payload = {
        "raw_message_id": raw_msg.id,
        "amount": Decimal("50.00"), 
        "currency": "USD",
        "txn_type": "credit",
        "hash": f"new_hash_{uuid.uuid4()}" 
    }
    
    # Simulate the background worker calling upsert_transaction
    result_txn = upsert_transaction(db_session, worker_payload, commit=True, actor_identifier="worker")
    
    # 3. Verify worker did NOT overwrite the manual correction
    db_session.expire_all()
    final_txn = db_session.query(Transactions).filter(Transactions.id == txn_id).first()
    assert final_txn.status == TransactionStatus.CORRECTED
    assert final_txn.amount == Decimal("200.00") # Maintained the corrected amount, ignored 50.00
    assert final_txn.id == result_txn.id

def test_transaction_invalidation(db_session):
    """Tests Scenario 2: Transaction Invalidation"""
    txn, _ = create_base_data(db_session)
    txn_id = txn.id
    
    invalidate_payload = {
        "reason": "Duplicate physical ledger entry"
    }
    
    # Admin invalidates transaction
    response = client.post(f"/api/v1/transactions/{txn_id}/invalidate", json=invalidate_payload)
    assert response.status_code == 200
    
    # Verify DB State
    db_session.expire_all()
    invalidated_txn = db_session.query(Transactions).filter(Transactions.id == txn_id).first()
    assert invalidated_txn.status == TransactionStatus.INVALIDATED
    assert "Duplicate physical ledger entry" in invalidated_txn.remarks
    
    # Verify Audit Log
    audit_logs = db_session.query(TransactionAudit).filter(TransactionAudit.transaction_id == txn_id).all()
    latest_audit = audit_logs[-1]
    assert latest_audit.action == TransactionAuditAction.INVALIDATED
    assert latest_audit.old_value["status"] == "review_needed"
    assert latest_audit.new_value["status"] == "invalidated"
