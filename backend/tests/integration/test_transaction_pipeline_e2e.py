import pytest
import uuid
from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import patch
from sqlalchemy import text
from fastapi.testclient import TestClient

from app.main import app
from app.database.database import SessionLocal
from app.models.raw_messages import RawMessages
from app.models.participants import Participants
from app.models.groups import Groups
from app.models.transactions import Transactions, TransactionStatus
from app.models.transaction_audit import TransactionAudit, TransactionAuditAction
from app.schemas.jobs import WebhookJobPayload
from app.workers.job_handler import process_webhook_batch

client = TestClient(app)

class MockExtractionResult:
    """A lightweight mock of the Pydantic extraction schema for pipeline testing."""
    def __init__(self, amount, confidence_score):
        self.id = uuid.uuid4().hex
        self.amount = amount
        self.currency = "ZMW"
        self.transaction_verb = "credit"
        self.transaction_date = "2026-03-24"
        self.description = "E2E pipeline test transaction"
        self.confidence_score = confidence_score
        self.confidence = confidence_score

    def model_dump(self, **kwargs):
        return {
            "id": self.id,
            "amount": self.amount,
            "currency": self.currency,
            "transaction_verb": self.transaction_verb,
            "transaction_date": self.transaction_date,
            "description": self.description,
            "confidence_score": self.confidence_score,
            "confidence": self.confidence
        }

def _cleanup(db, participant_id, group_id, raw_message_id, txn_id):
    """Safely cleans up records in dependency order, bypassing immutability triggers if necessary."""
    try:
        db.rollback()
        if txn_id:
            # Disable triggers temporarily to clean up immutable audit logs in the test environment
            db.execute(text("ALTER TABLE transaction_audit DISABLE TRIGGER ALL"))
            db.execute(text("DELETE FROM transaction_audit WHERE transaction_id = :id"), {"id": txn_id})
            db.execute(text("ALTER TABLE transaction_audit ENABLE TRIGGER ALL"))
            db.execute(text("DELETE FROM transactions WHERE id = :id"), {"id": txn_id})
        if raw_message_id:
            db.execute(text("DELETE FROM raw_messages WHERE id = :id"), {"id": raw_message_id})
        if group_id:
            db.execute(text("DELETE FROM groups WHERE id = :id"), {"id": group_id})
        if participant_id:
            db.execute(text("DELETE FROM participants WHERE id = :id"), {"id": participant_id})
        db.commit()
    except Exception:
        db.rollback()

@patch("app.workers.job_handler.get_cached_extractions_batch")
@patch("app.workers.job_handler.process_extraction_batch")
@patch("app.workers.job_handler.parse_batch_response")
def test_full_transaction_lifecycle_e2e(mock_parse, mock_process, mock_cache):
    """
    Simulates the entire transaction lifecycle from AI extraction to admin invalidation,
    verifying state changes and full audit trail reconstruction.
    """
    db = SessionLocal()
    mock_cache.return_value = {}
    mock_process.return_value = "dummy_llm_response"
    
    test_run_id = uuid.uuid4().hex[:8]
    txn_id = None
    
    # Prerequisite Setup
    participant = Participants(tenant_id=1, phone=f"+260{test_run_id}", displayname="E2E Tester")
    db.add(participant)
    group = Groups(tenant_id=1, group_id=f"grp_{test_run_id}", groupname="E2E Test Group")
    db.add(group)
    db.commit()
    
    raw_msg = RawMessages(
                tenant_id=1,
                sender_id=participant.id,
                group_id=group.id,
                message_id=f"msg_{test_run_id}",
                hash=f"raw_hash_{test_run_id}",
                received_at=datetime.now(timezone.utc),
                raw_json={
                    "entry": [{
                        "changes": [{
                            "value": {
                                "messages": [{
                                    "type": "text", 
                                    "text": {"body": "Received 500 ZMW for E2E Pipeline Simulation yesterday"}, 
                                    "timestamp": str(int(datetime.now().timestamp()))
                                }]
                            }
                        }]
                    }]
                },
                processed=False
            )
    db.add(raw_msg)
    db.commit()
    
    job = WebhookJobPayload(
        job_id=str(uuid.uuid4()),
        tenant_id=1,
        raw_message_id=raw_msg.id,
        webhook_event_type="messages",
        message_timestamp=datetime.now(timezone.utc),
        ingestion_time=datetime.now(timezone.utc),
        participant_id=participant.id,
        group_id=group.id
    )
    
    try:
        # -------------------------------------------------------------------
        # STEP 1: AI Extraction & Transaction Creation
        # -------------------------------------------------------------------
        mock_parse.return_value = {str(raw_msg.id): MockExtractionResult(amount=500.0, confidence_score=0.95)}
        results = process_webhook_batch([job])
        assert results[job.job_id] == "success"
        
        txn = db.query(Transactions).filter(Transactions.raw_message_id == raw_msg.id).first()
        assert txn is not None
        assert txn.status == TransactionStatus.PARSED
        assert float(txn.amount) == 500.0
        txn_id = txn.id
        
        # -------------------------------------------------------------------
        # STEP 2: Worker Reprocess (Upsert / Update)
        # -------------------------------------------------------------------
        db.expire_all()
        raw_msg_refresh = db.query(RawMessages).filter(RawMessages.id == raw_msg.id).first()
        raw_msg_refresh.processed = False
        db.commit()

        job2 = WebhookJobPayload(
            job_id=str(uuid.uuid4()),
            tenant_id=1,
            raw_message_id=raw_msg_refresh.id,
            webhook_event_type="messages",
            message_timestamp=datetime.now(timezone.utc),
            ingestion_time=datetime.now(timezone.utc),
            participant_id=participant.id,
            group_id=group.id
        )

        # Simulate an improved prompt version fixing the extraction amount 
        mock_parse.return_value = {str(raw_msg_refresh.id): MockExtractionResult(amount=600.0, confidence_score=0.98)}
        results = process_webhook_batch([job2])
        assert results[job2.job_id] == "success"
        
        db.expire_all()
        txn = db.query(Transactions).filter(Transactions.id == txn_id).first()
        assert float(txn.amount) == 600.0  # Confirms upsert behavior succeeded
        
        # -------------------------------------------------------------------
        # STEP 3: Admin Correction
        # -------------------------------------------------------------------
        correct_payload = {"amount": 750.00, "remarks": "Admin corrected amount"}
        response = client.post(f"/api/v1/transactions/{txn_id}/correct", json=correct_payload)
        assert response.status_code == 200
        
        db.expire_all()
        txn = db.query(Transactions).filter(Transactions.id == txn_id).first()
        assert txn.status == TransactionStatus.CORRECTED
        assert float(txn.amount) == 750.0
        
        # -------------------------------------------------------------------
        # STEP 4: Admin Invalidation
        # -------------------------------------------------------------------
        invalidate_payload = {"reason": "Not a valid expense"}
        response = client.post(f"/api/v1/transactions/{txn_id}/invalidate", json=invalidate_payload)
        assert response.status_code == 200
        
        db.expire_all()
        txn = db.query(Transactions).filter(Transactions.id == txn_id).first()
        assert txn.status == TransactionStatus.INVALIDATED
        
        # -------------------------------------------------------------------
        # STEP 5: Audit History Verification (The Source of Truth)
        # -------------------------------------------------------------------
        audits = db.query(TransactionAudit).filter(TransactionAudit.transaction_id == txn_id).order_by(TransactionAudit.id).all()
        
        # We expect exactly 4 sequence states: CREATED -> UPDATED -> CORRECTED -> INVALIDATED
        assert len(audits) == 4
        a_created, a_updated, a_corrected, a_invalidated = audits
        
        # Verify Creation Snapshot
        assert getattr(TransactionAuditAction, a_created.action, a_created.action) in ["created", TransactionAuditAction.CREATED.value]
        assert a_created.old_value is None
        assert float(a_created.new_value["amount"]) == 500.0
        
        # Verify Upsert Snapshot
        assert getattr(TransactionAuditAction, a_updated.action, a_updated.action) in ["updated", TransactionAuditAction.UPDATED.value]
        assert float(a_updated.old_value["amount"]) == 500.0
        assert float(a_updated.new_value["amount"]) == 600.0
        
        # Verify Correction Snapshot
        assert getattr(TransactionAuditAction, a_corrected.action, a_corrected.action) in ["corrected", TransactionAuditAction.CORRECTED.value]
        assert float(a_corrected.old_value["amount"]) == 600.0
        assert float(a_corrected.new_value["amount"]) == 750.0
        assert a_corrected.new_value["status"] in ["corrected", TransactionStatus.CORRECTED.value]
        
        # Verify Invalidation Snapshot
        assert getattr(TransactionAuditAction, a_invalidated.action, a_invalidated.action) in ["invalidated", TransactionAuditAction.INVALIDATED.value]
        assert a_invalidated.old_value["status"] in ["corrected", TransactionStatus.CORRECTED.value]
        assert a_invalidated.new_value["status"] in ["invalidated", TransactionStatus.INVALIDATED.value]
        assert "Not a valid expense" in a_invalidated.new_value["remarks"]
        
    finally:
        _cleanup(db, participant.id, group.id, raw_msg.id, txn_id)
        db.close()
