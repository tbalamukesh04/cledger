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
    from app.models.businesses import Businesses
    tenant = db_session.query(Businesses).filter_by(id=1).first()
    if not tenant:
        tenant = Businesses(id=1, name="Global Test", slug="global", is_active=True, meta_waba_id="test_waba", meta_phone_number_id="test_phone")
        db_session.add(tenant)
        db_session.commit()

    # Setup test data
    group = Groups(tenant_id=1, group_id="group_high", groupname="Test Group")
    participant = Participants(tenant_id=1, phone="1111111111", displayname="Test User 1")
    db_session.add_all([group, participant])
    db_session.commit()

    raw_msg = RawMessages(
            tenant_id=1,
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
        tenant_id=1,
        business_id="test_waba",
        phone_number_id="test_phone",
        message_id="wamid.test_high",
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
        confidence=0.95
    )

    with patch("app.workers.job_handler.parse_batch_response", return_value={str(raw_msg_id): mock_extraction}):
        with patch("app.workers.job_handler.get_cached_extractions_batch", return_value={}):
            with patch("app.workers.job_handler.process_extraction_batch", return_value="dummy"):
                results = process_webhook_batch([job])

    assert results[job.job_id] == "success"

    # Verify database persistence and routing status
    transaction = db_session.query(Transactions).filter_by(raw_message_id=raw_msg_id).first()

    assert transaction is not None
    assert transaction.confidence == 0.95
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
    from app.models.businesses import Businesses
    tenant = db_session.query(Businesses).filter_by(id=1).first()
    if not tenant:
        tenant = Businesses(id=1, name="Global Test", slug="global", is_active=True, meta_waba_id="test_waba", meta_phone_number_id="test_phone")
        db_session.add(tenant)
        db_session.commit()

    # Setup test data
    group = Groups(tenant_id=1, group_id="group_low", groupname="Test Group 2")
    participant = Participants(tenant_id=1, phone="2222222222", displayname="Test User 2")
    db_session.add_all([group, participant])
    db_session.commit()

    raw_msg = RawMessages(
                tenant_id=1,
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
        tenant_id=1,
        business_id="test_waba",
        phone_number_id="test_phone",
        message_id="wamid.test_low",
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

    assert transaction is None
    
    raw = db_session.query(RawMessages).filter_by(id=raw_msg_id).first()
    assert raw.processing_status == "review_needed"
    
    # Verify metadata routing details
    meta = raw.parsing_meta.get("ai_extraction", {})