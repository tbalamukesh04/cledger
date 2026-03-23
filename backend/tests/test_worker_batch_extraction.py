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

def run_batch_test():
    setup_logging()
    print("--- Starting AI Batch Extraction Integration Test ---")

    # 1. Create Mock Preprocessed Payloads
    # Mixing valid transactions with a conversational non-transaction message
    msg1 = PreprocessedPayload(
        raw_message_id=101, participant_id=1, normalized_timestamp=datetime.now(timezone.utc),
        message_id="wamid.BATCH_1", message_type="text", normalized_text="Received 500 ZMW for rent from John",
        message_hash="hash1", idempotency_identifier="idem1"
    )
    msg2 = PreprocessedPayload(
        raw_message_id=102, participant_id=1, normalized_timestamp=datetime.now(timezone.utc),
        message_id="wamid.BATCH_2", message_type="text", normalized_text="Paid 150K for groceries at Shoprite yesterday",
        message_hash="hash2", idempotency_identifier="idem2"
    )
    msg3 = PreprocessedPayload(
        raw_message_id=103, participant_id=1, normalized_timestamp=datetime.now(timezone.utc),
        message_id="wamid.BATCH_3", message_type="text", normalized_text="Hey, what time is the meeting tomorrow?",
        message_hash="hash3", idempotency_identifier="idem3"
    )

    messages = [msg1, msg2, msg3]
    original_ids = [str(m.raw_message_id) for m in messages]

    # 2. Build Batch Payload
    print("\n-> Building Batch Request Payload...")
    batch_payload = build_batch_request_payload(messages)

    # 3. Execute Batch Parse
    print("-> Sending Batch to Gemini API (This relies on the Day 23 AI Retry mechanism)...")
    parser = AIParser()
    
    start_time = time.perf_counter()
    results_list = parser.parse_batch(batch_payload)
    latency = time.perf_counter() - start_time

    # 4. Validate and Map Results
    print(f"\n--- Batch Extraction Results (Latency: {latency:.2f}s) ---")
    
    if len(results_list) != len(messages):
        print(f"❌ CRITICAL FAILURE: Expected {len(messages)} results, got {len(results_list)}.")
        return

    for i, result in enumerate(results_list):
        msg_id = original_ids[i]
        original_text = messages[i].normalized_text
        
        if result:
            # Check if it was classified correctly based on the confidence and verb
            if result.transaction_verb and result.amount:
                status = "✅ TRANSACTION PARSED"
            else:
                status = "⏭️ NON-TRANSACTION (Ignored)"
                
            print(f"[Message ID: {msg_id}] -> {status}")
            print(f"   Text: '{original_text}'")
            print(f"   Extracted: {result.amount} {result.currency} | Verb: {result.transaction_verb} | Date: {result.date} | Conf: {result.confidence}\n")
        else:
            print(f"❌ [Message ID: {msg_id}] -> EXTRACTION FAILED OR REJECTED BY VALIDATOR")
            print(f"   Text: '{original_text}'\n")

if __name__ == "__main__":
    run_batch_test()