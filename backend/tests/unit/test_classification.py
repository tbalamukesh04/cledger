import pytest
from datetime import datetime, timezone
from unittest.mock import patch

from app.schemas.preprocessing import PreprocessedPayload, ProcessingContext
from app.parsing.scoring_engine import TransactionScorer, FeatureExtractor

def create_mock_context(text: str) -> ProcessingContext:
    """Helper to generate a mock processing context with the given text."""
    payload = PreprocessedPayload(
        raw_message_id=999,
        participant_id=1,
        normalized_timestamp=datetime.now(timezone.utc),
        message_id="wamid.MOCK_TEST",
        message_type="text",
        normalized_text=text,
        message_hash="mock_hash",
        text_hash = "mock_text_hash",
        idempotency_identifier="mock_idem"
    )
    return ProcessingContext(payload=payload)

@pytest.fixture
def scorer():
    """Provides a scorer with deterministic weights and threshold for stable tests."""
    test_weights = {
        "amount_detected": 2,
        "currency_detected": 2,
        "date_detected": 1,
        "transaction_verb_detected": 2,
        "negative_context": -5
    }
    return TransactionScorer(weights=test_weights, threshold=4)

@patch('app.parsing.scoring_engine.detect_negative_context')
def test_scorer_clear_transaction(mock_detect_negative, scorer):
    """Test that a message meeting multiple criteria easily passes the threshold."""
    mock_detect_negative.return_value = False
    context = create_mock_context("paid Rahul 500 ZMW")
    result = scorer.evaluate(context)
    
    assert result.scoring.is_transaction_candidate is True
    # amount(2) + currency(2) + verb(2) = 6
    assert result.scoring.total_score == 6
    assert result.scoring.amount_detected is True
    assert result.scoring.currency_detected is True
    assert result.scoring.transaction_verb_detected is True

@patch('app.parsing.scoring_engine.detect_negative_context')
def test_scorer_clear_nontransaction(mock_detect_negative, scorer):
    """Test that random conversation scores below threshold."""
    mock_detect_negative.return_value = False
    context = create_mock_context("did you see the match yesterday")
    result = scorer.evaluate(context)
    
    assert result.scoring.is_transaction_candidate is False
    # date(1) = 1
    assert result.scoring.total_score == 1
    assert result.scoring.amount_detected is False

@patch('app.parsing.scoring_engine.detect_negative_context')
def test_scorer_borderline_case(mock_detect_negative, scorer):
    """Test that a message scoring exactly on the threshold passes."""
    mock_detect_negative.return_value = False
    context = create_mock_context("paid 500") 
    result = scorer.evaluate(context)
    
    assert result.scoring.is_transaction_candidate is True
    # amount(2) + verb(2) = 4 (exactly threshold)
    assert result.scoring.total_score == 4

@patch('app.parsing.scoring_engine.detect_negative_context')
def test_scorer_negative_context_suppression(mock_detect_negative, scorer):
    """Test that negative context effectively suppresses what looks like a valid transaction."""
    mock_detect_negative.return_value = True  # Simulate finding a phrase like "should I have"
    context = create_mock_context("Should I have paid 500 ZMW?") 
    result = scorer.evaluate(context)
    
    assert result.scoring.is_transaction_candidate is False
    # amount(2) + currency(2) + verb(2) + negative(-5) = 1
    assert result.scoring.total_score == 1
    assert result.scoring.negative_context is True

def test_feature_extractor_k_notation():
    """Unit test strictly for regex extraction accuracy on edge cases (K-notation)."""
    signals_prefix = FeatureExtractor.extract_positive_signals("sent K500")
    assert signals_prefix["amount_detected"] is True
    assert signals_prefix["currency_detected"] is True
    assert signals_prefix["transaction_verb_detected"] is True
    
    signals_suffix = FeatureExtractor.extract_positive_signals("sent 500K")
    assert signals_suffix["amount_detected"] is True
    assert signals_suffix["currency_detected"] is True

def test_scorer_extremely_long_message(scorer):
    """Test that regex evaluation does not hang (ReDoS) on massive strings."""
    long_text = "paid 500 ZMW " + ("random_word " * 5000)
    context = create_mock_context(long_text)
    
    # Should execute instantly without crashing
    result = scorer.evaluate(context)
    assert result.scoring.is_transaction_candidate is True
    assert result.scoring.total_score >= 4

def test_scorer_unusual_characters_and_emojis(scorer):
    """Test that emojis and unusual scripts do not break the regex engine."""
    text = "paid 💸 ₹500 🤷‍♂️ to 😊 yesterday 📅"
    context = create_mock_context(text)
    
    result = scorer.evaluate(context)
    # Verbs and dates should still be picked out through the noise
    assert result.scoring.transaction_verb_detected is True
    assert result.scoring.date_detected is True