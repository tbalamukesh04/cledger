import os
import logging
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

AI_BATCH_SIZE = int(os.getenv("AI_BATCH_SIZE", 10))

AI_BATCH_TIMEOUT_SECONDS = int(os.getenv("AI_BATCH_TIMEOUT_SECONDS", 5))

SCORING_WEIGHTS = {
    "amount_detected": 2, 
    "currency_detected": 2, 
    "transaction_verb_detected": 2, 
    "negative_context": -4
}

SCORING_THRESHOLD = int(os.getenv("SCORING_THRESHOLD", 2))

if not GEMINI_API_KEY:
    logger.warning('{"event_type": "ai_config_warning", "message": "GEMINI_API_KEY is not set in the environment."}')