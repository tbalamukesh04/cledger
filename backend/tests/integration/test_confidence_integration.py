import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

from app.workers.job_handler import process_webhook_batch
from app.schemas.jobs import WebhookJobPayload
from app.schemas.llm_extraction import LLMExtractionSchema
from app.models.raw_messages import RawMessages

def test_schema_confidence_normalization():
    """
    Verifies that the LLMExtractionSchema correctly normalizes different formats 
    of confidence scores retrieved from the LLM.
    """
    # Test 1: Percentage > 1.0 (e.g., LLM hallucinates 85 instead of 0.85)
    payload1 = {"id": 1, "amount": 500.0, "currency": "INR", "transaction_verb": "debit", "confidence": 85}
    schema1 = LLMExtractionSchema(**payload1)
    assert schema1.confidence_score == 0.85

    # Test 2: Valid float within bounds
    payload2 = {"id": 2, "amount": 1200.0, "currency": "INR", "transaction_verb": "debit", "confidence": 0.92}
    schema2 = LLMExtractionSchema(**payload2)
    assert schema2.confidence_score == 0.92

    # Test 3: Out of bounds (clamping to 1.0)
    payload3 = {"id": 3, "amount": 200.0, "currency": "INR", "transaction_verb": "credit", "confidence": 150}
    schema3 = LLMExtractionSchema(**payload3)
    assert schema3.confidence_score == 1.0

    # Test 4: String with percentage sign
    payload4 = {"id": 4, "amount": 100.0, "currency": "INR", "transaction_verb": "debit", "confidence": "95%"}
    schema4 = LLMExtractionSchema(**payload4)
    assert schema4.confidence_score == 0.95

@patch("app.workers.job_handler.SessionLocal")
@patch("app.workers.job_handler.process_extraction_batch")
@patch("app.workers.job_handler.get_cached_extractions_batch")
@patch("app.workers.job_handler.cache_extraction_result")
def test_worker_pipeline_confidence_persistence(
    mock_cache_store, 
    mock_cache_lookup, 
    mock_process_batch, 
    mock_session_local
):
    """
    Verifies that the worker pipeline correctly extracts, normalizes, and persists 
    the confidence score into the database metadata.
    """
    mock_session = MagicMock()
    mock_session_local.return_value = mock_session
    
    # Simulate a cache miss so it forces an LLM call
    mock_cache_lookup.return_value = {}

    # Setup mock RawMessage context
    mock_raw_msg = RawMessages(
        id=1,
        tenant_id=1,
        group_id=1,
        sender_id=1,
        message_id="wamid.123",
        received_at=datetime.now(timezone.utc),
        raw_json={
            "entry": [{"changes": [{"value": {"messages": [
                {"type": "text", "text": {"body": "paid Rahul 500 yesterday"}, "timestamp": "1710000000"}
            ]}}]}]
        },
        processed=False,
        hash="idem_1",
        parsing_meta={}
    )
    
    # Mock the SQLAlchemy query chain
    mock_query = mock_session.query.return_value
    mock_options = mock_query.options.return_value
    mock_filter = mock_options.filter.return_value
    mock_filter.all.return_value = [mock_raw_msg]

    # Setup incoming job payload
    job = WebhookJobPayload(
            job_id="job_1",
            tenant_id=1,
            business_id="test_waba",
            phone_number_id="test_phone",
            message_id="wamid.123",
            raw_message_id=1,
            participant_id=1,
            group_id=1,
            webhook_event_type="text",
            message_timestamp=datetime.now(timezone.utc),
            ingestion_time=datetime.now(timezone.utc)
        )

    # Mock the LLM Response returning a raw confidence of 82 (should normalize to 0.82)
    mock_process_batch.return_value = {
        "raw_response": {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": '[{"id": 1, "amount": 500, "currency": "INR", "transaction_verb": "debit", "counterparty": "Rahul", "confidence": 82}]'
                    }]
                }
            }]
        },
        "metadata": {"prompt_version": "v1"}
    }

    # Execute the Worker Pipeline
    results = process_webhook_batch([job])

    # Assertions
    assert results["job_1"] == "success", "Job should process successfully"
    
    # Verify Metadata Persistence
    assert mock_raw_msg.parsing_meta is not None
    assert "ai_extraction" in mock_raw_msg.parsing_meta
    
    extraction_meta = mock_raw_msg.parsing_meta["ai_extraction"]
    assert extraction_meta["status"] == "SUCCESS"
    assert "confidence" in extraction_meta
    
    # Verify the value was normalized properly and stored in the database mapping
    assert extraction_meta["confidence"] == 0.82
