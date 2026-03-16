# backend/app/ai/ai_parser.py
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

logger = logging.getLogger(__name__)

class AIParser:
    """
    High-level interface for extracting structured data from raw text using Gemini.
    """
    def __init__(self, gemini_client=None):
        self.client = gemini_client or GeminiClient()

    def parse_single(self, text: str, timestamp: str) -> Optional[TransactionExtractionSchema]:
        """Processes a single message and returns a validated schema."""
        if not text:
            return None
            
        prompt = build_transaction_prompt(text, timestamp)
        raw_response = self.client.generate_content(prompt, TRANSACTION_EXTRACTION_SYSTEM_PROMPT)
        return parse_and_validate_gemini_response(raw_response)

    def parse_batch(self, messages: List[Dict[str, str]]) -> List[Optional[TransactionExtractionSchema]]:
        """
        Processes a batch of messages in a single API call to save latency and cost.
        Input format: [{"id": "msg_1", "text": "...", "timestamp": "..."}, ...]
        Returns a list of validated schemas in the exact same order.
        """
        if not messages:
            return []
            
        prompt = build_batch_transaction_prompt(messages)
        raw_response = self.client.generate_content(prompt, BATCH_TRANSACTION_SYSTEM_PROMPT)
        
        if not raw_response:
            return [None] * len(messages)
            
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
                logger.error("Batch response length mismatch or invalid format")
                return [None] * len(messages)
                
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
            logger.error(f"Batch parsing execution error: {str(e)}", exc_info=True)
            return [None] * len(messages)