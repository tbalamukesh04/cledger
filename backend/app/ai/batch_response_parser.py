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
    back to its originating message ID using explicit ID keys.
    """
    # 1. Initialize the results map with None so we can track missed extractions
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
        
        if not isinstance(parsed_json_array, list):
            logger.error("Batch response valid JSON, but not a root list/array.")
            return results_map
            
        # 2. Iterate and map explicitly by ID, ignoring array order
        for item in parsed_json_array:
            # Extract the ID provided by the LLM
            extracted_id = item.get("id")
            
            if not extracted_id or str(extracted_id) not in results_map:
                logger.warning(f"LLM returned an unknown or missing ID. Item: {item}")
                continue
            
            # Remove the ID so the rest of the dictionary matches your strict Pydantic schema
            item_payload = {k: v for k, v in item.items() if k != "id"}

            try:
                validated_data = TransactionExtractionSchema(**item_payload)
                results_map[str(extracted_id)] = validated_data
            except ValidationError as e:
                # If one item fails validation, log it. It remains None in results_map.
                logger.warning(json.dumps({
                    "event_type": "batch_item_validation_error",
                    "message_id": extracted_id,
                    "error": str(e)
                }))
                
        return results_map
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to decode batch JSON: {str(e)}\nRaw Text: {raw_text}")
        return results_map
    except Exception as e:
        logger.error(f"Batch parsing execution error: {str(e)}", exc_info=True)
        return results_map