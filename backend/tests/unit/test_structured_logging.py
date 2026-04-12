import pytest
import json
import logging
import io
from app.config.logging_config import JSONFormatter, request_id_ctx, job_id_ctx
from app.utils.logger import log_event, log_error, bind_context, logger as app_logger
from app.core.log_events import LogEvent

@pytest.fixture
def capture_logs():
    """
    Fixture to capture JSON formatted logs in memory during tests.
    """
    # Create an in-memory text buffer
    log_buffer = io.StringIO()
    handler = logging.StreamHandler(log_buffer)
    handler.setFormatter(JSONFormatter())
    
    # Attach directly to the specific logger instance used by our utility
    app_logger.setLevel(logging.INFO)
    
    # Clear existing handlers to prevent double logging to console during tests
    old_handlers = app_logger.handlers[:]
    app_logger.handlers.clear()
    app_logger.addHandler(handler)
    
    yield log_buffer
    
    # Cleanup
    app_logger.handlers = old_handlers
    request_id_ctx.set(None)
    job_id_ctx.set(None)
    
def parse_logs(log_buffer: io.StringIO):
    """Parses the newline-separated JSON logs from the buffer."""
    lines = log_buffer.getvalue().strip().split('\n')
    return [json.loads(line) for line in lines if line]

def test_webhook_receipt_and_pii_redaction(capture_logs):
    """
    Simulates a webhook receipt and verifies that PII fields 
    are properly redacted before being written to the log.
    """
    bind_context(request_id="req-12345")
    
    log_event(
        LogEvent.WEBHOOK_RECEIVED,
        "Payload Extracted",
        phone_number="+1234567890",
        email="test@example.com",
        name="John Doe",
        msg_type="text",
        raw_message_text="I paid 50 ZMW for lunch",
        status="success"
    )
    
    logs = parse_logs(capture_logs)
    assert len(logs) == 1
    log = logs[0]
    
    # Verify base schema
    assert log["event"] == LogEvent.WEBHOOK_RECEIVED.value
    assert log["request_id"] == "req-12345"
    assert "timestamp" in log
    
    # Verify PII Redaction
    assert log["phone_number"] == "***REDACTED***"
    assert log["email"] == "***REDACTED***"
    assert log["name"] == "***REDACTED***"
    assert log["raw_message_text"] == "***REDACTED***"
    
    # Verify non-PII is kept
    assert log["msg_type"] == "text"
    assert log["status"] == "success"

def test_worker_job_lifecycle_and_transaction_creation(capture_logs):
    """
    Simulates the worker picking up a job, creating a transaction,
    and finishing the job, checking correlation IDs.
    """
    bind_context(job_id="job-999")
    
    log_event(LogEvent.JOB_STARTED, "Executing batch", size=1)
    
    log_event(
        LogEvent.TRANSACTION_CREATED,
        "Confidence Routing Decision Made",
        raw_message_id="msg-abc",
        confidence=0.95,
        status="parsed"
    )
    
    logs = parse_logs(capture_logs)
    assert len(logs) == 2
    
    assert logs[0]["event"] == LogEvent.JOB_STARTED.value
    assert logs[0]["job_id"] == "job-999"
    assert logs[0]["size"] == 1
    
    assert logs[1]["event"] == LogEvent.TRANSACTION_CREATED.value
    assert logs[1]["job_id"] == "job-999"
    assert logs[1]["confidence"] == 0.95

def test_llm_call_success_and_failure(capture_logs):
    """
    Simulates LLM interactions, verifying the error capturing utility.
    """
    bind_context(job_id="job-llm-1")
    
    # Success
    log_event(LogEvent.LLM_CALLED, "Successfully received response", duration_ms=1200)
    
    # Failure simulation
    try:
        raise ValueError("Gemini API Timeout")
    except Exception as e:
        log_error(LogEvent.LLM_ERROR, error=e, message="Error calling Gemini API for batch")
        
    logs = parse_logs(capture_logs)
    assert len(logs) == 2
    
    assert logs[0]["event"] == LogEvent.LLM_CALLED.value
    assert logs[0]["duration_ms"] == 1200
    
    error_log = logs[1]
    assert error_log["event"] == LogEvent.LLM_ERROR.value
    assert error_log["error_type"] == "ValueError"
    assert error_log["error_details"] == "Gemini API Timeout"
    assert "exception" in error_log  # Traceback string should be injected

def test_review_action_audit(capture_logs):
    """
    Simulates an admin reviewing and correcting a transaction.
    """
    bind_context(request_id="req-admin-55")
    
    log_event(
        LogEvent.REVIEW_FLAGGED, 
        "Transaction successfully corrected by admin", 
        transaction_id="txn-10", 
        status="corrected"
    )
    
    logs = parse_logs(capture_logs)
    assert len(logs) == 1
    assert logs[0]["event"] == LogEvent.REVIEW_FLAGGED.value
    assert logs[0]["request_id"] == "req-admin-55"
    assert logs[0]["transaction_id"] == "txn-10"
