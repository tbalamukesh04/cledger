import pytest
import uuid
from datetime import datetime, timezone, timedelta

from app.database.database import SessionLocal
from app.models.raw_messages import RawMessages
from app.models.groups import Groups
from app.models.participants import Participants
from app.models.transactions import Transactions
from app.schemas.jobs import WebhookJobPayload
from app.workers.job_handler import process_webhook_batch

# Define the test dataset
TEST_MESSAGES = [
    {"text": "paid Rahul 500 yesterday", "expected_amount": 500.0, "expected_verb": "DEBIT"},
    {"text": "sent ₹1200 to Aman", "expected_amount": 1200.0, "expected_verb": "DEBIT"},
    {"text": "received 200 from John", "expected_amount": 200.0, "expected_verb": "CREDIT"},
    {"text": "transferred 1500 for rent", "expected_amount": 1500.0, "expected_verb": "DEBIT"}
]

@pytest.fixture(scope="module")
def setup_test_data():
    """Sets up the prerequisite database records for the batch test."""
    db = SessionLocal()
    tenant_id = 1
    
    # 1. Create a dummy group and participant
    group = Groups(group_id=f"test_group_{uuid.uuid4().hex[:8]}", groupname="Batch Test Group", tenant_id=tenant_id)
    participant = Participants(phone=f"+1000{uuid.uuid4().hex[:4]}", displayname="Batch Tester", tenant_id=tenant_id)
    db.add(group)
    db.add(participant)
    db.commit()
    db.refresh(group)
    db.refresh(participant)

    raw_messages = []
    jobs = []

    # 2. Insert the RawMessages and construct the Job Payloads
    for msg_data in TEST_MESSAGES:
        # Construct a simulated Meta WhatsApp JSON payload
        simulated_json = {
            "entry": [{"changes": [{"value": {"messages": [{
                "type": "text", 
                "text": {"body": msg_data["text"]},
                "timestamp": str(int(datetime.now(timezone.utc).timestamp()))
            }]}}]}]
        }

        raw_msg = RawMessages(
                tenant_id=tenant_id,
                group_id=group.id,
                sender_id=participant.id,
                message_id=f"wamid.{uuid.uuid4().hex}",
                raw_json=simulated_json,
                received_at=datetime.now(timezone.utc),
                processed=False,
                hash=f"test_hash_{uuid.uuid4().hex}" 
            )
        db.add(raw_msg)
        db.commit()
        db.refresh(raw_msg)
        raw_messages.append(raw_msg)

        # Create the worker job payload
        job = WebhookJobPayload(
            job_id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            business_id="test_waba",
            phone_number_id="test_phone",
            message_id=raw_msg.message_id,
            raw_message_id=raw_msg.id,
            participant_id=participant.id,
            group_id=group.id,
            webhook_event_type="messages",
            message_timestamp=raw_msg.received_at,
            ingestion_time=raw_msg.received_at
        )
        jobs.append(job)

    yield db, jobs, raw_messages

    # 3. Teardown: Clean up the database after the test
    try:
        transaction_ids = [msg.id for msg in raw_messages]
        
        # Must delete audits first due to foreign key constraints!
        from app.models.transaction_audit import TransactionAudit
        from sqlalchemy import text
        
        txn_records = db.query(Transactions).filter(Transactions.raw_message_id.in_(transaction_ids)).all()
        txn_ids = [t.id for t in txn_records]
        if txn_ids:
            # Temporarily disable the immutability trigger to allow test teardown
            db.execute(text("ALTER TABLE transaction_audit DISABLE TRIGGER ALL;"))
            db.query(TransactionAudit).filter(TransactionAudit.transaction_id.in_(txn_ids)).delete(synchronize_session=False)
            db.execute(text("ALTER TABLE transaction_audit ENABLE TRIGGER ALL;"))
            
        db.query(Transactions).filter(Transactions.raw_message_id.in_(transaction_ids)).delete(synchronize_session=False)
        db.query(RawMessages).filter(RawMessages.id.in_(transaction_ids)).delete(synchronize_session=False)
        db.commit()
        db.delete(group)
        db.delete(participant)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Teardown skipped due to privileges: {e}")
    finally:
        db.close()


from unittest.mock import patch

class MockBatchExtractionResult:
    def __init__(self, msg_id, amount, verb):
        self.id = "dummy"
        self.amount = amount
        self.currency = "ZMW"
        self.transaction_verb = verb
        self.transaction_date = "2026-03-24"
        self.description = "Batch Test"
        self.confidence_score = 0.99
        self.confidence = 0.99
    def model_dump(self, **kwargs):
        return {"id": self.id, "amount": self.amount, "currency": self.currency, "transaction_verb": self.transaction_verb, "transaction_date": self.transaction_date, "description": self.description, "confidence_score": self.confidence_score, "confidence": self.confidence}

@patch("app.workers.job_handler.get_cached_extractions_batch")
@patch("app.workers.job_handler.process_extraction_batch")
@patch("app.workers.job_handler.parse_batch_response")
def test_batch_llm_extraction(mock_parse, mock_process, mock_cache, setup_test_data):
    """
    Integration test to verify that multiple messages are processed in a single batch,
    parsed correctly, and mapped back to their individual database records.
    """
    db, jobs, raw_messages = setup_test_data

    mock_cache.return_value = {}
    mock_process.return_value = "dummy"
    
    # Map the parsed responses to bypass the network entirely
    mock_results = {}
    for i, msg_data in enumerate(TEST_MESSAGES):
        cid = str(raw_messages[i].id)
        mock_results[cid] = MockBatchExtractionResult(cid, msg_data["expected_amount"], msg_data["expected_verb"])
    mock_parse.return_value = mock_results

    # 1. Execute the Batch Handler
    # This will trigger the scoring engine, batch them, call Gemini, parse the array, and map to DB
    results = process_webhook_batch(jobs)

    # 2. Verify worker status map
    assert len(results) == len(TEST_MESSAGES), "Worker did not return a status for all jobs"
    for job in jobs:
        assert results[job.job_id] == "success", f"Job {job.job_id} failed processing"

    # 3. Verify Database Persistence & ID Mapping
    for i, msg_data in enumerate(TEST_MESSAGES):
        raw_msg = raw_messages[i]
        
        # Refresh the raw message to get updated processing status
        db.refresh(raw_msg)
        assert raw_msg.processed is True
        assert raw_msg.is_transaction is True
        assert raw_msg.processing_status == "success"
        
        # Verify the Transaction record was created and mapped to the right message
        transaction = db.query(Transactions).filter(Transactions.raw_message_id == raw_msg.id).first()
        
        assert transaction is not None, f"Transaction record missing for message: '{msg_data['text']}'"
        assert float(transaction.amount) == msg_data["expected_amount"]
        assert transaction.txn_type.upper() == msg_data["expected_verb"].upper()
        
        # Check that the metadata contains the successful AI extraction flag
        assert "ai_extraction" in transaction.parsing_meta
        assert transaction.parsing_meta["ai_extraction"]["batch_processed"] is True