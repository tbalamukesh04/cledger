import logging
from typing import Dict, Any, Tuple, Optional

from app.ai.response_validator import TransactionExtractionSchema
from app.parsing.scoring_rules import (
    WEIGHT_AMOUNT, WEIGHT_CURRENCY, WEIGHT_DATE, WEIGHT_VERB, WEIGHT_NEGATIVE, TRANSACTION_THRESHOLD
)
from app.parsing.negative_context import detect_negative_context

logger = logging.getLogger(__name__)

class ScoringEngine:
    """
    Deterministic rules engine that converts AI-extracted signals into 
    a final classification decision and structured metadata.
    """
    def __init__(self):
        self.threshold = TRANSACTION_THRESHOLD

    def evaluate(
        self, 
        extraction: Optional[TransactionExtractionSchema], 
        original_text: str
    ) -> Tuple[bool, int, Dict[str, Any]]:
        
        if not extraction:
            return False, 0, {"error": "no_ai_extraction"}

        score = 0
        rules = {
            "amount": False,
            "currency": False,
            "date": False,
            "transaction_verb": False,
            "negative_context": False
        }

        # --- Rule Evaluations ---
        if extraction.amount is not None:
            score += WEIGHT_AMOUNT
            rules["amount"] = True

        if extraction.currency is not None:
            score += WEIGHT_CURRENCY
            rules["currency"] = True

        if extraction.date is not None:
            score += WEIGHT_DATE
            rules["date"] = True

        if extraction.transaction_verb is not None:
            score += WEIGHT_VERB
            rules["transaction_verb"] = True

        # --- Negative Context Evaluation ---
        has_negative = detect_negative_context(original_text)
        if has_negative:
            score += WEIGHT_NEGATIVE
            rules["negative_context"] = True

        # --- Classification Threshold Logic ---
        is_transaction = score >= self.threshold

        # --- Generate Scoring Breakdown Metadata ---
        metadata = {
            "score": score,
            "threshold": self.threshold,
            "rules": rules
        }

        logger.info(f"Scoring Engine Evaluation - Score: {score}/{self.threshold} | Is Transaction: {is_transaction}")
        
        return is_transaction, score, metadata