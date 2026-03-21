import logging
from typing import List, Dict, Any

from app.ai.gemini_client import GeminiClient
from app.ai.batch_request_builder import build_batch_request_payload, construct_batch_prompt
from app.ai.prompts.prompt_registry import PromptRegistry

logger = logging.getLogger(__name__)

def process_extraction_batch(candidates_for_ai: List[Any]) -> Dict[str, Any]:
    """
    Constructs and sends a batch of transaction messages to Gemini for extraction.
    Returns the raw JSON dictionary response from the Gemini API.
    """
    # 1. Build the payload
    batch_payload = build_batch_request_payload(candidates_for_ai)
    user_prompt_data, system_instruction, version_id = construct_batch_prompt(batch_payload)

    logger.info(f"Sending batch of {len(batch_payload)} messages to Gemini.",
    extra={
        "event_type": "batch_transaction_extraction_sent",
        "batch_size": len(batch_payload),
        "version_id": version_id
    })

    # 3. Call the LLM using your Client Class
    client = GeminiClient()
    try:
        response_dict = client.generate_content(
            prompt=user_prompt_data,
            system_instruction=system_instruction
        )
        return {
            "raw_response": response_dict,
            "metadata": {
                "prompt_version": version_id,
            }
        }
    except Exception as e:
        logger.error(f"Error calling Gemini API for batch: {e}")
        raise e