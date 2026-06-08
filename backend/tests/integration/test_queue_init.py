import json
from app.database.redis_client import redis_client, verify_redis_connection

def test_redis_queue_initialization():
    is_connected = verify_redis_connection()
    assert is_connected is True, "Could not connect to Redis. Check your server."

    dummy_job = {
        "job_id": "test_job_001",
        "message_id": "wamid.TEST12345",
        "status": "pending"
    }

    # Use a dedicated test queue to avoid race conditions with running background workers
    TEST_QUEUE = "cledger:test_queue_initialization"
    
    # Ensure clean slate
    redis_client.delete(TEST_QUEUE)

    initial_length = redis_client.llen(TEST_QUEUE)
    
    redis_client.lpush(TEST_QUEUE, json.dumps(dummy_job))
    
    new_length = redis_client.llen(TEST_QUEUE)
    assert new_length == initial_length + 1, "Job was not successfully pushed to Redis."

    redis_client.delete(TEST_QUEUE)
