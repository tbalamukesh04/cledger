import pytest
from datetime import datetime, timezone
from unittest.mock import patch

from app.database.database import SessionLocal
from app.models.raw_messages import RawMessages
from app.models.transactions import Transactions, TransactionStatus
from app.models.groups import Groups
from app.models.participants import Participants
from app.models.transaction_audit import TransactionAudit
from app.schemas.jobs import WebhookJobPayload
from app.workers.job_handler import process_webhook_batch
from app.schemas.llm_extraction import LLMExtractionSchema

def test_confidence_routing_high_confidence(db_session):
    """
    Test that an extraction with confidence >= threshold (0.82 >= 0.65)
    is routed to the 'accepted' status automatically.
    """
    # Setup test data
    group = Groups(group_id="group_high", groupname="Test Group")
    participant = Participants(phone="1111111111", displayname="Test User 1")
    db_session.add_all([group, participant])
    db_session.commit()

    raw_msg = RawMessages(
            message_id="wamid.test_high",
            sender_id=participant.id,
            group_id=group.id,
            raw_json={"entry": [{"changes": [{"value": {"messages": [{"type": "text", "text": {"body": "Paid K500 for lunch"}, "timestamp": "1710921000"}]}}]}]},
            received_at=datetime.now(timezone.utc),
            hash="test_hash_high"
        )
    db_session.add(raw_msg)
    db_session.commit()

    # Extract the integer ID now so we don't access the detached ORM object later
    raw_msg_id = raw_msg.id

    job = WebhookJobPayload(
        job_id="job_high",
        raw_message_id=raw_msg_id,
        participant_id=participant.id,
        group_id=group.id,
        webhook_event_type="text",
        message_timestamp=datetime.now(timezone.utc),
        ingestion_time=datetime.now(timezone.utc)
    )

    # Mock the LLM to return high confidence
    mock_extraction = LLMExtractionSchema(
        id=raw_msg_id,
        amount=500.0,
        currency="ZMW",
        transaction_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),  
        transaction_verb="debit",
        confidence=0.82
    )

    with patch("app.workers.job_handler.parse_batch_response", return_value={str(raw_msg_id): mock_extraction}):
        with patch("app.workers.job_handler.get_cached_extractions_batch", return_value={}):
            with patch("app.workers.job_handler.process_extraction_batch", return_value="dummy"):
                results = process_webhook_batch([job])

    assert results[job.job_id] == "success"

    # Verify database persistence and routing status
    transaction = db_session.query(Transactions).filter_by(raw_message_id=raw_msg_id).first()

    assert transaction is not None
    assert transaction.confidence == 0.82
    assert transaction.status == TransactionStatus.PARSED
    
    # Verify metadata routing details
    meta = transaction.parsing_meta.get("ai_extraction", {})
    assert meta.get("routing_status") == "parsed"
    assert meta.get("routing_action") == "auto_accepted"


def test_confidence_routing_low_confidence(db_session):
    """
    Test that an extraction with confidence < threshold (0.42 < 0.65)
    is flagged and routed to the 'review_required' status.
    """
    # Setup test data
    group = Groups(group_id="group_low", groupname="Test Group 2")
    participant = Participants(phone="2222222222", displayname="Test User 2")
    db_session.add_all([group, participant])
    db_session.commit()

    raw_msg = RawMessages(
                message_id="wamid.test_low",
                sender_id=participant.id,
                group_id=group.id,
                raw_json={"entry": [{"changes": [{"value": {"messages": [{"type": "text", "text": {"body": "Paid K500 for lunch"}, "timestamp": "1774000000"}]}}]}]},
                received_at=datetime.now(timezone.utc),
                hash="test_hash_low"
            )
    db_session.add(raw_msg)
    db_session.commit()

    # Extract the integer ID now so we don't access the detached ORM object later
    raw_msg_id = raw_msg.id

    job = WebhookJobPayload(
        job_id="job_low",
        raw_message_id=raw_msg_id,
        participant_id=participant.id,
        group_id=group.id,
        webhook_event_type="text",
        message_timestamp=datetime.now(timezone.utc),
        ingestion_time=datetime.now(timezone.utc)
    )

    # Mock the LLM to return low confidence
    mock_extraction = LLMExtractionSchema(
        id=raw_msg_id,
        amount=500.0,
        currency="ZMW",
        transaction_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),  
        transaction_verb="debit",
        confidence=0.42
    )

    with patch("app.workers.job_handler.parse_batch_response", return_value={str(raw_msg_id): mock_extraction}):
        with patch("app.workers.job_handler.get_cached_extractions_batch", return_value={}):
            with patch("app.workers.job_handler.process_extraction_batch", return_value="dummy"):
                results = process_webhook_batch([job])

    assert results[job.job_id] == "success"

    # Verify database persistence and routing status
    transaction = db_session.query(Transactions).filter_by(raw_message_id=raw_msg_id).first()

    assert transaction is not None
    assert transaction.confidence == 0.42
    assert transaction.status == TransactionStatus.REVIEW_NEEDED
    
    # Verify metadata routing details
    meta = transaction.parsing_meta.get("ai_extraction", {})
    assert meta.get("routing_status") == "review_needed"
    assert meta.get("routing_action") == "flagged_for_review"