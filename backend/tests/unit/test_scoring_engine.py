# backend/tests/test_scoring_engine.py
import os
import sys
from datetime import datetime, timezone

# Ensure the app module is in the path for testing
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.schemas.preprocessing import PreprocessedPayload, ProcessingContext
from app.parsing.scoring_engine import TransactionScorer

def create_mock_context(text: str) -> ProcessingContext:
    """Helper to generate a dummy processing context with the given text."""
    payload = PreprocessedPayload(
        raw_message_id=999,
        participant_id=1,
        group_id=None,
        normalized_timestamp=datetime.now(timezone.utc),
        message_id="wamid.MOCK_TEST",
        message_type="text",
        normalized_text=text,
        message_hash="mock_hash",
        idempotency_identifier="mock_idem"
    )
    return ProcessingContext(payload=payload)

def test_scoring_engine_classification():
    scorer = TransactionScorer()
    
    transaction_examples = [
        "paid Rahul 500",
        "sent him ₹1200",
        "received money yesterday"
    ]
    
    non_transaction_examples = [
        "Hey, what time are we meeting?",
        "How much do I owe you for the tickets?",
        "Can you pay me back tomorrow?" 
    ]

    for text in transaction_examples:
        context = create_mock_context(text)
        result = scorer.evaluate(context)
        assert result.scoring.is_transaction_candidate is True, f"Validation Failed: '{text}' was incorrectly flagged as NON-TRANSACTION."
        
    for text in non_transaction_examples:
        context = create_mock_context(text)
        result = scorer.evaluate(context)
        assert result.scoring.is_transaction_candidate is False, f"Validation Failed: '{text}' was incorrectly flagged as a TRANSACTION."
