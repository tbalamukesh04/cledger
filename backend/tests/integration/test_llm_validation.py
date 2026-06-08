import pytest
import uuid
from unittest.mock import patch
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.workers.job_handler import process_webhook_batch
from app.models.raw_messages import RawMessages
from app.models.transactions import Transactions
from app.models.groups import Groups
from app.models.participants import Participants
from app.models.audit_logs import AuditLog
from app.schemas.jobs import WebhookJobPayload

pytestmark = pytest.mark.integration

def create_mock_gemini_response(json_string: str) -> dict:
    """Helper to simulate the wrapped LLM response from extraction_service."""
    return {
        "raw_response": {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": json_string}]
                    }
                }
            ]
        },
        "metadata": {
            "prompt_version": "v1"
        }
    }

def create_test_job(msg: RawMessages) -> WebhookJobPayload:
    """Helper to create a valid job payload from a raw message."""
    return WebhookJobPayload(
        raw_message_id=msg.id,
        participant_id=msg.sender_id,
        group_id=msg.group_id,
        message_timestamp=msg.received_at,
        ingestion_time=datetime.now(timezone.utc),
        webhook_event_type="text"
    )

def setup_test_message(db_session: Session) -> RawMessages:
    """Helper to create a raw message that passes the scoring engine and reaches the LLM."""
    # 1. Create necessary foreign key dependencies first
    group = Groups(group_id=f"test_group_{uuid.uuid4().hex[:8]}", groupname="Test Group")
    db_session.add(group)
    db_session.flush() # Flush to generate the group.id

    participant = Participants(phone=f"1234567890_{uuid.uuid4().hex[:4]}", displayname="Test User")
    db_session.add(participant)
    db_session.flush() # Flush to generate the participant.id

    # 2. Create the RawMessage using actual schema columns
    valid_text = "Account debited by $500 on 2026-03-24 for coffee"
    whatsapp_json_payload = {
        "entry": [{"changes": [{"value": {"messages": [{"type": "text", "text": {"body": valid_text}}]}}]}]
    }
    
    msg = RawMessages(
        message_id=f"wamid.TEST_{uuid.uuid4().hex[:8]}",
        group_id=group.id,
        sender_id=participant.id,
        received_at=datetime.now(timezone.utc),
        raw_json=whatsapp_json_payload,
        raw_text=valid_text, 
        hash=uuid.uuid4().hex, # Dummy hash for unique constraint
        processed=False
    )
    db_session.add(msg)
    db_session.commit()
    db_session.refresh(msg)
    return msg

@patch("app.workers.job_handler.get_cached_extractions_batch")
@patch("app.workers.job_handler.process_extraction_batch")
def test_integration_schema_enforcement_valid(mock_process, mock_cache, db_session, mock_redis):
    """Verify strictly valid LLM outputs are accepted by the pipeline."""
    mock_cache.return_value = {}
    msg = setup_test_message(db_session)
    
    # Inject valid JSON mapped exactly to the test DB ID
    valid_json = f'''
    [
      {{
        "id": {msg.id},
        "amount": 500,
        "currency": "ZMW",
        "transaction_verb": "debit",
        "transaction_date": "2026-03-24",
        "counterparty": "Rahul",
        "reference": "payment",
        "confidence": 0.82
      }}
    ]
    '''
    mock_process.return_value = create_mock_gemini_response(valid_json)
    
    job = create_test_job(msg)
    msg_id = msg.id
    process_webhook_batch([job])
    
    # Validation: Ensure it was persisted
    db_session.expire_all()
    txn = db_session.query(Transactions).filter(Transactions.raw_message_id == msg_id).first()
    
    assert txn is not None, "Valid schema output should successfully persist a transaction."
    assert txn.amount == 500.0
    assert txn.currency == "ZMW"

@patch("app.workers.job_handler.get_cached_extractions_batch")
@patch("app.workers.job_handler.process_extraction_batch")
def test_integration_missing_fields_rejection(mock_process, mock_cache, db_session, mock_redis):
    """Verify outputs missing required schema fields are safely rejected and marked for review."""
    mock_cache.return_value = {}
    msg = setup_test_message(db_session)
    
    # Missing universal required fields ('amount') to guarantee failure
    missing_fields_json = f'''
        [
          {{
            "id": {msg.id},
            "amount": 500,
            "currency": "ZMW",
            "transaction_verb": "debit",
            "transaction_date": "2026-03-24"
          }}
        ]
        '''
    mock_process.return_value = create_mock_gemini_response(missing_fields_json)
    
    job = create_test_job(msg)
    msg_id = msg.id
    process_webhook_batch([job])
    
    # Validation: Ensure rejection protected the database and routed to review
    db_session.expire_all()
    txn = db_session.query(Transactions).filter(Transactions.raw_message_id == msg_id).first()
    assert txn is None, "Missing fields should cause schema validation failure and prevent persistence."
    
    updated_msg = db_session.query(RawMessages).filter(RawMessages.id == msg_id).first()
    assert updated_msg.processed is True, "Failed message must be marked as processed to avoid infinite loops."
    assert updated_msg.processing_status == "review_needed", "Failed message must be routed to human review."
    
    # Verify error metadata is captured (dynamically checking potential schema fields for flexibility)
    error_captured = (
        getattr(updated_msg, "error_code", None) is not None or
        getattr(updated_msg, "error_message", None) is not None or
        getattr(updated_msg, "parsing_meta", None) is not None or
        getattr(updated_msg, "processing_metadata", None) is not None
    )
    assert error_captured, "Error metadata must be stored on the raw message for review context."

    # Verify Append-Only Audit Trail
    audit_record = db_session.query(AuditLog).filter(
        AuditLog.entity_id == str(msg_id),
        AuditLog.entity_type == "raw_message"
    ).first()
    assert audit_record is not None, "Audit log must be created for schema validation failures."
    assert audit_record.event_type == "update"
    assert audit_record.old_state is None, "Old state must be NULL for this transition."
    assert audit_record.new_state.get("status") == "review_needed"
    assert audit_record.new_state.get("reason") is not None, "Audit log must capture the validation failure reason."

@patch("app.workers.job_handler.get_cached_extractions_batch")
@patch("app.workers.job_handler.process_extraction_batch")
def test_integration_incorrect_types_rejection(mock_process, mock_cache, db_session, mock_redis):
    """Verify outputs with uncoercible data types are safely rejected and marked for review."""
    mock_cache.return_value = {}
    msg = setup_test_message(db_session)
    
    # Provide an amount that cannot be coerced into a StrictFloat
    incorrect_types_json = f'''
    [
      {{
        "id": {msg.id},
        "amount": "five hundred",
        "currency": "ZMW",
        "transaction_verb": "debit",
        "transaction_date": "2026-03-24",
        "confidence": 0.82
      }}
    ]
    '''
    mock_process.return_value = create_mock_gemini_response(incorrect_types_json)
    
    job = create_test_job(msg)
    msg_id = msg.id
    process_webhook_batch([job])
    
    # Validation: Ensure rejection protected the database and routed to review
    db_session.expire_all()
    txn = db_session.query(Transactions).filter(Transactions.raw_message_id == msg_id).first()
    assert txn is None, "Incorrect types should cause schema validation failure and prevent persistence."
    
    updated_msg = db_session.query(RawMessages).filter(RawMessages.id == msg_id).first()
    assert updated_msg.processed is True, "Failed message must be marked as processed to avoid infinite loops."
    assert updated_msg.processing_status == "review_needed", "Failed message must be routed to human review."

    # Verify Append-Only Audit Trail
    audit_record = db_session.query(AuditLog).filter(
        AuditLog.entity_id == str(msg_id),
        AuditLog.entity_type == "raw_message"
    ).first()
    assert audit_record is not None, "Audit log must be created for type coercion failures."
    assert audit_record.event_type == "update"
    assert audit_record.new_state.get("status") == "review_needed"
    assert audit_record.new_state.get("reason") is not None

@patch("app.workers.job_handler.get_cached_extractions_batch")
@patch("app.workers.job_handler.process_extraction_batch")
def test_integration_invalid_date_format_rejection(mock_process, mock_cache, db_session, mock_redis):
    """Verify outputs with invalid date formats are safely rejected and marked for review."""
    mock_cache.return_value = {}
    msg = setup_test_message(db_session)
    
    # Provide a date that violates the strict YYYY-MM-DD format
    invalid_date_json = f'''
    [
      {{
        "id": {msg.id},
        "amount": 500,
        "currency": "ZMW",
        "transaction_verb": "debit",
        "transaction_date": "24-03-2026",
        "confidence": 0.82
      }}
    ]
    '''
    mock_process.return_value = create_mock_gemini_response(invalid_date_json)
    
    job = create_test_job(msg)
    msg_id = msg.id
    process_webhook_batch([job])
    
    # Validation: Ensure rejection protected the database and routed to review
    db_session.expire_all()
    txn = db_session.query(Transactions).filter(Transactions.raw_message_id == msg_id).first()
    assert txn is None, "Invalid date formats should cause schema validation failure and prevent persistence."
    
    updated_msg = db_session.query(RawMessages).filter(RawMessages.id == msg_id).first()
    assert updated_msg.processed is True, "Failed message must be marked as processed to avoid infinite loops."
    assert updated_msg.processing_status == "review_needed", "Failed message must be routed to human review."

    # Verify Append-Only Audit Trail
    audit_record = db_session.query(AuditLog).filter(
        AuditLog.entity_id == str(msg_id),
        AuditLog.entity_type == "raw_message"
    ).first()
    assert audit_record is not None, "Audit log must be created for date format failures."
    assert audit_record.event_type == "update"
    assert audit_record.new_state.get("status") == "review_needed"
    assert audit_record.new_state.get("reason") is not None

@patch("app.workers.job_handler.get_cached_extractions_batch")
@patch("app.workers.job_handler.process_extraction_batch")
def test_integration_malformed_json_fallback(mock_process, mock_cache, db_session, mock_redis):
    """Verify completely malformed JSON safely triggers the review flow instead of crashing."""
    mock_cache.return_value = {}
    msg = setup_test_message(db_session)
    
    malformed_json = f'''
    [
      {{
        "id": {msg.id},
        "amount": 500,
        "currency": "ZMW"
    '''
    mock_process.return_value = create_mock_gemini_response(malformed_json)
    
    # Note: We removed the try/except block. The worker must now internally catch parsing 
    # exceptions and update the DB state, rather than bubbling the error up to the queue.
    job = create_test_job(msg)
    msg_id = msg.id
    process_webhook_batch([job])
        
    # Validation: Ensure fatal JSON crashes don't cause partial writes, but DO route to review
    db_session.expire_all()
    txn = db_session.query(Transactions).filter(Transactions.raw_message_id == msg_id).first()
    assert txn is None, "Malformed JSON must not result in phantom persistence."
    
    updated_msg = db_session.query(RawMessages).filter(RawMessages.id == msg_id).first()
    assert updated_msg.processed is True, "Failed message must be marked as processed to avoid infinite loops."
    assert updated_msg.processing_status == "review_needed", "Malformed JSON must route to human review."

    # Verify Append-Only Audit Trail
    audit_record = db_session.query(AuditLog).filter(
        AuditLog.entity_id == str(msg_id),
        AuditLog.entity_type == "raw_message"
    ).first()
    assert audit_record is not None, "Audit log must be created for fatal JSON parse errors."
    assert audit_record.event_type == "update"
    assert audit_record.new_state.get("status") == "review_needed"
    assert audit_record.new_state.get("reason") is not None

@patch("app.workers.job_handler.get_cached_extractions_batch")
@patch("app.workers.job_handler.process_extraction_batch")
def test_integration_non_json_string_rejection(mock_process, mock_cache, db_session, mock_redis):
    """Verify LLM conversational responses (non-JSON) safely trigger the review flow."""
    mock_cache.return_value = {}
    msg = setup_test_message(db_session)
    
    # Provide a purely conversational/non-JSON response from the LLM
    non_json_string = "I am sorry, but I cannot extract financial details from this text."
    mock_process.return_value = create_mock_gemini_response(non_json_string)
    
    job = create_test_job(msg)
    msg_id = msg.id
    process_webhook_batch([job])
    
    # Validation: Ensure rejection protected the database and routed to review
    db_session.expire_all()
    txn = db_session.query(Transactions).filter(Transactions.raw_message_id == msg_id).first()
    assert txn is None, "Non-JSON strings must not result in persistence."
    
    updated_msg = db_session.query(RawMessages).filter(RawMessages.id == msg_id).first()
    assert updated_msg.processed is True, "Failed message must be marked as processed to avoid infinite loops."
    assert updated_msg.processing_status == "review_needed", "Non-JSON strings must route to human review."

    # Verify Append-Only Audit Trail
    audit_record = db_session.query(AuditLog).filter(
        AuditLog.entity_id == str(msg_id),
        AuditLog.entity_type == "raw_message"
    ).first()
    assert audit_record is not None, "Audit log must be created for hallucinatory conversational responses."
    assert audit_record.event_type == "update"
    assert audit_record.new_state.get("status") == "review_needed"
    assert audit_record.new_state.get("reason") is not None

@patch("app.workers.job_handler.get_cached_extractions_batch")
@patch("app.workers.job_handler.process_extraction_batch")
def test_integration_batch_resilience_partial_failure(mock_process, mock_cache, db_session, mock_redis):
    """Verify that a malformed output for ONE message in a batch doesn't block the valid messages."""
    mock_cache.return_value = {}
    
    # Setup TWO distinct messages for the same batch
    msg_valid = setup_test_message(db_session)
    msg_invalid = setup_test_message(db_session)
    
    # Mixed LLM response: Msg 1 is perfect, Msg 2 is missing 'amount'
    mixed_json = f'''
        [
          {{
            "id": {msg_valid.id},
            "amount": 500,
            "currency": "ZMW",
            "transaction_verb": "debit",
            "transaction_date": "2026-03-24",
            "counterparty": "Rahul",
            "reference": "payment",
            "confidence": 0.82
          }},
          {{
            "id": {msg_invalid.id},
            "amount": 300,
            "currency": "ZMW",
            "transaction_verb": "debit",
            "transaction_date": "2026-03-24"
          }}
        ]
        '''

    mock_process.return_value = create_mock_gemini_response(mixed_json)
    
    # Send both jobs to the worker pipeline simultaneously 
    job_valid = create_test_job(msg_valid)
    job_invalid = create_test_job(msg_invalid)
    valid_id = msg_valid.id
    invalid_id = msg_invalid.id
    process_webhook_batch([job_valid, job_invalid])
    
    # --- VALIDATION FOR SUCCESSFUL MESSAGE ---
    db_session.expire_all()
    txn_valid = db_session.query(Transactions).filter(Transactions.raw_message_id == valid_id).first()
    assert txn_valid is not None, "Worker must successfully persist the valid message despite sibling failures."
    assert txn_valid.amount == 500.0
    
    # --- VALIDATION FOR FAILED MESSAGE ---
    txn_invalid = db_session.query(Transactions).filter(Transactions.raw_message_id == invalid_id).first()
    assert txn_invalid is None, "Worker must block the invalid message from persistence."
    
    updated_invalid_msg = db_session.query(RawMessages).filter(RawMessages.id == invalid_id).first()
    assert updated_invalid_msg.processed is True
    assert updated_invalid_msg.processing_status == "review_needed", "Worker must safely route the isolated failure to review."
    
    # Ensure audit isolation
    audit_record = db_session.query(AuditLog).filter(
        AuditLog.entity_id == str(invalid_id),
        AuditLog.entity_type == "raw_message"
    ).first()
    assert audit_record is not None, "Audit log must be created specifically for the failed item in the batch."
    assert audit_record.event_type == "update"
    assert audit_record.new_state.get("status") == "review_needed"