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
        normalized_timestamp=datetime.now(timezone.utc),
        message_id="wamid.MOCK_TEST",
        message_type="text",
        normalized_text=text,
        message_hash="mock_hash",
        idempotency_identifier="mock_idem"
    )
    return ProcessingContext(payload=payload)

def run_scoring_tests():
    scorer = TransactionScorer()
    
    print("==================================================")
    print("🚀 SCORING ENGINE VALIDATION TESTS")
    print("==================================================")
    
    # Representative datasets as specified in Step 9
    transaction_examples = [
        "paid Rahul 500",
        "sent him ₹1200",
        "received money yesterday"
    ]
    
    non_transaction_examples = [
        "should pay him tomorrow",
        "did you send the money",
        "let's split the bill"
    ]
    
    # --- TEST 1: POSITIVE TRANSACTIONS ---
    print("\n[1] Testing Transaction Examples (Expected: TRUE)")
    for text in transaction_examples:
        context = create_mock_context(text)
        result = scorer.evaluate(context)
        
        score = result.scoring.total_score
        candidate = result.scoring.is_transaction_candidate
        breakdown = result.scoring.rule_breakdown
        
        print(f" -> '{text}'")
        print(f"    Score: {score} | Candidate: {candidate} | Breakdown: {breakdown}")
        
        assert candidate is True, f"❌ Validation Failed: '{text}' was incorrectly flagged as NON-TRANSACTION."
        
    print("✅ All positive transactions correctly classified.")

    # --- TEST 2: NEGATIVE / NON-TRANSACTIONS ---
    print("\n[2] Testing Non-Transaction Examples (Expected: FALSE)")
    for text in non_transaction_examples:
        context = create_mock_context(text)
        result = scorer.evaluate(context)
        
        score = result.scoring.total_score
        candidate = result.scoring.is_transaction_candidate
        breakdown = result.scoring.rule_breakdown
        negative_flag = result.scoring.negative_context
        
        print(f" -> '{text}'")
        print(f"    Score: {score} | Candidate: {candidate} | Negative Context: {negative_flag} | Breakdown: {breakdown}")
        
        assert candidate is False, f"❌ Validation Failed: '{text}' was incorrectly flagged as a TRANSACTION."
        
    print("✅ All non-transactions successfully filtered out.")
    
    print("\n🏆 Checkpoint Passed: The scoring engine correctly routes messages based on deterministic rules!")

if __name__ == "__main__":
    run_scoring_tests()