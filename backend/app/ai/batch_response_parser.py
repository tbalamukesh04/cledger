import json
import logging
from typing import List, Dict, Optional, Any

from app.ai.validation_utility import validate_extraction_item
from app.schemas.llm_extraction import LLMExtractionSchema

logger = logging.getLogger(__name__)

def parse_batch_response(
    service_response: Dict[str, Any], # Changed to receive dict containing response + metadata
    original_ids: List[str],
    batch_id: str
) -> Dict[str, Optional[LLMExtractionSchema]]:
    
    # 1. Unpack the response and metadata injected by extraction_service
    raw_response = service_response.get("raw_response", {})
    metadata = service_response.get("metadata", {})
    prompt_version = metadata.get("prompt_version")

    results_map = {msg_id: None for msg_id in original_ids}
    
    if not raw_response:
        logger.error("Empty raw response received for batch.")
        return results_map
        
    try:
        candidates = raw_response.get("candidates", [])
        if not candidates:
            raise ValueError("No candidates returned from Gemini.")
            
        raw_text = candidates[0].get("content", {}).get("parts", [])[0].get("text", "")
        
        cleaned_text = raw_text.strip()
        if cleaned_text.startswith("```json"):
            cleaned_text = cleaned_text[7:]
        if cleaned_text.endswith("```"):
            cleaned_text = cleaned_text[:-3]
            
        parsed_json_array = json.loads(cleaned_text.strip())
        
        if not isinstance(parsed_json_array, list):
            logger.error("Batch response valid JSON, but not a root list/array.")
            return results_map
            
        for item in parsed_json_array:
            extracted_id = item.get("id")
            
            if not extracted_id or str(extracted_id) not in results_map:
                logger.warning(f"LLM returned an unknown or missing ID. Item: {item}")
                continue
            
            # 2. INJECT PROMPT VERSION before passing to your validation utility
            if "confidence" not in item and "confidence_score" not in item:
                item["confidence_score"] = 0.0

            item["prompt_version"] = prompt_version
            
            try:
                # 3. Validate item
                validated_data = validate_extraction_item(item, batch_id)
                results_map[str(extracted_id)] = validated_data
            except Exception as item_error:
                logger.error(
                    f"Item-level validation failed in batch {batch_id}. Item ID: {extracted_id}. Routing to DLQ.", 
                    exc_info=True
                )
                
        return results_map
        
    except json.JSONDecodeError as e:
        logger.error(json.dumps({
            "event_type": "llm_malformed_json_error",
            "error": str(e),
            "raw_text": raw_text if 'raw_text' in locals() else "unknown"
        }))
        raise ValueError(f"Malformed JSON response from LLM: {str(e)}")
        
    except Exception as e:
        logger.error(json.dumps({
            "event_type": "batch_parsing_execution_error",
            "error": str(e)
        }), exc_info=True)
        raise e