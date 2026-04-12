import pytest
from app.ai.batch_response_parser import parse_batch_response

def create_mock_gemini_response(json_string: str) -> dict:
    return {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": json_string
                        }
                    ]
                }
            }
        ]
    }

def test_valid_response_accepted():
    valid_json = """
    [
      {
        "id": "msg-1",
        "amount": 500,
        "currency": "INR",
        "transaction_verb": "debit",
        "date": "2026-03-10",
        "counterparty": "Rahul",
        "reference": "payment",
        "confidence": 0.82
      }
    ]
    """
    raw_response = create_mock_gemini_response(valid_json)
    
    result = parse_batch_response(raw_response, ["msg-1"], "batch-test-01")
    
    assert result["msg-1"] is not None
    assert result["msg-1"].amount == 500.0
    assert result["msg-1"].currency == "INR"
    assert result["msg-1"].transaction_verb == "debit"
    assert result["msg-1"].transaction_date == "2026-03-10"

def test_missing_fields_rejected():
    missing_fields_json = """
    [
      {
        "id": "msg-2",
        "amount": 500,
        "confidence": 0.82
      }
    ]
    """
    raw_response = create_mock_gemini_response(missing_fields_json)
    
    result = parse_batch_response(raw_response, ["msg-2"], "batch-test-02")
    
    # Should return None for the specific message ID due to validation failure
    assert result["msg-2"] is None

def test_incorrect_data_types_rejected():
    incorrect_types_json = """
    [
      {
        "id": "msg-3",
        "amount": "five hundred",
        "currency": "INR",
        "transaction_verb": "debit",
        "date": "2026-03-10",
        "counterparty": "Rahul",
        "reference": "payment",
        "confidence": 0.82
      }
    ]
    """
    raw_response = create_mock_gemini_response(incorrect_types_json)
    
    result = parse_batch_response(raw_response, ["msg-3"], "batch-test-03")
    
    # Should return None because 'amount' cannot be parsed into a numeric type
    assert result["msg-3"] is None

def test_malformed_json_raises_error():
    malformed_json = """
    [
      {
        "id": "msg-4",
        "amount": 500,
        "currency": "INR"
    """
    raw_response = create_mock_gemini_response(malformed_json)
    
    # The worker relies on the parser throwing a ValueError to trigger the batch retry logic
    with pytest.raises(ValueError, match="Malformed JSON response from LLM"):
        parse_batch_response(raw_response, ["msg-4"], "batch-test-04")