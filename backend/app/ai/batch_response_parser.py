import json
import logging
from typing import List, Dict, Optional, Any
from pydantic import ValidationError

from app.ai.response_validator import TransactionExtractionSchema

logger = logging.getLogger(__name__)

def parse_batch_response(
    raw_response: Optional[Dict[str, Any]], 
    original_ids: List[str]
) -> Dict[str, Optional[TransactionExtractionSchema]]:
    """
    Parses a batched Gemini response, mapping each extracted transaction 
    back to its originating message ID.
    
    Returns:
        Dict mapping string message IDs to their validated Pydantic schema (or None if failed).
    """
    # Initialize the results map with None for all expected IDs
    results_map = {msg_id: None for msg_id in original_ids}
    
    if not raw_response:
        logger.error("Empty raw response received for batch.")
        return results_map
        
    try:
        candidates = raw_response.get("candidates", [])
        if not candidates:
            raise ValueError("No candidates returned from Gemini.")
            
        raw_text = candidates[0].get("content", {}).get("parts", [])[0].get("text", "")
        
        # Clean markdown formatting if present
        cleaned_text = raw_text.strip()
        if cleaned_text.startswith("```json"):
            cleaned_text = cleaned_text[7:]
        if cleaned_text.endswith("```"):
            cleaned_text = cleaned_text[:-3]
            
        parsed_json_array = json.loads(cleaned_text.strip())
        
        # Guard against hallucinated structures (e.g., returning an object instead of a list)
        if not isinstance(parsed_json_array, list) or len(parsed_json_array) != len(original_ids):
            logger.error("Batch response length mismatch or invalid root format.")
            return results_map
            
        # Independently validate each item in the batch
        for idx, item in enumerate(parsed_json_array):
            msg_id = original_ids[idx]
            try:
                validated_data = TransactionExtractionSchema(**item)
                results_map[msg_id] = validated_data
            except ValidationError as e:
                # If one item fails validation, the rest of the batch survives
                logger.warning(json.dumps({
                    "event_type": "batch_item_validation_error",
                    "message_id": msg_id,
                    "error": str(e)
                }))
                
        return results_map
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to decode batch JSON: {str(e)}")
        return results_map
    except Exception as e:
        logger.error(f"Batch parsing execution error: {str(e)}", exc_info=True)
        return results_map