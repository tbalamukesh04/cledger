import hashlib
from datetime import datetime

def generate_content_hash(text: str | None, timestamp: datetime) -> str:
    """
    Generates a deterministic SHA256 hash based on the normalized message 
    content and final timestamp.
    
    This is used as a strict fallback idempotency identifier when a native 
    WhatsApp Message ID (wamid) is unavailable.
    
    Args:
        text (str | None): The cleaned, normalized message text.
        timestamp (datetime): The timezone-aware UTC datetime of the message.
        
    Returns:
        str: A 64-character SHA256 hex digest.
    """
    # Safely handle empty or media-only messages where text might be None
    safe_text = text if text is not None else ""
    
    # Enforce a strict, stable ISO 8601 string format for the timestamp
    safe_timestamp = timestamp.isoformat()
    
    # Combine the inputs deterministically with a delimiter
    base_string = f"{safe_text}|{safe_timestamp}"
    
    # Generate and return the hash
    return hashlib.sha256(base_string.encode('utf-8')).hexdigest()