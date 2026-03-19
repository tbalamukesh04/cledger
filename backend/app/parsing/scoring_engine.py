# backend/app/parsing/scoring_engine.py
import re
import logging
from app.ai.config import SCORING_WEIGHTS, SCORING_THRESHOLD
from app.schemas.preprocessing import ProcessingContext, ScoringResult
from app.parsing.context_filters import detect_negative_context

logger = logging.getLogger(__name__)

class FeatureExtractor:
    """Extracts positive deterministic signals from text."""
    AMOUNT_PATTERN = re.compile(r'\b\d+(?:\.\d{1,2})?\b', re.IGNORECASE)
    CURRENCY_PATTERN = re.compile(r'\b(?:ZMW|K|ZMK|USD|EUR|GBP|kwacha|dollars?)\b|\$|£|€', re.IGNORECASE)
    DATE_PATTERN = re.compile(r'\b(?:today|yesterday|tomorrow|january|february|march|april|may|june|july|august|september|october|november|december|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b|\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b', re.IGNORECASE)
    VERB_PATTERN = re.compile(r'\b(?:paid|sent|received|got|gave|spent|bought|transfer|transferred|credit|debit|deposit|withdraw|repay|refund)\b', re.IGNORECASE)

    @classmethod
    def extract_positive_signals(cls, text: str) -> dict:
        if not text:
            return {"amount": False, "currency": False, "date": False, "verb": False}
            
        return {
            "amount_detected": bool(cls.AMOUNT_PATTERN.search(text)),
            "currency_detected": bool(cls.CURRENCY_PATTERN.search(text)),
            "date_detected": bool(cls.DATE_PATTERN.search(text)),
            "transaction_verb_detected": bool(cls.VERB_PATTERN.search(text))
        }

class TransactionScorer:
    """Computes the weighted score and makes the classification decision."""
    
    def __init__(self, weights: dict = None, threshold: int = None):
        self.weights = weights or SCORING_WEIGHTS
        self.threshold = threshold if threshold is not None else SCORING_THRESHOLD

    def evaluate(self, context: ProcessingContext) -> ProcessingContext:
        text = context.payload.normalized_text or ""
        
        # 1. Gather all signals (Positive features + Negative context)
        signals = FeatureExtractor.extract_positive_signals(text)
        signals["negative_context"] = detect_negative_context(text)
        
        # 2. Step 5: Implement Weighted Score Calculation
        total_score = 0
        rule_breakdown = {}
        
        for rule_name, is_present in signals.items():
            if is_present:
                points = self.weights.get(rule_name, 0)
                total_score += points
                rule_breakdown[rule_name] = points
            else:
                rule_breakdown[rule_name] = 0
                
        # 3. Step 6: Implement Classification Decision Logic
        is_candidate = total_score >= self.threshold
        
        # 4. Attach Results to Context
        context.scoring = ScoringResult(
            amount_detected=signals["amount_detected"],
            currency_detected=signals["currency_detected"],
            date_detected=signals["date_detected"],
            transaction_verb_detected=signals["transaction_verb_detected"],
            negative_context=signals["negative_context"],
            rule_breakdown=rule_breakdown,
            total_score=total_score,
            is_transaction_candidate=is_candidate
        )
        
        logger.info(
            f"Scoring Complete | MsgID: {context.payload.raw_message_id} | "
            f"Score: {total_score} | Threshold: {self.threshold} | "
            f"Candidate: {is_candidate} | Breakdown: {rule_breakdown}"
        )
        
        return context