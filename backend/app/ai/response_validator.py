import json
import logging
import re
from typing import Optional, Dict, Any, Literal
from pydantic import BaseModel, ValidationError, Field, field_validator

logger = logging.getLogger(__name__)

from pydantic import model_validator
from typing import Any

class TransactionExtractionSchema(BaseModel):
    amount: float = Field(..., gt=0.0, description="The monetary amount extracted")
    currency: str = Field(..., min_length=3, max_length=3, description="The 3-letter currency code")
    date: Optional[str] = Field(None, description="ISO 8601 date string (YYYY-MM-DD).")
    transaction_verb: str = Field(..., description="The type of transaction (credit/debit/unknown)")
    counterparty: Optional[str] = None 

    reference: Optional[str] = None
    confidence: float = Field(..., ge=0.0, le=1.0, description="Extraction confidence")


    @field_validator("currency")
    def validate_currency(cls, v):
        if v is not None:
            return v.upper()
        return v

def parse_and_validate_gemini_response(raw_response: Optional[Dict[str, Any]]) -> Optional[TransactionExtractionSchema]:
    if not raw_response:
        return None
    
    try:
        candidates = raw_response.get("candidates", [])
        if not candidates:
            raise ValueError("No candidates found in the response.")
        
        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            raise ValueError("No parts found in the response.")
        
        raw_text = parts[0].get("text", "")
        
        cleaned_text = raw_text.strip()
        if cleaned_text.startswith("```json"):
            cleaned_text = cleaned_text[7:]
        if cleaned_text.endswith("```"):
            cleaned_text = cleaned_text[:-3]
        cleaned_text = cleaned_text.strip()

        parsed_json = json.loads(cleaned_text)

        validated_data = TransactionExtractionSchema(**parsed_json)
        
        logger.info(json.dumps({
            "event_type": "ai_validation_success",
            "confidence": validated_data.confidence,
            "transaction_verb": validated_data.transaction_verb,
            "extracted_date": validated_data.date
        }))

        return validated_data

    except json.JSONDecodeError as e:
        logger.error(json.dumps({
            "event_type": "ai_validation_error",
            "error_type": "json_decode_error",
            "error_message": str(e),
            "raw_text": raw_text if "raw_text" in locals() else "unknown"
        }))
        return None
    except ValidationError as e:
        logger.error(json.dumps({
            "event_type": "ai_validation_error",
            "error_type": "validation_error",
            "error_details": e.errors(),
            "raw_text": cleaned_text if 'cleaned_text' in locals() else "unknown"
        }))
        return None

    except Exception as e:
        logger.error(json.dumps({
            "event_type": "ai_processing_error",
            "error_msg": str(e)
        }), exc_info=True)
        return None