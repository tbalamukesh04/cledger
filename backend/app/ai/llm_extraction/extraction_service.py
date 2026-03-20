import logging
from typing import List, Dict, Any

from app.ai.gemini_client import GeminiClient
from app.ai.prompt_templates import TRANSACTION_EXTRACTION_SYSTEM_PROMPT
from app.ai.batch_request_builder import build_batch_request_payload, construct_batch_prompt

logger = logging.getLogger(__name__)

def process_extraction_batch(candidates_for_ai: List[Any]) -> Dict[str, Any]:
    """
    Constructs and sends a batch of transaction messages to Gemini for extraction.
    Returns the raw JSON dictionary response from the Gemini API.
    """
    # 1. Build the payload
    batch_payload = build_batch_request_payload(candidates_for_ai)
    prompt_data = construct_batch_prompt(batch_payload)

    # 2. Add strict batch instructions to the system prompt
    batch_instruction = (
        f"{TRANSACTION_EXTRACTION_SYSTEM_PROMPT}\n\n"
        "IMPORTANT: You are processing a BATCH of messages. "
        "You MUST return a valid JSON array. Each element in the array must be an object "
        "containing the exact 'id' provided in the prompt, alongside the extracted fields: "
        "amount, currency, transaction_verb, transaction_date, counterparty, and reference. "
        "If a message is not a transaction, return null for the financial fields but KEEP the 'id'. "
        "Do NOT wrap the response in markdown blocks."
    )

    logger.info(f"Sending batch of {len(batch_payload)} messages to Gemini.")

    # 3. Call the LLM using your Client Class
    client = GeminiClient()
    try:
        response_dict = client.generate_content(
            prompt=prompt_data,
            system_instruction=batch_instruction
        )
        return response_dict
    except Exception as e:
        logger.error(f"Error calling Gemini API for batch: {e}")
        raise e