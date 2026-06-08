import pytest
from unittest.mock import patch, MagicMock
from app.workers.job_handler import process_webhook_batch
from app.schemas.jobs import WebhookJobPayload
from app.models.raw_messages import RawMessages
from app.models.transactions import Transactions, TransactionStatus
from app.models.transaction_audit import TransactionAudit
from app.models.audit_logs import AuditLog
from app.database.database import SessionLocal
import json
from datetime import datetime, timezone

@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.rollback()
        db.close()

@patch("app.workers.job_handler.process_extraction_batch")
def test_malformed_json_rejection_step_5(mock_extraction, db_session):
    """
    Validates Step 5: Malformed JSON output does not crash worker,
    does not create transaction, routes to review_needed with correct audit.
    """
    # Mock LLM returning garbage string instead of JSON array
    mock_extraction.return_value = {
        "raw_response": {"candidates": [{"content": {"parts": [{"text": "This is not json."}]}}]},
        "metadata": {"prompt_version": "v1.1"}
    }
    
    # Cleanup previous test runs
    db_session.query(AuditLog).filter(AuditLog.entity_id == "9001").delete()
    db_session.query(RawMessages).filter(RawMessages.id == 9001).delete()
    db_session.commit()

    raw = RawMessages(id=9001, sender_id=1, group_id=1, message_id="wamid.9001", received_at=datetime.now(timezone.utc), raw_json={"entry": [{"changes": [{"value": {"messages": [{"type": "text", "text": {"body": "Paid 150 ZMW for lunch"}, "timestamp": "1780030800"}]}}]}]}, hash="hash_9001", processed=False)
    db_session.add(raw)
    db_session.commit()

    job = WebhookJobPayload(
        job_id="test-job-9001", 
        raw_message_id=9001, 
        webhook_event_type="message", 
        message_timestamp="2026-05-29T05:00:00Z",
        participant_id=1,
        group_id=1,
        ingestion_time=datetime.now(timezone.utc)
    )
    
    results = process_webhook_batch([job])
    
    assert results["test-job-9001"] == "success" # Job completed safely without infinite retry
    
    raw = db_session.query(RawMessages).filter(RawMessages.id == 9001).first()
    assert raw.processing_status == "review_needed"
    assert raw.parsing_meta["ai_extraction"]["status"] == "AI_EXTRACTION_FAILED"
    
    txn = db_session.query(Transactions).filter(Transactions.raw_message_id == 9001).first()
    assert txn is None # No unsafe persistence
    
    audit = db_session.query(AuditLog).filter(AuditLog.entity_id == "9001").first()
    assert audit.new_state["reason"] == "AI_EXTRACTION_FAILED"

@patch("app.workers.job_handler.process_extraction_batch")
def test_strict_schema_enforcement_step_3(mock_extraction, db_session):
    """
    Validates Step 3: Missing required keys fail validation (no null-sanitization fallback).
    """
    # Missing 'amount' and 'currency'
    mock_extraction.return_value = {
        "raw_response": {"candidates": [{"content": {"parts": [{"text": json.dumps([{"id": 9002, "transaction_verb": "credit"}])}]}}]},
        "metadata": {"prompt_version": "v1.1"}
    }
    db_session.query(AuditLog).filter(AuditLog.entity_id == "9002").delete()
    db_session.query(RawMessages).filter(RawMessages.id == 9002).delete()
    db_session.commit()

    raw = RawMessages(id=9002, sender_id=1, group_id=1, message_id="wamid.9002", received_at=datetime.now(timezone.utc), raw_json={"entry": [{"changes": [{"value": {"messages": [{"type": "text", "text": {"body": "Paid 150 ZMW for lunch"}, "timestamp": "1780030800"}]}}]}]}, hash="hash_9002", processed=False)
    db_session.add(raw)
    db_session.commit()

    job = WebhookJobPayload(
        job_id="test-job-9002", 
        raw_message_id=9002, 
        webhook_event_type="message", 
        message_timestamp="2026-05-29T05:00:00Z",
        participant_id=1,
        group_id=1,
        ingestion_time=datetime.now(timezone.utc)
    )
    process_webhook_batch([job])

    raw = db_session.query(RawMessages).filter(RawMessages.id == 9002).first()
    assert raw.processing_status == "review_needed"
    
    txn = db_session.query(Transactions).filter(Transactions.raw_message_id == 9002).first()
    assert txn is None
    
    audit = db_session.query(AuditLog).filter(AuditLog.entity_id == "9002").first()
    assert audit.new_state["reason"] == "AI_EXTRACTION_FAILED"

@patch("app.workers.job_handler.process_extraction_batch")
def test_low_confidence_routing_step_4(mock_extraction, db_session):
    """
    Validates Step 4: Valid schema but low confidence correctly bypasses auto-persistence.
    """
    # Valid schema, but confidence is 0.1
    mock_extraction.return_value = {
        "raw_response": {"candidates": [{"content": {"parts": [{"text": json.dumps([{"id": 9003, "amount": 100, "currency": "ZMW", "transaction_verb": "credit", "confidence": 0.1}])}]}}]},
        "metadata": {"prompt_version": "v1.1"}
    }

    txn = db_session.query(Transactions).filter(Transactions.raw_message_id == 9003).first()
    if txn:
        db_session.query(TransactionAudit).filter(TransactionAudit.transaction_id == txn.id).delete()
        db_session.delete(txn)
    db_session.query(AuditLog).filter(AuditLog.entity_id == "9003").delete()
    db_session.query(RawMessages).filter(RawMessages.id == 9003).delete()
    db_session.commit()

    raw = RawMessages(id=9003, sender_id=1, group_id=1, message_id="wamid.9003", received_at=datetime.now(timezone.utc), raw_json={"entry": [{"changes": [{"value": {"messages": [{"type": "text", "text": {"body": "Paid 150 ZMW for lunch"}, "timestamp": "1780030800"}]}}]}]}, hash="hash_9003", processed=False)
    db_session.add(raw)
    db_session.commit()

    job = WebhookJobPayload(
        job_id="test-job-9003", 
        raw_message_id=9003, 
        webhook_event_type="message", 
        message_timestamp="2026-05-29T05:00:00Z",
        participant_id=1,
        group_id=1,
        ingestion_time=datetime.now(timezone.utc)
    )
    process_webhook_batch([job])

    raw = db_session.query(RawMessages).filter(RawMessages.id == 9003).first()
    assert raw.processing_status == "review_needed"
    assert raw.parsing_meta["ai_extraction"]["status"] == "REJECTED_LOW_CONFIDENCE"
    
    txn = db_session.query(Transactions).filter(Transactions.raw_message_id == 9003).first()
    assert txn is None
    
    audit = db_session.query(AuditLog).filter(AuditLog.entity_id == "9003").first()
    assert audit.new_state["reason"] == "LOW_CONFIDENCE"