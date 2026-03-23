import os
import json
import logging
from datetime import datetime, timezone

# Adjust path if running from root
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.parsing.scoring_engine import TransactionScorer
from app.ai.llm_extraction.extraction_service import LLMExtractionService
from app.schemas.preprocessing import PreprocessedPayload, ProcessingContext

# Configure basic logging to see the structured logs we implemented in Step 7
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def run_integration_test():
    print("\n==================================================")
    print("🚀 STARTING LLM EXTRACTION INTEGRATION TEST")
    print("==================================================\n")
    
    # Initialize our pipeline components
    scorer = TransactionScorer()
    extraction_service = LLMExtractionService()
    
    # The test messages specified in the execution plan
    test_messages = [
        "paid Rahul 500 yesterday",
        "sent ₹1200 for rent",
        "received money from John"
    ]
    
    # We lock the base timestamp so Gemini can accurately resolve "yesterday"
    base_timestamp = datetime.now(timezone.utc)
    
    candidates_for_ai = []
    
    print("--- 🎯 PHASE 1: SCORING ENGINE ---")
    for idx, text in enumerate(test_messages):
        # Construct a dummy payload to simulate the worker's PreprocessedPayload
        payload = PreprocessedPayload(
            raw_message_id=idx + 100, # Dummy ID
            participant_id=1,
            group_id=None,
            normalized_timestamp=base_timestamp,
            message_id=f"test_msg_{idx}",
            message_type="text",
            normalized_text=text,
            message_hash=f"hash_{idx}",
            idempotency_identifier=f"idem_{idx}"
        )
        
        # Evaluate context using the Phase 4 Scorer
        context = ProcessingContext(payload=payload)
        context = scorer.evaluate(context)
        
        print(f"\nMessage: '{text}'")
        print(f"Score: {context.scoring.total_score} | Is Transaction: {context.scoring.is_transaction_candidate}")
        print(f"Rule Breakdown: {context.scoring.rule_breakdown}")
        
        if context.scoring.is_transaction_candidate:
            candidates_for_ai.append(payload)

    print("\n==================================================")
    print("--- 🧠 PHASE 2: LLM EXTRACTION (GEMINI) ---")
    
    if not candidates_for_ai:
        print("⚠️ No candidates passed the scoring threshold. Exiting.")
        return

    print(f"Submitting batch of {len(candidates_for_ai)} transactions to Gemini API...")
    print(f"Using context timestamp: {base_timestamp.isoformat()}\n")
    
    # Execute the LLM extraction
    results = extraction_service.extract_transaction_batch(candidates_for_ai)
    
    print("\n--- 📊 PHASE 3: EXTRACTION RESULTS ---")
    for candidate, result in zip(candidates_for_ai, results):
        print(f"\n📝 Original Text: '{candidate.normalized_text}'")
        if result:
            # Print the validated Pydantic model dumped to JSON
            print(json.dumps(result.to_dict(), indent=2))
        else:
            print("❌ Extraction Failed or returned None.")
            
    print("\n==================================================")
    print("✅ INTEGRATION TEST COMPLETE")
    print("==================================================\n")

if __name__ == "__main__":
    # Ensure API key is present before running
    if not os.getenv("GEMINI_API_KEY"):
        print("🛑 ERROR: GEMINI_API_KEY environment variable is missing.")
        print("Please export it before running this test: export GEMINI_API_KEY='your_key'")
        sys.exit(1)
        
    run_integration_test()