import re
import logging

logger = logging.getLogger(__name__)

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
    r"will pay",
    r"please send",
    r"please pay",
    r"please transfer",
    r"make sure",
    r"remind me",
    r"let['']?s",
    r"if you",
    r"once you",
    r"when you",
    r"i heard",
    r"they said",
    r"he said",
    r"she said",
    r"apparently",
    r"i was told",
    r"the price",
    r"salary",
    r"budget",
    r"estimate",
    r"invoice total",
    r"total cost",
    r"normally",
    r"we charge",
    r"not received",
    r"not yet received",
    r"never got",
    r"not paid",
    r"is pending",
    r"maybe i",
    r"he owes",
    r"we need to",
]

NEGATIVE_PATTERN = re.compile(
    r'\b(?:' + '|'.join(NEGATIVE_PHRASES) + r')\b|\?',
    re.IGNORECASE,
)


def detect_negative_context(text: str) -> bool:
    """
    Scans the text for negative conversational context phrases.
    Returns True if any negative phrase or a question mark is detected.

    A True return causes the scoring engine to apply a -4 penalty,
    typically pushing non-transaction messages below the classification
    threshold while leaving genuine transactions (which rarely contain
    these phrases) unaffected.
    """
    if not text:
        return False

    is_negative = bool(NEGATIVE_PATTERN.search(text))

    if is_negative:
        logger.debug(f"Negative context detected in text: '{text[:50]}...'")

    return is_negative