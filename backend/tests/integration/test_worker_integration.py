import pytest
from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
from collections import defaultdict

from app.database.database import SessionLocal
from app.models.participants import Participants
from app.models.groups import Groups
from app.models.raw_messages import RawMessages
from app.models.transactions import Transactions, TransactionStatus
from app.schemas.jobs import WebhookJobPayload
from app.workers.job_handler import process_webhook_batch

class MockExtractionResult:
    """Mock AI response to bypass network and Pydantic validation during integration tests"""
    def __init__(self):
        self.amount = 150.0
        self.currency = "ZMW"
        self.transaction_date = datetime.now().strftime("%Y-%m-%d")
        self.transaction_verb = "debit"
        self.description = "Groceries"
        self.confidence_score = 0.95
        self.prompt_version = "v1"
        
    def model_dump(self):
        return {
            "amount": self.amount,
            "currency": self.currency,
            "transaction_verb": self.transaction_verb,
            "description": self.description,
            "confidence_score": self.confidence_score
        }

def test_worker_transaction_persistence_integration():
    """
    Validates the end-to-end flow:
    Raw Message -> Preprocessing -> AI (Mocked) -> Status Routing -> Persistence.
    """
    # Explicitly import connected models so SQLAlchemy's mapper registry can resolve string relationships
    from app.models.users import Users
    from app.models.businesses import Businesses
    
    db = SessionLocal()
    
    # --- 1. SETUP: Create required Foreign Key entities ---
    test_phone = "9998887771_e2e"
    participant = db.query(Participants).filter_by(phone=test_phone).first()
    if not participant:
        participant = Participants(phone=test_phone, displayname="Integration Tester")
        db.add(participant)
        
    group = db.query(Groups).filter_by(group_id="integration_group_e2e").first()
    if not group:
        group = Groups(group_id="integration_group_e2e", groupname="Integration Group")
        db.add(group)

    test_business = db.query(Businesses).filter_by(meta_waba_id="worker_e2e_waba").first()
    if not test_business:
        test_business = Businesses(
            name="Worker E2E Enterprise",
            slug="worker-e2e",
            meta_waba_id="worker_e2e_waba",
            meta_phone_number_id="worker_e2e_phone",
            is_active=True
        )
        db.add(test_business)

    db.commit()
    db.refresh(test_business)

    # Create a completely fresh raw message mimicking a webhook payload
    raw_msg = RawMessages(
        tenant_id=test_business.id,
        sender_id=participant.id,
        group_id=group.id,
        message_id=f"wamid.integration_{datetime.now().timestamp()}",
        received_at=datetime.now(timezone.utc),    
        raw_json={
            "entry": [{"changes": [{"value": {"messages": [{
                "type": "text",
                "text": {"body": "Bought groceries for 150 ZMW"},
                "timestamp": str(int(datetime.now().timestamp()))
            }]}}]}]
        },
        processed=False,
        hash=f"hash_integration_{datetime.now().timestamp()}"
    )
    db.add(raw_msg)
    db.commit()
    db.refresh(raw_msg)

    # Construct the Job Payload that the Redis Queue would normally pass
    job = WebhookJobPayload(
            job_id="job_integration_001",
            tenant_id=test_business.id,
            business_id="worker_e2e_waba",
            phone_number_id="worker_e2e_phone",
            message_id=raw_msg.message_id,
            raw_message_id=raw_msg.id,
            participant_id=participant.id,
            group_id=group.id,
            webhook_event_type="messages",
            message_timestamp=datetime.now(timezone.utc),
            ingestion_time=datetime.now(timezone.utc)
        )

    # --- 2. MOCK AI EXTRACTION: Force a Cache Hit ---
    # This bypasses the Gemini network call but provides a valid extraction payload to the worker
    mock_extraction = MockExtractionResult()

    try:
        # Patch the cache function to always return our mock extraction
        with patch("app.workers.job_handler.get_cached_extractions_batch") as mock_cache:
            mock_dict = MagicMock()
            mock_dict.get.return_value = mock_extraction
            mock_cache.return_value = mock_dict
            
            # --- 3. EXECUTE: Run the batch worker ---
            results = process_webhook_batch([job])
        
        # --- 4. ASSERTIONS: Validate the complete pipeline ---
        assert results[job.job_id] == "success", "Worker failed to process the job"

        # Verify the database persistence and mapping
        txn = db.query(Transactions).filter(Transactions.raw_message_id == raw_msg.id).first()
        
        assert txn is not None, "Worker did not persist the transaction to the database"
        assert txn.amount == Decimal("150.00"), "Amount incorrectly mapped"
        assert txn.currency == "ZMW", "Currency incorrectly mapped"
        assert txn.txn_type == "debit", "Transaction type incorrectly mapped"
        assert txn.remarks == "Groceries", "Remarks incorrectly mapped"
        assert txn.status == TransactionStatus.PARSED, "Status not correctly assigned based on >0.65 confidence"
        assert txn.confidence == 0.95, "Confidence score incorrectly mapped"
        assert txn.created_at is not None, "Timestamps were not auto-generated"
        
        # --- 5. VALIDATE UNIQUENESS ENFORCEMENT ---
        # Reset the processed flag to simulate the same message re-entering the pipeline
        db.refresh(raw_msg)
        raw_msg.processed = False
        db.commit()
        
        with patch("app.workers.job_handler.get_cached_extractions_batch") as mock_cache_2:
            mock_dict_2 = MagicMock()
            mock_dict_2.get.return_value = mock_extraction
            mock_cache_2.return_value = mock_dict_2
            duplicate_results = process_webhook_batch([job])
            
        # The worker should catch the ValueError from the CRUD layer safely, skipping DB insertion
        assert duplicate_results[job.job_id] == "success"
        
        # Ensure only 1 transaction exists for this message
        txn_count = db.query(Transactions).filter(Transactions.raw_message_id == raw_msg.id).count()
        assert txn_count == 1, "Uniqueness constraint failed: Duplicate transaction created!"

    finally:
       # --- 6. CLEANUP ---
        # Use rollback to clear the session state. 
        # Delete is blocked by Postgres immutable audit triggers.
        db.rollback()