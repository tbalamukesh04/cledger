import pytest
from unittest.mock import patch, MagicMock
from app.workers.job_handler import process_webhook_batch
from app.schemas.jobs import WebhookJobPayload
from app.models.raw_messages import RawMessages
from app.models.transactions import Transactions, TransactionStatus
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
    
    # Assuming job payload and raw_message ID 1 exists in test DB setup
    # Cleanup previous test runs
    db_session.query(Transactions).filter(Transactions.raw_message_id == 1).delete()
    db_session.query(AuditLog).filter(AuditLog.entity_id == "1").delete()
    db_session.query(RawMessages).filter(RawMessages.id == 1).delete()
    db_session.commit()

    raw = RawMessages(id=1, sender_id=1, group_id=1, message_id="wamid.1", received_at=datetime.now(timezone.utc), raw_json={"entry": [{"changes": [{"value": {"messages": [{"type": "text", "text": {"body": "Test"}, "timestamp": "1672531200"}]}}]}]}, hash="hash_1", processed=False)
    db_session.add(raw)
    db_session.commit()

    job = WebhookJobPayload(
        job_id="test-job-1", 
        raw_message_id=1, 
        webhook_event_type="message", 
        message_timestamp="2026-05-29T10:00:00Z",
        participant_id=1,
        group_id=1,
        ingestion_time=datetime.now(timezone.utc)
    )
    
    results = process_webhook_batch([job])
    
    assert results["test-job-1"] == "success" # Job completed safely without infinite retry
    
    raw = db_session.query(RawMessages).filter(RawMessages.id == 1).first()
    assert raw.processing_status == "review_needed"
    assert raw.parsing_meta["ai_extraction"]["status"] == "AI_EXTRACTION_FAILED"
    
    txn = db_session.query(Transactions).filter(Transactions.raw_message_id == 1).first()
    assert txn is None # No unsafe persistence
    
    audit = db_session.query(AuditLog).filter(AuditLog.entity_id == "1").first()
    assert audit.new_state["reason"] == "LLM_SCHEMA_INVALID"

@patch("app.workers.job_handler.process_extraction_batch")
def test_strict_schema_enforcement_step_3(mock_extraction, db_session):
    """
    Validates Step 3: Missing required keys fail validation (no null-sanitization fallback).
    """
    # Missing 'amount' and 'currency'
    mock_extraction.return_value = {
        "raw_response": {"candidates": [{"content": {"parts": [{"text": json.dumps([{"id": 2, "transaction_verb": "credit"}])}]}}]},
        "metadata": {"prompt_version": "v1.1"}
    }
    
    db_session.query(Transactions).filter(Transactions.raw_message_id == 2).delete()
    db_session.query(AuditLog).filter(AuditLog.entity_id == "2").delete()
    db_session.query(RawMessages).filter(RawMessages.id == 2).delete()
    db_session.query(AuditLog).filter(AuditLog.entity_id == "2").delete()
    db_session.query(RawMessages).filter(RawMessages.id == 2).delete()
    db_session.commit()

    raw = RawMessages(id=2, sender_id=1, group_id=1, message_id="wamid.2", received_at=datetime.now(timezone.utc), raw_json={"entry": [{"changes": [{"value": {"messages": [{"type": "text", "text": {"body": "Test"}, "timestamp": "1672531200"}]}}]}]}, hash="hash_2", processed=False)
    db_session.add(raw)
    db_session.commit()

    job = WebhookJobPayload(
        job_id="test-job-2", 
        raw_message_id=2, 
        webhook_event_type="message", 
        message_timestamp="2026-05-29T10:00:00Z",
        participant_id=1,
        group_id=1,
        ingestion_time=datetime.now(timezone.utc)
    )
    process_webhook_batch([job])
    
    raw = db_session.query(RawMessages).filter(RawMessages.id == 2).first()
    assert raw.processing_status == "review_needed"
    
    txn = db_session.query(Transactions).filter(Transactions.raw_message_id == 2).first()
    assert txn is None
    
    audit = db_session.query(AuditLog).filter(AuditLog.entity_id == "2").first()
    assert audit.new_state["reason"] == "LLM_SCHEMA_INVALID"

@patch("app.workers.job_handler.process_extraction_batch")
def test_low_confidence_routing_step_4(mock_extraction, db_session):
    """
    Validates Step 4: Valid schema but low confidence correctly bypasses auto-persistence.
    """
    # Valid schema, but confidence is 0.1
    mock_extraction.return_value = {
        "raw_response": {"candidates": [{"content": {"parts": [{"text": json.dumps([{"id": 3, "amount": 100, "currency": "ZMW", "transaction_verb": "credit", "confidence_score": 0.1}])}]}}]},
        "metadata": {"prompt_version": "v1.1"}
    }
    
    db_session.query(Transactions).filter(Transactions.raw_message_id == 3).delete()
    db_session.query(AuditLog).filter(AuditLog.entity_id == "3").delete()
    db_session.query(RawMessages).filter(RawMessages.id == 3).delete()
    db_session.commit()

    raw = RawMessages(id=3, sender_id=1, group_id=1, message_id="wamid.3", received_at=datetime.now(timezone.utc), raw_json={"entry": [{"changes": [{"value": {"messages": [{"type": "text", "text": {"body": "Test"}, "timestamp": "1672531200"}]}}]}]}, hash="hash_3", processed=False)
    db_session.add(raw)
    db_session.commit()

    job = WebhookJobPayload(
        job_id="test-job-3", 
        raw_message_id=3, 
        webhook_event_type="message", 
        message_timestamp="2026-05-29T10:00:00Z",
        participant_id=1,
        group_id=1,
        ingestion_time=datetime.now(timezone.utc)
    )
    process_webhook_batch([job])
    
    raw = db_session.query(RawMessages).filter(RawMessages.id == 3).first()
    assert raw.processing_status == "review_needed"
    assert raw.parsing_meta["ai_extraction"]["status"] == "REJECTED_LOW_CONFIDENCE"
    
    txn = db_session.query(Transactions).filter(Transactions.raw_message_id == 3).first()
    assert txn is None
    
    audit = db_session.query(AuditLog).filter(AuditLog.entity_id == "3").first()
    assert audit.new_state["reason"] == "LOW_CONFIDENCE"