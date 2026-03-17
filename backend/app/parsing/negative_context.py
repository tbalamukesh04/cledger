import re
import logging

logger = logging.getLogger(__name__)

# Patterns that indicate a message is likely just chatter or future intent
NEGATIVE_CONTEXT_PATTERNS = [
    r"\b(should|might|maybe|planning to|going to|will|about to)\s+(pay|send|transfer|give|deposit|remit)\b",
    r"\b(can you|could you|please)\s+(send|pay|transfer|deposit)\b",
    r"\b(how much|what is|when).*\b(price|cost|balance|total)\b",
    r"\b(owe|owes|debt)\b",
    r"\b(supposed to|need to|have to)\b"
]

# Compile patterns for better performance
COMPILED_PATTERNS = [re.compile(pattern, re.IGNORECASE) for pattern in NEGATIVE_CONTEXT_PATTERNS]

def detect_negative_context(text: str) -> bool:
    """
    Analyzes the raw text for conversational, interrogative, or future-tense 
    markers that disqualify it as a completed financial transaction.
    """
    if not text:
        return False
        
    for pattern in COMPILED_PATTERNS:
        match = pattern.search(text)
        if match:
            logger.debug(f"Negative context flagged by phrase: '{match.group(0)}'")
            return True
            
    return False