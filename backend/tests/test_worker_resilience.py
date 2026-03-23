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

def run_resilience_tests():
    setup_logging()
    
    print(f"{'='*60}\n🚀 SCENARIO 1: Transient Database Failure (Retry & Backoff)\n{'='*60}")
    redis_client.delete(WEBHOOK_QUEUE_NAME, WEBHOOK_ACTIVE_QUEUE, WEBHOOK_DLQ_NAME)
    
    # Insert a structurally valid job into the queue
    job_data = create_dummy_job("retry_test_1")
    redis_client.lpush(WEBHOOK_QUEUE_NAME, json.dumps(job_data))
    
    print("-> Injected job. Mocking Database to fail twice, then succeed...")

    # We patch process_webhook_job to simulate the DB dropping and locking
    with patch('app.workers.worker_service.process_webhook_job') as mock_process:
        # Raise OperationalError twice, then return True (Success) on the 3rd attempt
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
        main_len = redis_client.llen(WEBHOOK_QUEUE_NAME)
        dlq_len = redis_client.llen(WEBHOOK_DLQ_NAME)

        print(f"\n-> Call count for process_webhook_job: {mock_process.call_count}")
        print(f"-> Active Queue: {active_len}, Main Queue: {main_len}, DLQ: {dlq_len}")

        if mock_process.call_count == 3 and active_len == 0 and dlq_len == 0:
            print("✅ SCENARIO 1 PASSED: Worker correctly triggered exponential backoff, retried the transient failures, and successfully completed the job!\n")
        else:
            print("❌ SCENARIO 1 FAILED: Retry mechanism did not work as expected.\n")


    print(f"{'='*60}\n🚀 SCENARIO 2: Redis Outage Recovery\n{'='*60}")
    redis_client.delete(WEBHOOK_QUEUE_NAME, WEBHOOK_ACTIVE_QUEUE, WEBHOOK_DLQ_NAME)

    job_data_2 = create_dummy_job("redis_test_2")

    # FIXED: We now patch the base redis.Redis class so it catches the local instance
    with patch('redis.Redis.brpoplpush') as mock_redis:
        # 1st call: Raise a network drop error
        # 2nd call: Return the job payload successfully
        # 3rd call: Return None to simulate an empty queue
        mock_redis.side_effect = [
            redis.exceptions.ConnectionError("Simulated Redis Network Drop"),
            json.dumps(job_data_2),
            None
        ]

        # We also mock the processing function so it successfully clears the job
        with patch('app.workers.worker_service.process_webhook_job') as mock_process_2:
            mock_process_2.return_value = True

            ws.is_running = True
            worker_thread = threading.Thread(target=ws.start_worker)
            worker_thread.daemon = True
            worker_thread.start()

            # The Redis error in worker_service.py triggers an explicit 2s sleep before resuming the loop
            time.sleep(4) 

            ws.is_running = False
            worker_thread.join()

            print(f"\n-> Call count for Redis pop: {mock_redis.call_count}")
            print(f"-> Call count for processing: {mock_process_2.call_count}")

            # mock_redis will be called at least twice (Failure -> Success)
            if mock_redis.call_count >= 2 and mock_process_2.call_count == 1:
                print("✅ SCENARIO 2 PASSED: Worker survived the Redis outage, slept to prevent log spam, reconnected, and resumed processing!")
            else:
                print("❌ SCENARIO 2 FAILED: Worker crashed or failed to resume.")

if __name__ == '__main__':
    run_resilience_tests()