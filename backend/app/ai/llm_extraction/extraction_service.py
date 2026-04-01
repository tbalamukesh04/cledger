from typing import List, Dict, Any

from app.ai.gemini_client import GeminiClient
from app.ai.batch_request_builder import build_batch_request_payload, construct_batch_prompt
from app.ai.prompts.prompt_registry import PromptRegistry
from app.utils.logger import log_event, log_error, LogTimer
from app.core.log_events import LogEvent

def process_extraction_batch(candidates_for_ai: List[Any]) -> Dict[str, Any]:
    """
    Constructs and sends a batch of transaction messages to Gemini for extraction.
    Returns the raw JSON dictionary response from the Gemini API.
    """
    batch_payload = build_batch_request_payload(candidates_for_ai)
    user_prompt_data, system_instruction, version_id = construct_batch_prompt(batch_payload)

    timer = LogTimer()
    log_event(
        LogEvent.LLM_CALLED, 
        f"Sending batch of {len(batch_payload)} messages to Gemini.",
        batch_size=len(batch_payload),
        version_id=version_id,
        status="initiated"
    )

    client = GeminiClient()
    try:
        response_dict = client.generate_content(
            prompt=user_prompt_data,
            system_instruction=system_instruction
        )
        log_event(
            LogEvent.LLM_CALLED,
            "Successfully received response from Gemini.",
            status="success",
            batch_size=len(batch_payload),
            duration_ms=timer.get_duration_ms()
        )
        return {
            "raw_response": response_dict,
            "metadata": {
                "prompt_version": version_id,
            }
        }
    except Exception as e:
        log_error(
            LogEvent.LLM_ERROR, 
            error=e, 
            message="Error calling Gemini API for batch",
            duration_ms=timer.get_duration_ms(),
            status="failed"
        )
        raise e