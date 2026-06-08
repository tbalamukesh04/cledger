import os
import json
import time
import sys
import threading
from datetime import datetime, timezone
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database.redis_client import redis_client, WEBHOOK_QUEUE_NAME, WEBHOOK_ACTIVE_QUEUE, WEBHOOK_DLQ_NAME
from app.workers.worker_service import start_worker

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

def test_crash_recovery_visibility_protection():
    redis_client.delete(WEBHOOK_QUEUE_NAME, WEBHOOK_ACTIVE_QUEUE, WEBHOOK_DLQ_NAME)
    
    dummy_orphaned_job = {
        "job_id": "crash_test_1", 
        "raw_message_id": 999, 
        "participant_id": 1,
        "group_id": 1,
        "message_timestamp": datetime.now(timezone.utc).isoformat(),
        "webhook_event_type": "text",
        "ingestion_time": datetime.now(timezone.utc).isoformat()
    }
    redis_client.lpush(WEBHOOK_ACTIVE_QUEUE, json.dumps(dummy_orphaned_job))
    
    import app.workers.worker_service as ws
    ws.is_running = True
    
    worker_thread = threading.Thread(target=ws.start_worker)
    worker_thread.daemon = True
    worker_thread.start()
    
    time.sleep(2) 
    
    ws.is_running = False
    worker_thread.join()
    
    active_len = redis_client.llen(WEBHOOK_ACTIVE_QUEUE)
    dlq_len = redis_client.llen(WEBHOOK_DLQ_NAME)
    
    assert active_len == 0, f"Expected Active Queue to be empty, got {active_len}"
    assert dlq_len == 0, f"Expected 0 jobs in DLQ for skipped processed jobs, got {dlq_len}"

def test_dead_letter_queue_poison_pill():
    redis_client.delete(WEBHOOK_QUEUE_NAME, WEBHOOK_ACTIVE_QUEUE, WEBHOOK_DLQ_NAME)
    
    poison_pill = "{ invalid_json: missing_quotes }"
    redis_client.lpush(WEBHOOK_QUEUE_NAME, poison_pill)
    
    import app.workers.worker_service as ws
    ws.is_running = True
    
    from unittest.mock import patch
    with patch('app.workers.worker_service.process_webhook_batch', return_value={"crash_test_1": "success"}):
        worker_thread = threading.Thread(target=ws.start_worker)
        worker_thread.daemon = True
        worker_thread.start()
        
        time.sleep(2) 
        
        ws.is_running = False
        worker_thread.join()
    
    dlq_len = redis_client.llen(WEBHOOK_DLQ_NAME)
    main_len_after = redis_client.llen(WEBHOOK_QUEUE_NAME)
    
    assert main_len_after == 0, f"Expected Main Queue to be empty, got {main_len_after}"
    assert dlq_len >= 1, f"Expected at least 1 job in DLQ, got {dlq_len}"