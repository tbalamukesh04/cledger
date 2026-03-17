import os
import logging
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

AI_BATCH_SIZE = int(os.getenv("AI_BATCH_SIZE", 10))

AI_BATCH_TIMEOUT_SECONDS = int(os.getenv("AI_BATCH_TIMEOUT_SECONDS", 5))

if not GEMINI_API_KEY:
    logger.warning('{"event_type": "ai_config_warning", "message": "GEMINI_API_KEY is not set in the environment."}')