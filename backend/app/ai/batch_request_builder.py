import json
from typing import List, Dict, Any
from app.schemas.preprocessing import PreprocessedPayload

def build_batch_request_payload(messages: List[PreprocessedPayload]) -> List[Dict[str, Any]]:
    """
    Constructs the LLM request payload for multiple messages.
    Assigns message identifiers and extracts normalized text for the LLM.
    
    Example structure:
    [
      { "id": "msg1", "text": "paid Rahul 500 yesterday", "timestamp": "2026-03-19T..."},
      { "id": "msg2", "text": "sent ₹1200 to Aman", "timestamp": "2026-03-19T..."}
    ]
    """
    batch_payload = []
    for msg in messages:
        batch_payload.append({
            "id": str(msg.raw_message_id),
            "text": msg.normalized_text if msg.normalized_text else "",
            "timestamp": msg.normalized_timestamp.isoformat()
        })
    return batch_payload

def construct_batch_prompt(batch_payload: List[Dict[str, Any]]) -> str:
    """
    Embeds messages into a structured JSON string prompt format.
    Each message remains identifiable via its 'id' key.
    """
    return json.dumps(batch_payload, indent=2)