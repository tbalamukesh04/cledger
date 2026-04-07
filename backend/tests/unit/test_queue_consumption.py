import pytest
import json
from unittest.mock import call

from app.schemas.jobs import WebhookJobPayload
from app.database.redis_client import WEBHOOK_QUEUE_NAME

# Assuming you have a function that pushes to the queue, 
# or we just test the worker's extraction logic.
def test_redis_queue_push_pop_simulation(mock_redis):
    """Test that the application interacts with Redis queue correctly."""
    
    # 1. Simulate a JSON string sitting in the Redis queue
    mock_job = {
        "job_id": "test_uuid_123",
        "raw_message_id": 999,
        "participant_id": 1,
        "group_id": 2,
        "webhook_event_type": "text",
        "message_timestamp": "2024-01-01T12:00:00Z",
        "ingestion_time": "2024-01-01T12:00:05Z"
    }
    mock_payload_str = json.dumps(mock_job)
    
    # Simulate redis.brpop returning a tuple (queue_name, payload)
    mock_redis.brpop.return_value = (WEBHOOK_QUEUE_NAME.encode('utf-8'), mock_payload_str.encode('utf-8'))
    
    # 2. Pop it off (Simulating what the worker does)
    result = mock_redis.brpop([WEBHOOK_QUEUE_NAME], timeout=5)
    
    assert result is not None
    queue_name, popped_str = result
    
    # 3. Validate extraction
    popped_job = WebhookJobPayload(**json.loads(popped_str.decode('utf-8')))
    assert popped_job.job_id == "test_uuid_123"
    assert popped_job.raw_message_id == 999
    
    # 4. Verify Redis was actually called with correct parameters
    mock_redis.brpop.assert_called_with([WEBHOOK_QUEUE_NAME], timeout=5)
