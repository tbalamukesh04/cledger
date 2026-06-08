import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from pydantic import ValidationError

from app.schemas.llm_extraction import LLMExtractionSchema

logger = logging.getLogger(__name__)

def validate_extraction_item(raw_item: Dict[str, Any], batch_id: str) -> Optional[LLMExtractionSchema]:
    """
    Validates a single LLM extraction payload against the strict LLMExtractionSchema.
    Logs structured validation outcomes for monitoring and debugging.
    """
    msg_id = raw_item.get("id", "UNKNOWN_ID")
    current_timestamp = datetime.now(timezone.utc).isoformat()
    
    try:
        validated_data = LLMExtractionSchema(**raw_item)
        
        # Log successful strict validation
        logger.info(json.dumps({
            "event_type": "llm_schema_validation",
            "raw_message_id": msg_id,
            "batch_id": batch_id,
            "validation_status": "SUCCESS",
            "validation_error_reason": None,
            "timestamp": current_timestamp
        }))
        
        return validated_data

    except ValidationError as e:
        # Extract clear error messages for observability
        error_details = [{"field": err["loc"][0], "msg": err["msg"]} for err in e.errors()]
        
        logger.warning(json.dumps({
            "event_type": "llm_schema_validation",
            "raw_message_id": msg_id,
            "batch_id": batch_id,
            "validation_status": "FAILED",
            "validation_error_reason": error_details,
            "timestamp": current_timestamp,
            "raw_payload": raw_item
        }))
        return None
        
    except Exception as e:
        logger.error(json.dumps({
            "event_type": "llm_schema_validation",
            "raw_message_id": msg_id,
            "batch_id": batch_id,
            "validation_status": "CRITICAL_ERROR",
            "validation_error_reason": str(e),
            "timestamp": current_timestamp
        }), exc_info=True)
        return None