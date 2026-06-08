from typing import List, Dict

# -----------------------------------------------------------------------------
# SYSTEM PROMPTS
# -----------------------------------------------------------------------------
TRANSACTION_EXTRACTION_SYSTEM_PROMPT = """You are a highly precise financial data extraction AI. 
Your sole purpose is to analyze text messages and extract financial transaction details into a strict JSON format.
Do NOT output any markdown formatting, conversational text, or explanation. Output ONLY raw, valid JSON.

Extract the following exact fields:
- "amount": The absolute monetary value as a strictly positive float. Evaluate abbreviations (e.g., "50K" = 50000.0). Null if not found.
- "currency": The 3-letter uppercase currency code. If "K" is used or implied by Zambian context, use "ZMW". Default to "ZMW" if unspecified.
- "transaction_verb": Must be EXACTLY "credit" (receiving money) or "debit" (sending/spending money). Null if unclear.
- "date": The date of the transaction in strict ISO 8601 format (YYYY-MM-DD). You MUST use the provided "Context Timestamp" to mathematically resolve relative expressions like "yesterday". Null ONLY if no time reference exists.
- "counterparty": The exact name of the person or entity involved (e.g., "Rahul", "John"). Null if no specific person/entity is mentioned.
- "reference": A concise, well-formatted summary of the transaction's purpose, location, or recipient. Combine details logically (e.g., if the text says "paid 2000K for rent in Monze", output "Rent - Monze". If the text is "paid Rahul 500", output "to Rahul". If "received money from John", output "from John"). Null ONLY if completely unspecified.
- "confidence": A float between 0.0 and 1.0 indicating your confidence in this extraction.

If the text does NOT describe a financial transaction, return all fields as null except "confidence", which must be set to 0.0.
"""

BATCH_TRANSACTION_SYSTEM_PROMPT = """You are a highly precise financial data extraction AI. 
Your sole purpose is to analyze a batch of text messages and extract financial transaction details into a strict JSON ARRAY format.
Do NOT output any markdown formatting, conversational text, or explanation. Output ONLY a raw, valid JSON ARRAY containing objects with the following exact fields:

- "amount": The absolute monetary value as a strictly positive float. Evaluate abbreviations (e.g., "50K" = 50000.0). Null if not found.
- "currency": The 3-letter uppercase currency code. If "K" is used or implied by Zambian context, use "ZMW". Default to "ZMW" if unspecified.
- "transaction_verb": Must be EXACTLY "credit" (receiving money) or "debit" (sending/spending money). Null if unclear.
- "date": The date of the transaction in strict ISO 8601 format (YYYY-MM-DD). You MUST use the provided "Context Timestamp" to mathematically resolve relative expressions like "yesterday". Null ONLY if no time reference exists.
- "counterparty": The exact name of the person or entity involved (e.g., "Rahul", "John"). Null if no specific person/entity is mentioned.
- "reference": A concise, well-formatted summary of the transaction's purpose, location, or recipient. Combine details logically (e.g., if the text says "paid 2000K for rent in Monze", output "Rent - Monze". If the text is "paid Rahul 500", output "to Rahul". If "received money from John", output "from John"). Null ONLY if completely unspecified.
- "confidence": A float between 0.0 and 1.0 indicating your confidence in this extraction.

If a text does NOT describe a financial transaction, return all fields as null except "confidence", which must be set to 0.0 for that specific object.
Ensure the output is a valid JSON array `[]` where each element corresponds to the input message in the exact same order.
"""

# -----------------------------------------------------------------------------
# USER PROMPTS & BUILDERS
# -----------------------------------------------------------------------------
TRANSACTION_EXTRACTION_USER_PROMPT = """Context Timestamp: {context_timestamp}

Message Text:
{normalized_text}

Please extract the transaction details and return ONLY a JSON object matching the requested schema.
"""

def build_transaction_prompt(text: str, timestamp: str) -> str:
    """Builder function for single extraction requests."""
    return TRANSACTION_EXTRACTION_USER_PROMPT.format(
        context_timestamp=timestamp,
        normalized_text=text
    )

def build_batch_transaction_prompt(messages: List[Dict[str, str]]) -> str:
    """Builder function for batch extraction requests."""
    prompt = "Extract transactions from the following batch of messages:\n\n"
    for i, msg in enumerate(messages):
        prompt += f"--- Message {i+1} ---\n"
        prompt += f"Context Timestamp: {msg.get('timestamp')}\n"
        prompt += f"Message Text:\n{msg.get('text')}\n\n"
    prompt += "Return ONLY a JSON array of extracted objects matching the exact size and order of the input messages."
    return prompt