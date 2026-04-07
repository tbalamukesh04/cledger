import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
from sqlalchemy.exc import IntegrityError

from app.utils.idempotency import generate_idempotency_key
from app.workers.job_handler import process_webhook_batch

def test_generate_idempotency_key_wamid():
    """Test exact WAMID extraction for basic deduplication."""
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"value": {"messages": [{"id": "wamid.123"}]}}]}]
    }
    key = generate_idempotency_key(payload)
    assert key == "idem_msg_wamid.123"

def test_generate_idempotency_key_status():
    """Test exact status ID extraction."""
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"value": {"statuses": [{"id": "stat.456"}]}}]}]
    }
    key = generate_idempotency_key(payload)
    assert key == "idem_stat_stat.456"

def test_generate_idempotency_key_fallback():
    """Test fallback hash generation for malformed/unusual payloads."""
    payload = {"invalid_schema": True, "data": "test"}
    key1 = generate_idempotency_key(payload)
    key2 = generate_idempotency_key(payload)
    
    assert key1.startswith("idem_hash_")
    assert key1 == key2  # Must be deterministic

@patch('app.workers.job_handler.SessionLocal')
def test_worker_already_processed_skip(mock_session_local):
    """Test Scenario 3: Worker marks job as success if DB record is already processed."""
    mock_db = MagicMock()
    mock_session_local.return_value = mock_db
    
    # Create a flexible query mock using the new .all() batch execution
    mock_query = MagicMock()
    mock_db.query.return_value = mock_query
    mock_query.options.return_value = mock_query
    mock_query.filter.return_value = mock_query
    
    # Simulate a message that has already been processed
    mock_msg = MagicMock()
    mock_msg.id = 999
    mock_msg.processed = True
    mock_query.all.return_value = [mock_msg]
    
    mock_job = MagicMock()
    mock_job.job_id = "job_123"
    mock_job.raw_message_id = 999
    
    # Worker takes a list of jobs now
    results = process_webhook_batch([mock_job])
    
    # Ensure it returns success for the skipped job and still commits the batch state
    assert results["job_123"] == "success"
    mock_db.commit.assert_called_once()

@patch('app.workers.job_handler.SessionLocal')
def test_worker_content_hash_collision(mock_session_local):
    """Test Scenario 2: Worker safely catches IntegrityError on duplicate DB commits."""
    mock_db = MagicMock()
    mock_session_local.return_value = mock_db
    
    mock_query = MagicMock()
    mock_db.query.return_value = mock_query
    mock_query.options.return_value = mock_query
    mock_query.filter.return_value = mock_query
    
    # Simulate a non-transaction message that is NOT yet processed
    mock_msg = MagicMock()
    mock_msg.id = 999
    mock_msg.processed = False
    mock_msg.raw_json = {
        "entry": [{"changes": [{"value": {
            "messages": [{"type": "text", "text": {"body": "hello world"}, "timestamp": "123"}]
        }}]}]
    }
    mock_msg.sender = None
    mock_msg.group = None
    mock_msg.received_at = datetime.now(timezone.utc)
    mock_msg.message_id = "mock_wamid_123"
    mock_msg.hash = "old_hash"
    
    mock_query.all.return_value = [mock_msg]
    
    # Force an IntegrityError when the worker attempts to commit the batch
    mock_db.commit.side_effect = IntegrityError("duplicate key", params={}, orig=Exception())
    
    mock_job = MagicMock()
    mock_job.job_id = "job_123"
    mock_job.raw_message_id = 999
    mock_job.webhook_event_type = "text"
    
    results = process_webhook_batch([mock_job])
        
    # Verify rollback was called and the specific job was marked for retry
    mock_db.rollback.assert_called_once()
    assert results["job_123"] == "retry"

@patch('app.workers.job_handler.SessionLocal')
def test_worker_missing_keys_graceful_handling(mock_session_local):
    """Test Scenario 4: Worker gracefully handles completely empty/malformed JSON without crashing."""
    mock_db = MagicMock()
    mock_session_local.return_value = mock_db
    
    mock_query = MagicMock()
    mock_db.query.return_value = mock_query
    mock_query.options.return_value = mock_query
    mock_query.filter.return_value = mock_query
    
    # Simulate a message with NO nested entry/changes/messages keys
    mock_msg = MagicMock()
    mock_msg.id = 999
    mock_msg.processed = False
    mock_msg.raw_json = {}  # Entirely empty payload
    mock_msg.sender = None
    mock_msg.group = None
    mock_msg.received_at = datetime.now(timezone.utc)
    mock_msg.message_id = "wamid.null_test"
    mock_msg.hash = "old_hash"
    mock_msg.parsing_meta = None
    
    mock_query.all.return_value = [mock_msg]
    
    mock_job = MagicMock()
    mock_job.job_id = "job_123"
    mock_job.raw_message_id = 999
    mock_job.webhook_event_type = "text"
    
    # Process the job
    results = process_webhook_batch([mock_job])
    
    # It should score 0, bypass the AI entirely, not crash, and mark as success (NON_TRANSACTION)
    assert results["job_123"] == "success"
    assert mock_msg.processing_status == "NON_TRANSACTION"
    mock_db.commit.assert_called_once()