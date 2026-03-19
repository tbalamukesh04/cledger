import sys
import json
import time
import signal
import logging
from datetime import datetime, timezone
from pydantic import ValidationError

import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from app.database.redis_client import get_redis_client, WEBHOOK_QUEUE_NAME, WEBHOOK_ACTIVE_QUEUE, WEBHOOK_DLQ_NAME
from app.schemas.jobs import WebhookJobPayload
from app.workers.job_handler import process_webhook_batch, RETRYABLE_EXCEPTIONS
from app.config.logging_config import setup_logging
from app.utils.backoff import apply_exponential_backoff
from app.ai.config import AI_BATCH_SIZE, AI_BATCH_TIMEOUT_SECONDS

setup_logging()
logger = logging.getLogger(__name__)

is_running = True

MAX_RETRIES = 3
BASE_RETRY_DELAY_SECONDS = 1

def handle_shutdown(signum, frame):
    global is_running
    logger.info(json.dumps({
        "event_type": "worker_shutdown_initiated",
        "signal": signum
    }))
    is_running = False

signal.signal(signal.SIGINT, handle_shutdown)
signal.signal(signal.SIGTERM, handle_shutdown)

def start_worker():
    global is_running
    logger.info(json.dumps({
        "event_type": "worker_startup",
        "queue": WEBHOOK_QUEUE_NAME
    }))

    redis_client = get_redis_client()

    try:
        redis_client.ping()
        logger.info(json.dumps({"event_type": "redis_connection_success"}))
    except Exception as e:
        logger.error(json.dumps({
            "event_type": "redis_connection_failed",
            "error": str(e)
        }))
        sys.exit(1)

    # ==========================================================
    # --- CRITICAL MISSING BLOCK: Crash Recovery ---
    # Recover jobs left in the active queue due to previous crashes
    # ==========================================================
    while True:
        recovered_job = redis_client.rpoplpush(WEBHOOK_ACTIVE_QUEUE, WEBHOOK_QUEUE_NAME)
        if not recovered_job:
            break
        logger.info(json.dumps({
            "event_type": "job_recovered_from_crash",
            "message": "Orphaned job safely returned to main queue."
        }))
    
    logger.info(json.dumps({"event_type": "worker_listening", "batch_size": AI_BATCH_SIZE}))

    while is_running:
        try:
            batch_payloads = []
            batch_jobs = []
            start_time = time.time()

            # 1. Gather Batch loop
            while len(batch_payloads) < AI_BATCH_SIZE and is_running:
                # Use a short 1-second timeout so we can respect the overall BATCH_TIMEOUT
                payload_str = redis_client.brpoplpush(WEBHOOK_QUEUE_NAME, WEBHOOK_ACTIVE_QUEUE, timeout=1)
                
                if payload_str:
                    batch_payloads.append(payload_str)
                    try:
                        job = WebhookJobPayload(**json.loads(payload_str))
                        batch_jobs.append(job)
                    except (json.JSONDecodeError, ValidationError) as e:
                        logger.error(f"Job validation error, sending to DLQ: {e}")
                        redis_client.lpush(WEBHOOK_DLQ_NAME, payload_str)
                        redis_client.lrem(WEBHOOK_ACTIVE_QUEUE, 1, payload_str)
                        batch_payloads.remove(payload_str) # Don't process this one
                
                if time.time() - start_time >= AI_BATCH_TIMEOUT_SECONDS:
                    break

            # 2. Process Batch
            if batch_jobs:
                logger.info(json.dumps({"event_type": "executing_batch", "size": len(batch_jobs)}))
                
                # We execute the new batch handler
                results = process_webhook_batch(batch_jobs)

                # 3. Cleanup Active Queue based on results
                for payload_str, job in zip(batch_payloads, batch_jobs):
                    status = results.get(job.job_id, "retry")
                    
                    if status == "success":
                        redis_client.lrem(WEBHOOK_ACTIVE_QUEUE, 1, payload_str)
                        
                    elif status == "dlq":
                        redis_client.lpush(WEBHOOK_DLQ_NAME, job.to_json())
                        redis_client.lrem(WEBHOOK_ACTIVE_QUEUE, 1, payload_str)
                        
                    elif status == "retry":
                        job.retry_count += 1
                        if job.retry_count > MAX_RETRIES:
                            logger.error(f"Job {job.job_id} max retries exceeded. Moving to DLQ.")
                            redis_client.lpush(WEBHOOK_DLQ_NAME, job.to_json())
                            redis_client.lrem(WEBHOOK_ACTIVE_QUEUE, 1, payload_str)
                        else:
                            # Re-queue for next attempt
                            logger.warning(f"Job {job.job_id} retrying ({job.retry_count}/{MAX_RETRIES}).")
                            redis_client.lpush(WEBHOOK_QUEUE_NAME, job.to_json())
                            redis_client.lrem(WEBHOOK_ACTIVE_QUEUE, 1, payload_str)
                            apply_exponential_backoff(job.retry_count, BASE_RETRY_DELAY_SECONDS)

        except Exception as e:
            logger.error(json.dumps({"event_type": "redis_polling_error", "error": str(e)}))
            time.sleep(2) 

    logger.info(json.dumps({"event_type": "worker_shutdown_complete"}))

if __name__ == "__main__":
    start_worker()