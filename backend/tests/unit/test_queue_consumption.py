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
        "tenant_id": 1,
        "business_id": "test_waba",
        "phone_number_id": "test_phone",
        "message_id": "wamid.999",
        "raw_message_id": 999,
        "participant_id": 1,
        "group_id": 2,
        "webhook_event_type": "text",
        "message_timestamp": "2024-01-01T12:00:00Z",
        "ingestion_time": "2024-01-01T12:00:05Z"
    }
    mock_payload_str = json.dumps(mock_job)
    
    # 1. Push to the actual mock queue
    mock_redis.lpush(WEBHOOK_QUEUE_NAME, mock_payload_str)
    
    # 2. Pop it off (Simulating what the worker does)
    result = mock_redis.brpop([WEBHOOK_QUEUE_NAME], timeout=5)
    
    assert result is not None
    queue_name, popped_str = result
    
    # 3. Validate extraction
    popped_job = WebhookJobPayload(**json.loads(popped_str))
    assert popped_job.job_id == "test_uuid_123"
    assert popped_job.raw_message_id == 999