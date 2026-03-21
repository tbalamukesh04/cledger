import json
from typing import List, Dict, Any, Tuple
from app.schemas.preprocessing import PreprocessedPayload
from app.ai.prompts.prompt_registry import PromptRegistry
from app.ai.config import ACTIVE_PROMPT_VERSION

def build_batch_request_payload(candidates_for_ai: List[Any]) -> List[Dict[str, Any]]:
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
    for candidate in candidates_for_ai:
        batch_payload.append({
            "id": str(candidate.raw_message_id),
            "text": candidate.normalized_text if candidate.normalized_text else "",
            "timestamp": candidate.normalized_timestamp.isoformat()
        })
    return batch_payload

def construct_batch_prompt(batch_payload: List[Dict[str, Any]]) -> Tuple[str,str,str]:
    """
    Retrieves the active prompt template and constructs the final LLM inputs.
    
    Returns:
        Tuple containing:
        - user_prompt_data (str): The JSON stringified payload.
        - system_instruction (str): The versioned system prompt with batch rules.
        - version_id (str): The version identifier used.
    """

    system_prompt, version_id = PromptRegistry.get_prompt(
        task="batch_transaction_extraction",
        version=ACTIVE_PROMPT_VERSION
    )

    system_instruction = (
        f"{system_prompt}\n\n"
        "IMPORTANT: You are processing a BATCH of messages. "
        "You MUST return a valid JSON array. Each element in the array must be an object "
        "containing the exact 'id' provided in the prompt, alongside the extracted fields: "
        "amount, currency, transaction_verb, transaction_date, counterparty, and reference. "
        "If a message is not a transaction, return null for the financial fields but KEEP the 'id'. "
        "Do NOT wrap the response in markdown blocks."
    )

    user_prompt_data = json.dumps(batch_payload)

    return user_prompt_data, system_instruction, version_id