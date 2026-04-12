import os
import json
import logging
from datetime import datetime, timezone

# Adjust path if running from root
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.parsing.scoring_engine import TransactionScorer
from app.ai.llm_extraction.extraction_service import process_extraction_batch
from app.ai.batch_response_parser import parse_batch_response
from app.schemas.preprocessing import PreprocessedPayload, ProcessingContext

# Configure basic logging to see the structured logs we implemented in Step 7
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

import pytest

def test_llm_extraction_integration():
    if not os.getenv("GEMINI_API_KEY"):
        pytest.skip("GEMINI_API_KEY environment variable is missing.")
        
    scorer = TransactionScorer()
    
    test_messages = [
        "paid Rahul 500 yesterday",
        "sent ₹1200 for rent",
        "received money from John"
    ]
    
    base_timestamp = datetime.now(timezone.utc)
    candidates_for_ai = []
    
    for idx, text in enumerate(test_messages):
        payload = PreprocessedPayload(
            raw_message_id=idx + 100,
            participant_id=1,
            group_id=None,
            normalized_timestamp=base_timestamp,
            message_id=f"test_msg_{idx}",
            message_type="text",
            normalized_text=text,
            message_hash=f"hash_{idx}",
            idempotency_identifier=f"idem_{idx}"
        )
        
        context = ProcessingContext(payload=payload)
        context = scorer.evaluate(context)
        
        if context.scoring.is_transaction_candidate:
            candidates_for_ai.append(payload)

    assert len(candidates_for_ai) > 0, "No candidates passed the scoring threshold."

    raw_response = process_extraction_batch(candidates_for_ai)
    candidate_ids = [str(c.raw_message_id) for c in candidates_for_ai]
    extracted_data_map = parse_batch_response(raw_response, candidate_ids, "int_test_batch")
    
    results = [extracted_data_map.get(str(c.raw_message_id)) for c in candidates_for_ai]
    
    for result in results:
        assert result is not None, "LLM Extraction failed to return a validated object."
