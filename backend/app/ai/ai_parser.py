import json
import logging
from typing import List, Dict, Optional
from pydantic import ValidationError

from app.ai.gemini_client import GeminiClient
from app.ai.prompt_templates import (
    TRANSACTION_EXTRACTION_SYSTEM_PROMPT,
    BATCH_TRANSACTION_SYSTEM_PROMPT,
    build_transaction_prompt,
    build_batch_transaction_prompt
)
from app.ai.response_validator import parse_and_validate_gemini_response, TransactionExtractionSchema
from app.utils.backoff import apply_exponential_backoff

logger = logging.getLogger(__name__)

class AIParser:
    """
    High-level interface for extracting structured data from raw text using Gemini,
    with built-in validation and retry mechanisms.
    """
    def __init__(self, gemini_client=None, max_retries: int = 3):
        self.client = gemini_client or GeminiClient()
        self.max_retries = max_retries

    def parse_single(self, text: str, timestamp: str) -> Optional[TransactionExtractionSchema]:
        """Processes a single message, retrying on validation or network failures."""
        if not text:
            return None
            
        prompt = build_transaction_prompt(text, timestamp)
        
        for attempt in range(1, self.max_retries + 1):
            raw_response = self.client.generate_content(prompt, TRANSACTION_EXTRACTION_SYSTEM_PROMPT)
            validated_schema = parse_and_validate_gemini_response(raw_response)
            
            if validated_schema:
                return validated_schema
                
            logger.warning(json.dumps({
                "event_type": "ai_extraction_retry",
                "attempt": attempt,
                "reason": "validation_failed_or_malformed_json"
            }))
            
            if attempt < self.max_retries:
                apply_exponential_backoff(attempt, base_delay=2)
                
        logger.error(json.dumps({
            "event_type": "ai_extraction_permanent_failure",
            "reason": "max_retries_exceeded"
        }))
        return None

    def parse_batch(self, messages: List[Dict[str, str]]) -> List[Optional[TransactionExtractionSchema]]:
        """Processes a batch of messages. Note: Batch level retries should be handled carefully."""
        if not messages:
            return []
            
        prompt = build_batch_transaction_prompt(messages)
        
        for attempt in range(1, self.max_retries + 1):
            raw_response = self.client.generate_content(prompt, BATCH_TRANSACTION_SYSTEM_PROMPT)
            
            if not raw_response:
                apply_exponential_backoff(attempt, base_delay=2)
                continue
                
            try:
                candidates = raw_response.get("candidates", [])
                if not candidates:
                    raise ValueError("No candidates returned")
                    
                raw_text = candidates[0].get("content", {}).get("parts", [])[0].get("text", "")
                
                cleaned_text = raw_text.strip()
                if cleaned_text.startswith("```json"):
                    cleaned_text = cleaned_text[7:]
                if cleaned_text.endswith("```"):
                    cleaned_text = cleaned_text[:-3]
                    
                parsed_json_array = json.loads(cleaned_text.strip())
                
                if not isinstance(parsed_json_array, list) or len(parsed_json_array) != len(messages):
                    raise ValueError("Batch response length mismatch or invalid format")
                    
                results = []
                for item in parsed_json_array:
                    try:
                        validated_data = TransactionExtractionSchema(**item)
                        results.append(validated_data)
                    except ValidationError as e:
                        logger.warning(f"Validation error in batch item: {e}")
                        results.append(None) 
                return results
                
            except Exception as e:
                logger.warning(json.dumps({
                    "event_type": "ai_batch_extraction_retry",
                    "attempt": attempt,
                    "error": str(e)
                }))
                if attempt < self.max_retries:
                    apply_exponential_backoff(attempt, base_delay=2)

        logger.error(json.dumps({
            "event_type": "ai_batch_extraction_permanent_failure",
            "reason": "max_retries_exceeded"
        }))
        return [None] * len(messages)