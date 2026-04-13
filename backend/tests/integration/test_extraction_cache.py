import pytest
from unittest.mock import patch, MagicMock

from app.ai.extraction_cache import get_cached_extractions_batch, cache_extraction_result, EXTRACTION_CACHE_PREFIX
from app.utils.hashing import generate_text_hash
from app.schemas.llm_extraction import LLMExtractionSchema
from app.database.redis_client import get_redis_client

@pytest.fixture(autouse=True)
def clean_redis_cache():
    """Fixture to ensure the Redis cache is clean before and after tests."""
    redis_client = get_redis_client()
    
    def clear_keys():
        keys = redis_client.keys(f"{EXTRACTION_CACHE_PREFIX}*")
        if keys:
            redis_client.delete(*keys)
            
    clear_keys() # Clean before
    yield
    clear_keys() # Clean after


def test_extraction_cache_lifecycle():
    """
    Validates the end-to-end lifecycle of the extraction cache.
    1. First request triggers a miss.
    2. Result is stored in the cache.
    3. Second identical request triggers a hit and retrieves the exact schema.
    """
    message_text = "paid Rahul 500 yesterday"
    text_hash = generate_text_hash(message_text)

    # ---------------------------------------------------------
    # RUN 1: Cache Miss Simulation
    # ---------------------------------------------------------
    first_lookup = get_cached_extractions_batch([text_hash])
    
    # Verify the cache missed
    assert first_lookup.get(text_hash) is None, "Expected cache miss on the first run"

    # Simulate the LLM Extraction that the worker would perform
    # FIXED: Added required 'id' and valid 'transaction_verb'
    mock_llm_result = LLMExtractionSchema(
        id=1,
        amount=500.0,
        currency="INR",
        transaction_verb="debit",
        counterparty="Rahul",
        reference="yesterday",
        confidence=0.98,
        prompt_version="v1"
    )

    # Worker explicitly stores the successful extraction
    cache_extraction_result(text_hash, mock_llm_result)

    # ---------------------------------------------------------
    # RUN 2: Cache Hit Simulation (Identical Message)
    # ---------------------------------------------------------
    second_lookup = get_cached_extractions_batch([text_hash])
    cached_result = second_lookup.get(text_hash)

    # Verify the cache hit and data integrity
    assert cached_result is not None, "Expected cache hit on the second run"
    assert cached_result.amount == 500.0
    assert cached_result.counterparty == "Rahul"
    assert cached_result.transaction_verb == "debit"
    assert cached_result.confidence_score == 0.98

def test_cache_batch_mixed_results():
    """
    Validates that the cache can handle a mix of hits and misses simultaneously,
    which happens during batch processing in the worker.
    """
    text_hit = "groceries 1200"
    text_miss = "auto fare 150"
    
    hash_hit = generate_text_hash(text_hit)
    hash_miss = generate_text_hash(text_miss)
    
    # Pre-populate the cache with the 'hit' scenario
    # FIXED: Added required 'id' and valid 'transaction_verb'
    hit_schema = LLMExtractionSchema(
        id=2,
        amount=1200.0,
        currency="INR",
        transaction_verb="debit",
        counterparty="groceries",
        reference=None,
        confidence=0.90
    )
    cache_extraction_result(hash_hit, hit_schema)
    
    # Perform a batch lookup for both
    batch_results = get_cached_extractions_batch([hash_hit, hash_miss])
    
    # Verify isolation and correct retrieval
    assert batch_results.get(hash_hit) is not None, "Expected hit for pre-populated cache"
    assert batch_results.get(hash_hit).amount == 1200.0
    assert batch_results.get(hash_miss) is None, "Expected miss for unpopulated cache"
