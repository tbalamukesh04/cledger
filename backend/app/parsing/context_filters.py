import re
import logging

logger = logging.getLogger(__name__)

# List of conversational phrases indicating future intent, questions, or non-transactions
NEGATIVE_PHRASES = [
    r"should pay", 
    r"will send", 
    r"maybe transfer", 
    r"planning to", 
    r"did you send",
    r"quote",
    r"how much",
    r"can you",
    r"should i",
    r"going to",
    r"owe",
    r"balance",
    r"will pay"
]

NEGATIVE_PATTERN = re.compile(r'\b(?:' + '|'.join(NEGATIVE_PHRASES) + r')\b|\?', re.IGNORECASE)

def detect_negative_context(text: str) -> bool:
    """
    Scans the text for negative conversational context phrases.
    Returns True if a negative phrase or question mark is detected.
    """
    if not text:
        return False
        
    is_negative = bool(NEGATIVE_PATTERN.search(text))
    
    if is_negative:
        logger.debug(f"Negative context detected in text: '{text[:30]}...'")
        
    return is_negative