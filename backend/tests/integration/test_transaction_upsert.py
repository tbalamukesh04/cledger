import pytest
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

from app.database.database import SessionLocal
from app.models.raw_messages import RawMessages
from app.models.participants import Participants
from app.models.groups import Groups
from app.models.transactions import Transactions, TransactionStatus
from app.schemas.jobs import WebhookJobPayload
from app.workers.job_handler import process_webhook_batch
from app.ai.config import EXTRACTION_CONFIDENCE_THRESHOLD

def setup_test_data(db, message_text: str):
    """Helper to create necessary FK relations (Participants, Groups, RawMessages)"""
    # Create Participant
    participant = Participants(phone=f"+123456789{uuid.uuid4().hex[:4]}", displayname="Test User")
    db.add(participant)
    db.commit()

    # Create Group
    group = Groups(group_id=f"test_group_{uuid.uuid4().hex[:4]}", groupname="Test Group")
    db.add(group)
    db.commit()

    # Create RawMessage
    raw_msg = RawMessages(
        tenant_id=1,
        sender_id=participant.id,
        group_id=group.id,
        message_id=f"wamid.{uuid.uuid4()}",
        raw_json={
            "entry": [{
                "changes": [{
                    "value": {
                        "messages": [{
                            "type": "text", 
                            "text": {"body": message_text}, 
                            "timestamp": str(int(datetime.now().timestamp()))
                        }]
                    }
                }]
            }]
        },
        received_at=datetime.now(timezone.utc),
        processed=False,
        hash=f"mock_hash_{uuid.uuid4().hex}"  # Added mock hash to satisfy NOT NULL constraint
    )
    db.add(raw_msg)
    db.commit()

    # Create Mock Job Payload
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
    return raw_msg.id, job

class MockExtractionResult:
    """A lightweight mock of the Pydantic extraction schema."""
    def __init__(self, amount, currency, transaction_verb, transaction_date, description, confidence_score):
        self.id = "mock_id_123"
        self.amount = amount
        self.currency = currency
        self.transaction_verb = transaction_verb
        self.transaction_date = transaction_date
        self.description = description
        self.confidence_score = confidence_score
        self.confidence = confidence_score  # satisfies LLMExtractionSchema requirements
        self.prompt_version = "v1.1"
        
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

def create_mock_extraction(amount=500.00, confidence=0.95):
    """Helper to construct standard AI extraction result schemas."""
    return MockExtractionResult(
        amount=amount,
        currency="ZMW",
        transaction_verb="credit",
        transaction_date="2026-03-23",
        description="Test transaction via AI",
        confidence_score=confidence
    )


@patch("app.workers.job_handler.get_cached_extractions_batch")
@patch("app.workers.job_handler.process_extraction_batch")
@patch("app.workers.job_handler.parse_batch_response")
def test_scenario_1_and_2_upsert_behavior(mock_parse, mock_process, mock_cache, db_session):
    """
    Scenario 1: Initial Transaction Creation
    Scenario 2: Message Reprocessing (Update instead of duplicate)
    """
    mock_cache.return_value = {}
    mock_process.return_value = "dummy_raw_llm_response"
    msg_id, job = setup_test_data(db_session, "Received 500 ZMW from John")
    
    # ---------------------------------------------------------
    # SCENARIO 1: INITIAL CREATION
    # ---------------------------------------------------------
    mock_parse.return_value = {str(msg_id): create_mock_extraction(amount=500.0, confidence=0.95)}
    
    results = process_webhook_batch([job])
    assert results[job.job_id] == "success", "Worker batch processing failed."
    
    # Verify initial creation parameters
    txn = db_session.query(Transactions).filter(Transactions.raw_message_id == msg_id).first()
    assert txn is not None
    assert float(txn.amount) == 500.0
    assert txn.status == TransactionStatus.PARSED # High confidence
    assert txn.confidence == 0.95

    # ---------------------------------------------------------
    # SCENARIO 2: MESSAGE REPROCESSING
    # ---------------------------------------------------------
    # Reset raw message so it gets picked up again by the worker
    raw_msg = db_session.query(RawMessages).filter(RawMessages.id == msg_id).first()
    raw_msg.processed = False
    db_session.commit()
    
    # Mock an improved extraction from a better LLM prompt (e.g. corrected amount and higher confidence)
    mock_parse.return_value = {str(msg_id): create_mock_extraction(amount=600.0, confidence=0.99)}
    
    results = process_webhook_batch([job])
    assert results[job.job_id] == "success"
    
    # Verify UPSERT logic (No duplicates created, existing row modified)
    txns = db_session.query(Transactions).filter(Transactions.raw_message_id == msg_id).all()
    assert len(txns) == 1, "Duplicate transaction was created during reprocessing!"
    
    updated_txn = txns[0]
    assert float(updated_txn.amount) == 600.0, "Amount was not updated during upsert."
    assert updated_txn.confidence == 0.99, "Confidence was not updated during upsert."


@patch("app.workers.job_handler.get_cached_extractions_batch")
@patch("app.workers.job_handler.process_extraction_batch")
@patch("app.workers.job_handler.parse_batch_response")
def test_scenario_3_low_confidence(mock_parse, mock_process, mock_cache, db_session):
    """
    Scenario 3: Low Confidence Extraction
    Verifies that extractions below the threshold are assigned status 'REVIEW_NEEDED'.
    """
    mock_cache.return_value = {}
    mock_process.return_value = "dummy_raw_llm_response"
    msg_id, job = setup_test_data(db_session, "Sent 100 ZMW")

    # Set mock confidence slightly below the threshold
    low_confidence = EXTRACTION_CONFIDENCE_THRESHOLD - 0.05
    mock_parse.return_value = {str(msg_id): create_mock_extraction(amount=100.0, confidence=low_confidence)}
    
    results = process_webhook_batch([job])
    assert results[job.job_id] == "success"
    
    # Verify status assignment logic
    txn = db_session.query(Transactions).filter(Transactions.raw_message_id == msg_id).first()
    assert txn is not None
    assert txn.status == TransactionStatus.REVIEW_NEEDED, "Low confidence extraction did not trigger REVIEW_NEEDED status."


@patch("app.workers.job_handler.get_cached_extractions_batch")
@patch("app.workers.job_handler.process_extraction_batch")
@patch("app.workers.job_handler.parse_batch_response")
def test_scenario_4_worker_retry(mock_parse, mock_process, mock_cache, db_session):
    """
    Scenario 4: Worker Retry
    Verifies that running the worker twice on the same message behaves identically to an upsert
    and guarantees 1-to-1 data idempotency.
    """
    mock_cache.return_value = {}
    mock_process.return_value = "dummy_raw_llm_response"
    msg_id, job = setup_test_data(db_session, "Paid 200 ZMW")
    
    mock_parse.return_value = {str(msg_id): create_mock_extraction(amount=200.0, confidence=0.90)}
    
    # First Run
    process_webhook_batch([job])
    
    # Reset raw message to simulate a forced retry, queue dead-letter return, or crash recovery
    raw_msg = db_session.query(RawMessages).filter(RawMessages.id == msg_id).first()
    raw_msg.processed = False
    db_session.commit()
    
    # Second Run (Exact same extraction mock)
    process_webhook_batch([job])
    
    # Verify strict database idempotency 
    txns = db_session.query(Transactions).filter(Transactions.raw_message_id == msg_id).all()
    assert len(txns) == 1, "Idempotency failure: Worker retry created a duplicate transaction."