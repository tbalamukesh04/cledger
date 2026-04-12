# backend/tests/test_prompt_versioning.py
import pytest
import json
from unittest.mock import patch
from datetime import datetime, timezone

from app.ai.llm_extraction.extraction_service import process_extraction_batch
from app.ai.batch_response_parser import parse_batch_response
from app.ai.prompts.prompt_registry import PromptRegistry

class DummyCandidate:
    def __init__(self, raw_message_id, normalized_text):
        self.raw_message_id = raw_message_id
        self.normalized_text = normalized_text
        self.normalized_timestamp = datetime.now(timezone.utc)

@pytest.fixture
def mock_gemini_client():
    with patch("app.ai.llm_extraction.extraction_service.GeminiClient") as MockClient:
        mock_instance = MockClient.return_value
        yield mock_instance

def test_prompt_version_tracking_and_update(mock_gemini_client):
    """
    Validates that the extraction pipeline correctly attaches, parses, and 
    persists the prompt version, even when the active version changes.
    """
    # 1. Setup Test Data using the correct attribute names
    candidates = [
        DummyCandidate(raw_message_id=1, normalized_text="Paid 500 for rent"),
        DummyCandidate(raw_message_id=2, normalized_text="Received 1000 from Rahul")
    ]
    candidate_ids = ["1", "2"]

    # ==========================================
    # PHASE 1: Test with Prompt Version v1.1
    # ==========================================
    # We mock the Registry directly to guarantee the pipeline gets v1.1
    with patch.object(PromptRegistry, 'get_prompt', return_value=("Test Template V1.1", "v1.1")):
        
        mock_gemini_client.generate_content.return_value = {
            "candidates": [{"content": {"parts": [{"text": json.dumps([
                {"id": 1, "amount": 500, "currency": "ZMW", "transaction_verb": "debit", "confidence": 0.9},
                {"id": 2, "amount": 1000, "currency": "ZMW", "transaction_verb": "credit", "confidence": 0.9}
            ])}]}}]
        }
        
        service_response_v1 = process_extraction_batch(candidates)
        parsed_results_v1 = parse_batch_response(service_response_v1, candidate_ids, "batch-111")
        
        assert service_response_v1["metadata"]["prompt_version"] == "v1.1"
        assert parsed_results_v1["1"].prompt_version == "v1.1"
        assert parsed_results_v1["2"].prompt_version == "v1.1"

    # ==========================================
    # PHASE 2: Test Update to Prompt Version v1.2
    # ==========================================
    # We mock the Registry to simulate the system switching to v1.2
    with patch.object(PromptRegistry, 'get_prompt', return_value=("Test Template V1.2", "v1.2")):
        
        mock_gemini_client.generate_content.return_value = {
            "candidates": [{"content": {"parts": [{"text": json.dumps([
                {"id": 1, "amount": 500, "currency": "ZMW", "transaction_verb": "debit", "confidence": 0.95},
                {"id": 2, "amount": 1000, "currency": "ZMW", "transaction_verb": "credit", "confidence": 0.95}
            ])}]}}]
        }
        
        service_response_v2 = process_extraction_batch(candidates)
        parsed_results_v2 = parse_batch_response(service_response_v2, candidate_ids, "batch-222")
        
        assert service_response_v2["metadata"]["prompt_version"] == "v1.2"
        assert parsed_results_v2["1"].prompt_version == "v1.2"
        assert parsed_results_v2["2"].prompt_version == "v1.2"
        
        # Explicit check that the versions are distinctly isolated
        assert parsed_results_v1["1"].prompt_version != parsed_results_v2["1"].prompt_version

    print("✅ Prompt Versioning Validation Test Passed!")