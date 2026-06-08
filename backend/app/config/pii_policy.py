import re

# PII Scope definitions and transformation rules
# - PARTIAL_MASK: Retains only the last 4 characters (e.g., XXXXXX1234)
# - TRUNCATE_MASK: Retains the first 10 characters + appends original length
# - FULL_REMOVAL: Completely removes the value, substituting with [REMOVED]
# - REDACT: Replaces the entire string with ***REDACTED***

PII_FIELD_RULES = {
    # Phones
    "phone_number": "PARTIAL_MASK",
    "wa_id": "PARTIAL_MASK",
    "from": "PARTIAL_MASK",
    
    # Raw Messages
    "message_text": "TRUNCATE_MASK",
    "raw_message_text": "TRUNCATE_MASK",
    "text": "TRUNCATE_MASK",
    "body": "TRUNCATE_MASK",
    
    # Names & Identifiers
    "name": "REDACT",
    "displayname": "REDACT",
    "email": "REDACT",
    "upi_id": "REDACT",
    "account_number": "REDACT",
    
    # Secrets & Tokens
    "api_key": "FULL_REMOVAL",
    "token": "FULL_REMOVAL",
    "signature": "FULL_REMOVAL",
    "x-hub-signature-256": "FULL_REMOVAL",
    "hub.verify_token": "FULL_REMOVAL"
}

# Regex patterns for unstructured text (scanning raw log strings)
PII_PATTERNS = [
    (re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'), '[EMAIL_REDACTED]'),
    (re.compile(r'\b(?:\+?\d{1,3}[\s-]?)?(?:\d{10}|\d{3}[\s-]\d{3}[\s-]\d{4})\b'), '[PHONE_REDACTED]'),
    (re.compile(r'\b[a-zA-Z0-9.\-_]{2,256}@[a-zA-Z]{2,64}\b'), '[UPI_REDACTED]'),
    (re.compile(r'\b\d{9,18}\b'), '[ACCOUNT_REDACTED]')
]

def apply_field_redaction(key: str, value: any) -> any:
    """Applies specific transformation rules based on the field name."""
    if value is None:
        return value
        
    if not isinstance(value, str):
        # If a PII field is a complex object (like a dict/list), redact it outright
        return "***REDACTED_OBJECT***"

    rule = PII_FIELD_RULES.get(key.lower())

    if rule == "PARTIAL_MASK":
        if len(value) > 4:
            return "*" * (len(value) - 4) + value[-4:]
        return "***"
        
    elif rule == "TRUNCATE_MASK":
        prefix = value[:10] if len(value) > 10 else value
        return f"{prefix}... [REDACTED LENGTH: {len(value)}]"
        
    elif rule == "FULL_REMOVAL":
        return "[REMOVED]"
        
    elif rule == "REDACT":
        return "***REDACTED***"
        
    return value

def redact_unstructured_text(text: str) -> str:
    """Scans and redacts unstructured text strings using regex."""
    if not isinstance(text, str):
        return text
    redacted_text = text
    for pattern, replacement in PII_PATTERNS:
        redacted_text = pattern.sub(replacement, redacted_text)
    return redacted_text    