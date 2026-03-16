import json
import logging
import requests
from typing import Optional, Dict, Any

from app.ai.config import GEMINI_API_KEY
from app.utils.backoff import apply_exponential_backoff

logger = logging.getLogger(__name__)

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

class GeminiClient:
    def __init__(self, api_key: Optional[str] = GEMINI_API_KEY, timeout: int = 15, max_retries=3):
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries

    def generate_content(self, prompt: str, system_instruction: Optional[str]=None) -> Optional[Dict[str, Any]]:
        if not self.api_key:
            logger.error(json.dumps({
                "event_type": "gemini_client_error",
                "error_message": "GEMINI_API_KEY is not set."
            }))
            return None

        headers = {"Content-Type": "application/json"}
        payload: Dict[str, Any] = {
            "contents": [{"parts":[{"text": prompt}]}],
            "generationConfig":{
                "temperature": 0.0,
                "response_mime_type": "application/json"
            }
        }

        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        url = f"{GEMINI_API_URL}?key={self.api_key}"

        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(json.dumps({
                    "event_type": "gemini_api_request",
                    "attempt": attempt,
                    "timeout_seconds": self.timeout
                }))

                response = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
                response.raise_for_status()

                logger.info(json.dumps({
                    "event_type": "gemini_api_success",
                    "attempt": attempt,
                    "status_code": response.status_code
                }))

                return response.json()
            
            except requests.exceptions.RequestException as e:
                logger.warning(json.dumps({
                    "event_type": "gemini_api_transient_failure",
                    "attempt": attempt,
                    "error": str(e)
                }))

                if attempt < self.max_retries:
                    apply_exponential_backoff(attempt, 1)
                else:
                    logger.error(json.dumps({
                        "event_type": "gemini_api_permanent_failure",
                        "reason": "max_retries_exceeded",
                        "error": str(e)
                    }), exc_info=True)
                    return None