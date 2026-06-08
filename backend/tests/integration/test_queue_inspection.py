import json
from app.database.redis_client import redis_client, WEBHOOK_QUEUE_NAME

def test_inspect_queue():
    length = redis_client.llen(WEBHOOK_QUEUE_NAME)
    assert length >= 0, "Queue length should be a non-negative integer."
    
    if length > 0:
        items = redis_client.lrange(WEBHOOK_QUEUE_NAME, 0, 0)
        assert len(items) == 1, "Failed to retrieve the latest job payload."
        
        parsed_job = json.loads(items[0])
        assert isinstance(parsed_job, dict), "Payload in Redis is not a valid JSON object."
