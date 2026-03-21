from typing import Tuple
from app.ai.prompts.extraction_prompt import BATCH_TRANSACTION_SYSTEM_PROMPT_V1_1
from app.ai.prompts.extraction_prompt_v1 import BATCH_EXTRACTION_PROMPT_V1

class PromptRegistry:

    _registry = {
        "v1": BATCH_EXTRACTION_PROMPT_V1,
        "v1.1": BATCH_TRANSACTION_SYSTEM_PROMPT_V1_1, 
    }

    _active_versions = {
        "batch_transaction_extraction": "v1.1"
    }

    @classmethod
    def get_prompt(cls, task: str, version: str = None) -> Tuple[str, str]:
        if task not in cls._registry:
            raise ValueError(f"PromptRegistry Error: Unknown Task '{task}'")

        target_version = version or cls._active_versions.get(task)

        if target_version not in cls._registry:
            raise ValueError(f"PromptRegistry Error: Unknown Version '{target_version}' for Task '{task}'")

        return cls._registry[task][target_version], target_version

    @classmethod
    def get_active_version(cls, task: str) -> str:
        if task not in cls._active_versions:
            raise ValueError(f"PromptRegistry Error: Unknown Task '{task}'")
        return cls._active_versions[task]