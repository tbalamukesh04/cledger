# backend/app/ai/extraction_cache.py
import json
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, List

from app.database.redis_client import get_redis_client
from app.schemas.llm_extraction import LLMExtractionSchema

logger = logging.getLogger(__name__)

EXTRACTION_CACHE_PREFIX = "cledger:extraction_cache:"
EXTRACTION_CACHE_TTL = 86400 * 30  # 30 days retention

def get_cached_extractions_batch(text_hashes: List[str]) -> Dict[str, Optional[LLMExtractionSchema]]:
    """
    Batch retrieval of cached extractions from Redis.
    """
    if not text_hashes:
        return {}
        
    redis_client = get_redis_client()
    keys = [f"{EXTRACTION_CACHE_PREFIX}{th}" for th in text_hashes]
    
    results = {}
    try:
        cached_values = redis_client.mget(keys)
        for text_hash, cached_data in zip(text_hashes, cached_values):
            if cached_data:
                try:
                    parsed_data = json.loads(cached_data)
                    schema_payload = parsed_data.get("extraction_result", parsed_data)
                    results[text_hash] = LLMExtractionSchema(**schema_payload)
                except Exception as e:
                    # RAISE the error so we can see what Pydantic is complaining about
                    raise RuntimeError(f"Cache parse error for {text_hash}: {e}\nPayload: {schema_payload}") from e
            else:
                results[text_hash] = None
    except Exception as e:
        if isinstance(e, RuntimeError):
            raise e
        logger.warning(f"Batch cache retrieval failed: {e}")
        return {th: None for th in text_hashes}
        
    return results

def cache_extraction_result(text_hash: str, extraction_result: LLMExtractionSchema) -> None:
    """
    Stores a successful LLM extraction result in the Redis cache.
    """
    if not text_hash or not extraction_result:
        return
        
    redis_client = get_redis_client()
    cache_key = f"{EXTRACTION_CACHE_PREFIX}{text_hash}"
    
    try:
        cache_payload = {
            "message_hash": text_hash,
            "extraction_result": extraction_result.model_dump(mode='json'),
            "prompt_version": getattr(extraction_result, "prompt_version", None),
            "model_version": "gemini-2.5-flash",
            "confidence": extraction_result.confidence,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        redis_client.setex(cache_key, EXTRACTION_CACHE_TTL, json.dumps(cache_payload))
    except Exception as e:
        # RAISE the error so we can see if Redis is failing to save
        raise RuntimeError(f"Redis setex failed for {text_hash}: {e}") from e