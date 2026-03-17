import json
from typing import List, Dict
from app.schemas.preprocessing import PreprocessedPayload

def build_batch_request_payload(messages: List[PreprocessedPayload]) -> List[Dict[str, str]]:
    """
    Transforms a list of preprocessed worker payloads into a minimal dictionary 
    format optimized for the AI context window.
    """
    batch_payload = []
    for msg in messages:
        batch_payload.append({
            "id": str(msg.raw_message_id),
            "text": msg.normalized_text if msg.normalized_text else "",
            "timestamp": msg.normalized_timestamp.isoformat()
        })
    return batch_payload

def construct_batch_prompt(batch_payload: List[Dict[str, str]]) -> str:
    """
    Converts the structured payload into a JSON string format 
    that acts as the primary prompt for the AI model.
    """
    return json.dumps(batch_payload, indent=2)