import pytest
import json
from unittest.mock import patch
from app.ai.ai_parser import AIParser
from app.ai.response_validator import TransactionExtractionSchema

def create_gemini_response(json_data: dict) -> dict:
    return {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": f"```json\n{json.dumps(json_data)}\n```"}
                    ]
                }
            }
        ]
    }

@pytest.fixture
def parser():
    return AIParser(max_retries=2)

def test_parse_empty_input(parser):
    result = parser.parse_single("", "2024-01-01T12:00:00Z")
    assert result is None

@patch('app.ai.ai_parser.GeminiClient.generate_content')
def test_parse_single_valid_transaction(mock_generate, parser):
    expected_json = {
        "amount": 500.0,
        "currency": "ZMW",
        "date": "2024-01-01",
        "transaction_verb": "paid",
        "counterparty": "Rahul",
        "reference": "lunch",
        "confidence": 0.95
    }
    mock_generate.return_value = create_gemini_response(expected_json)
    result = parser.parse_single("Paid Rahul 500 ZMW for lunch", "2024-01-01T12:00:00Z")

    assert result is not None
    assert isinstance(result, TransactionExtractionSchema)
    assert result.amount == 500.0
    assert result.currency == "ZMW"
    assert result.transaction_verb == "paid"
    assert result.confidence == 0.95
    assert mock_generate.call_count == 1

@patch('app.ai.ai_parser.apply_exponential_backoff')
@patch('app.ai.ai_parser.GeminiClient.generate_content')
def test_parse_noisy_unstructured_message(mock_generate, mock_backoff, parser):
    """Test that non-transactional/noisy messages are handled gracefully (returning null fields)."""
    noisy_json = {
        "amount": None,
        "currency": None,
        "date": None,
        "transaction_verb": None,
        "counterparty": None,
        "reference": None,
        "confidence": 0.0
    }
    mock_generate.return_value = create_gemini_response(noisy_json)
    
    result = parser.parse_single("Hey, did you watch the match yesterday?", "2024-01-01T12:00:00Z")
    
    assert result is None

@patch('app.ai.ai_parser.apply_exponential_backoff')
@patch('app.ai.ai_parser.GeminiClient.generate_content')
def test_parse_malformed_json_triggers_retry(mock_generate, mock_backoff, parser):
    """Test that malformed JSON triggers a retry, and correctly processes upon success."""
    valid_json = {
        "amount": 100.0,
        "currency": "USD",
        "date": "2024-01-01",
        "transaction_verb": "received",
        "confidence": 0.9
    }
    
    # First response is bad JSON, second is successful
    mock_generate.side_effect = [
        {"candidates": [{"content": {"parts": [{"text": "{bad_json: true"}]}}]},
        create_gemini_response(valid_json)
    ]
    
    result = parser.parse_single("Received 100 USD", "2024-01-01T12:00:00Z")
    
    assert result is not None
    assert result.amount == 100.0
    assert mock_generate.call_count == 2
    assert mock_backoff.call_count == 1

@patch('app.ai.ai_parser.apply_exponential_backoff')
@patch('app.ai.ai_parser.GeminiClient.generate_content')
def test_parse_validation_error_permanent_failure(mock_generate, mock_backoff, parser):
    """Test that repeated Pydantic validation errors (e.g. negative amount) eventually return None."""
    # Amount < 0 violates the schema `gt=0.0`
    invalid_json = {
        "amount": -50.0,
        "currency": "ZMW",
        "confidence": 0.9
    }
    mock_generate.return_value = create_gemini_response(invalid_json)
    
    result = parser.parse_single("Paid -50 ZMW", "2024-01-01T12:00:00Z")
    
    assert result is None
    assert mock_generate.call_count == parser.max_retries
    assert mock_backoff.call_count == parser.max_retries - 1

@patch('app.ai.ai_parser.GeminiClient.generate_content')
def test_parse_extremely_long_message(mock_generate, parser):
    """Test that the parser does not crash when fed an abnormally long string."""
    long_text = "paid 500 ZMW " + ("and " * 5000)  # ~25,000 characters
    expected_json = {
        "amount": 500.0,
        "currency": "ZMW",
        "date": "2024-01-01",
        "transaction_verb": "paid",
        "confidence": 0.95
    }
    mock_generate.return_value = create_gemini_response(expected_json)
    
    result = parser.parse_single(long_text, "2024-01-01T12:00:00Z")
    assert result is not None
    assert result.amount == 500.0

@patch('app.ai.ai_parser.GeminiClient.generate_content')
def test_parse_terrible_spelling(mock_generate, parser):
    """Test that heavily misspelled text is processed without breaking the parser wrapper."""
    text = "sndd 500 kwca 2 Rhl thx"
    expected_json = {
        "amount": 500.0,
        "currency": "ZMW",
        "date": "2024-01-01",
        "transaction_verb": "sent",
        "counterparty": "Rhl",
        "confidence": 0.85
    }
    mock_generate.return_value = create_gemini_response(expected_json)
    
    result = parser.parse_single(text, "2024-01-01T12:00:00Z")
    assert result is not None
    assert result.currency == "ZMW"
    assert result.transaction_verb == "sent"