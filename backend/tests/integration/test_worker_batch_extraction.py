import os
import time
from datetime import datetime, timezone
from dotenv import load_dotenv

import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.schemas.preprocessing import PreprocessedPayload
from app.ai.ai_parser import AIParser
from app.ai.batch_request_builder import build_batch_request_payload
from app.config.logging_config import setup_logging

load_dotenv()

def test_worker_batch_extraction(mock_gemini):
    setup_logging()
    
    # Bypass the network to avoid 429/503 errors
    mock_gemini.return_value = {
        "candidates": [{
            "content": {
                "parts": [{
                    "text": '''[
                        {"id": 101, "amount": 500, "currency": "ZMW", "transaction_verb": "credit", "counterparty": "John", "confidence": 0.95}, 
                        {"id": 102, "amount": 150000, "currency": "ZMW", "transaction_verb": "debit", "counterparty": "Shoprite", "confidence": 0.98}, 
                        {"id": 103, "amount": null, "currency": null, "transaction_verb": "none", "counterparty": "None", "confidence": 0.85}
                    ]'''
                }]
            }
        }]
    }
        
    msg1 = PreprocessedPayload(
        raw_message_id=101, participant_id=1, group_id=None, normalized_timestamp=datetime.now(timezone.utc),
        message_id="wamid.BATCH_1", message_type="text", normalized_text="Received 500 ZMW for rent from John",
        message_hash="hash1", text_hash="thash1", idempotency_identifier="idem1"
    )
    msg2 = PreprocessedPayload(
        raw_message_id=102, participant_id=1, group_id=None, normalized_timestamp=datetime.now(timezone.utc),
        message_id="wamid.BATCH_2", message_type="text", normalized_text="Paid 150K for groceries at Shoprite yesterday",
        message_hash="hash2", text_hash="thash2", idempotency_identifier="idem2"
    )
    msg3 = PreprocessedPayload(
        raw_message_id=103, participant_id=1, group_id=None, normalized_timestamp=datetime.now(timezone.utc),
        message_id="wamid.BATCH_3", message_type="text", normalized_text="Hey, what time is the meeting tomorrow?",
        message_hash="hash3", text_hash="thash3", idempotency_identifier="idem3"
    )

    messages = [msg1, msg2, msg3]
    batch_payload = build_batch_request_payload(messages)

    parser = AIParser()
    results_list = parser.parse_batch(batch_payload)

    assert len(results_list) == len(messages), f"Expected {len(messages)} results, got {len(results_list)}."
    
    for result in results_list:
        assert result is not None, "Extraction failed or rejected by validator"
