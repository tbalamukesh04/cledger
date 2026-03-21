import os
import logging
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

AI_BATCH_SIZE = int(os.getenv("AI_BATCH_SIZE", 10))
MAX_BATCH_PAYLOAD_SIZE = int(os.getenv("MAX_BATCH_PAYLOAD_SIZE", 50))
AI_BATCH_TIMEOUT_SECONDS = int(os.getenv("AI_BATCH_TIMEOUT_SECONDS", 5))

ACTIVE_PROMPT_VERSION = os.getenv("ACTIVE_PROMPT_VERSION", "v1.1")

EXTRACTION_CONFIDENCE_THRESHOLD = float(os.getenv("EXTRACTION_CONFIDENCE_THRESHOLD", 0.65))

SCORING_WEIGHTS = {
    "amount_detected":           2,
    "currency_detected":         2,
    "transaction_verb_detected": 2,
    "negative_context":         -4,
}

SCORING_THRESHOLD = int(os.getenv("SCORING_THRESHOLD", 2))

if not GEMINI_API_KEY:
    logger.warning(
        '{"event_type": "ai_config_warning", '
        '"message": "GEMINI_API_KEY is not set in the environment."}'
    )