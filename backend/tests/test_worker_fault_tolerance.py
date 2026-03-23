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

def run_fault_tolerance_tests():
    print(f"{'='*60}\n🚀 SCENARIO 1: Crash Recovery (Visibility Protection)\n{'='*60}")
    
    # 1. Clear all queues
    redis_client.delete(WEBHOOK_QUEUE_NAME, WEBHOOK_ACTIVE_QUEUE, WEBHOOK_DLQ_NAME)
    
    # 2. Simulate a mid-processing crash with a structurally VALID payload
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
    
    print("-> Simulated worker crash. Job abandoned in ACTIVE queue.")
    
    # 3. Start the worker in a background thread
    print("\n-> Restarting worker service...")
    import app.workers.worker_service as ws
    ws.is_running = True
    
    worker_thread = threading.Thread(target=ws.start_worker)
    worker_thread.daemon = True
    worker_thread.start()
    
    time.sleep(2) # Give it 2 seconds to run startup, recover, and process
    
    # Stop the worker safely
    ws.is_running = False
    worker_thread.join()
    
    active_len = redis_client.llen(WEBHOOK_ACTIVE_QUEUE)
    dlq_len = redis_client.llen(WEBHOOK_DLQ_NAME)
    
    print("\n-> Checking Queues post-recovery...")
    print(f"-> Active Queue Length: {active_len}")
    print(f"-> Dead Letter Queue Length: {dlq_len}")
    
    # The worker should recover the job, try to process it, fail (DB id 999 not found), and route to DLQ
    if active_len == 0 and dlq_len == 1:
        print("✅ SCENARIO 1 PASSED: Worker correctly recovered orphaned job, processed it, and safely routed to DLQ!\n")
    else:
        print("❌ SCENARIO 1 FAILED: Job recovery did not work as expected.\n")


    print(f"{'='*60}\n🚀 SCENARIO 2: Dead Letter Queue (Poison Pill)\n{'='*60}")
    
    # Clear queues again so DLQ length starts at exactly 0
    redis_client.delete(WEBHOOK_QUEUE_NAME, WEBHOOK_ACTIVE_QUEUE, WEBHOOK_DLQ_NAME)
    
    # We push a structurally invalid JSON string
    poison_pill = "{ invalid_json: missing_quotes }"
    redis_client.lpush(WEBHOOK_QUEUE_NAME, poison_pill)
    
    print("-> Injected 'Poison Pill' into Main Queue.")
    
    # Run worker briefly
    ws.is_running = True
    worker_thread = threading.Thread(target=ws.start_worker)
    worker_thread.daemon = True
    worker_thread.start()
    
    time.sleep(3)
    
    # Stop worker
    ws.is_running = False
    worker_thread.join()
    
    dlq_len = redis_client.llen(WEBHOOK_DLQ_NAME)
    main_len_after = redis_client.llen(WEBHOOK_QUEUE_NAME)
    
    print("\n-> Checking Queues post-poison pill...")
    print(f"-> Main Queue Length: {main_len_after}")
    print(f"-> Dead Letter Queue Length: {dlq_len}")
    
    if main_len_after == 0 and dlq_len == 1:
        print("✅ SCENARIO 2 PASSED: Permanently failed job was safely routed to the DLQ!")
    else:
        print("❌ SCENARIO 2 FAILED: DLQ routing did not work as expected.")

if __name__ == "__main__":
    run_fault_tolerance_tests()