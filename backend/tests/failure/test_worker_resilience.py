import os
import json
import time
import sys
import threading
from unittest.mock import patch
from datetime import datetime, timezone

from sqlalchemy.exc import OperationalError
import redis

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database.redis_client import redis_client, WEBHOOK_QUEUE_NAME, WEBHOOK_ACTIVE_QUEUE, WEBHOOK_DLQ_NAME
import app.workers.worker_service as ws
from app.config.logging_config import setup_logging

def create_dummy_job(job_id: str) -> dict:
    return {
        "job_id": job_id,
        "raw_message_id": 999,
        "participant_id": 1,
        "group_id": 1,
        "message_timestamp": datetime.now(timezone.utc).isoformat(),
        "webhook_event_type": "text",
        "ingestion_time": datetime.now(timezone.utc).isoformat()
    }

def test_transient_database_failure():
    setup_logging()
    redis_client.delete(WEBHOOK_QUEUE_NAME, WEBHOOK_ACTIVE_QUEUE, WEBHOOK_DLQ_NAME)
    
    job_data = create_dummy_job("retry_test_1")
    redis_client.lpush(WEBHOOK_QUEUE_NAME, json.dumps(job_data))

    with patch('app.workers.worker_service.process_webhook_batch') as mock_process:
        mock_process.side_effect = [
            OperationalError("Mock DB drop", None, None),
            OperationalError("Mock DB lock timeout", None, None),
            True
        ]

        ws.is_running = True
        worker_thread = threading.Thread(target=ws.start_worker)
        worker_thread.daemon = True
        worker_thread.start()

        time.sleep(5)

        ws.is_running = False
        worker_thread.join()

        active_len = redis_client.llen(WEBHOOK_ACTIVE_QUEUE)
        dlq_len = redis_client.llen(WEBHOOK_DLQ_NAME)

        assert mock_process.call_count == 3, "Failed to backoff and retry exactly 3 times."
        assert active_len == 0, "Job was not cleared from Active Queue."
        assert dlq_len == 0, "Job incorrectly routed to DLQ on transient failure."

def test_redis_outage_recovery():
    setup_logging()
    redis_client.delete(WEBHOOK_QUEUE_NAME, WEBHOOK_ACTIVE_QUEUE, WEBHOOK_DLQ_NAME)
    job_data_2 = create_dummy_job("redis_test_2")

    with patch('redis.Redis.brpoplpush') as mock_redis:
        mock_redis.side_effect = [
            redis.exceptions.ConnectionError("Simulated Redis Network Drop"),
            json.dumps(job_data_2),
            None
        ]

        with patch('app.workers.worker_service.process_webhook_job') as mock_process_2:
            mock_process_2.return_value = True

            ws.is_running = True
            worker_thread = threading.Thread(target=ws.start_worker)
            worker_thread.daemon = True
            worker_thread.start()

            time.sleep(4) 

            ws.is_running = False
            worker_thread.join()

            assert mock_redis.call_count >= 2, "Redis did not retry pop after connection drop."
            assert mock_process_2.call_count == 1, "Job was not successfully processed after Redis recovery."
