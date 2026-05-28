import sys
import json
import time
import uuid
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
from app.ai.config import WORKER_BATCH_SIZE, AI_BATCH_TIMEOUT_SECONDS
from app.utils.logger import log_event, log_error, bind_context
from app.core.log_events import LogEvent

setup_logging()

is_running = True

MAX_RETRIES = 3
BASE_RETRY_DELAY_SECONDS = 1

def handle_shutdown(signum, frame):
    global is_running
    log_event(LogEvent.WORKER_SHUTDOWN, "Worker shutdown initiated", signal=signum)
    is_running = False

signal.signal(signal.SIGINT, handle_shutdown)
signal.signal(signal.SIGTERM, handle_shutdown)

def start_worker():
    global is_running
    log_event(LogEvent.WORKER_STARTUP, "Worker starting up", queue=WEBHOOK_QUEUE_NAME)

    redis_client = get_redis_client()

    try:
        redis_client.ping()
        log_event(LogEvent.REDIS_CONNECTION, "Redis connection successful", status="connected")
    except Exception as e:
        log_error(LogEvent.SYSTEM_ERROR, error=e, message="Redis connection failed during worker startup")
        sys.exit(1)

    # ==========================================================
    # --- CRITICAL MISSING BLOCK: Crash Recovery ---
    # Recover jobs left in the active queue due to previous crashes
    # ==========================================================
    while True:
        recovered_job = redis_client.rpoplpush(WEBHOOK_ACTIVE_QUEUE, WEBHOOK_QUEUE_NAME)
        if not recovered_job:
            break
        log_event(LogEvent.SYSTEM_ERROR, "Orphaned job safely returned to main queue", status="recovered")
    
    log_event(LogEvent.WORKER_STARTUP, "Worker listening for jobs", batch_size=WORKER_BATCH_SIZE)


    last_queue_log_time = time.time()
    QUEUE_LOG_INTERVAL_SECONDS = 60

    while is_running:
        try:
            current_time = time.time()
            if current_time - last_queue_log_time >= QUEUE_LOG_INTERVAL_SECONDS:
                queue_depth = redis_client.llen(WEBHOOK_QUEUE_NAME)
                log_event(LogEvent.QUEUE_DEPTH_CHECKED, "Queue depth", queue_name=WEBHOOK_QUEUE_NAME, queue_depth=queue_depth)
                last_queue_log_time = current_time
                
            batch_payloads = []
            batch_jobs = []
            start_time = time.time()

            # 1. Gather Batch loop
            while len(batch_payloads) < WORKER_BATCH_SIZE and is_running:
                # Use a short 1-second timeout so we can respect the overall BATCH_TIMEOUT
                payload_str = redis_client.brpoplpush(WEBHOOK_QUEUE_NAME, WEBHOOK_ACTIVE_QUEUE, timeout=1)
                
                if payload_str:
                    batch_payloads.append(payload_str)
                    try:
                        job = WebhookJobPayload(**json.loads(payload_str))
                        batch_jobs.append(job)
                    except (json.JSONDecodeError, ValidationError) as e:
                        log_error(LogEvent.JOB_FAILED, error=e, message="Job validation error, sending to DLQ", status="dlq")
                        redis_client.lpush(WEBHOOK_DLQ_NAME, payload_str)
                        redis_client.lrem(WEBHOOK_ACTIVE_QUEUE, 1, payload_str)
                        batch_payloads.remove(payload_str) # Don't process this one
                
                if time.time() - start_time >= AI_BATCH_TIMEOUT_SECONDS:
                    break

            # 2. Process Batch
            if batch_jobs:
                # Bind a batch_id for the execution wrapper logs
                batch_id = str(uuid.uuid4())
                bind_context(job_id=f"batch-{batch_id}")
                log_event(LogEvent.JOB_STARTED, "Executing batch", size=len(batch_jobs))
                
                # We execute the new batch handler
                results = process_webhook_batch(batch_jobs)
                
                # Throttle to respect Gemini rate limits
                time.sleep(3) 

                # 3. Cleanup Active Queue based on results
                for payload_str, job in zip(batch_payloads, batch_jobs):
                    
                    # Bind context specifically for this job's cleanup logs
                    bind_context(job_id=job.job_id)
                    status = results.get(job.job_id, "retry")
                    
                    if status == "success":
                        redis_client.lrem(WEBHOOK_ACTIVE_QUEUE, 1, payload_str)
                        
                    elif status == "dlq":
                        redis_client.lpush(WEBHOOK_DLQ_NAME, job.to_json())
                        redis_client.lrem(WEBHOOK_ACTIVE_QUEUE, 1, payload_str)
                        log_event(LogEvent.JOB_FAILED, "Job moved to DLQ", status="dlq")
                        
                    elif status == "retry":
                        job.retry_count += 1
                        if job.retry_count > MAX_RETRIES:
                            log_event(LogEvent.JOB_FAILED, "Job max retries exceeded. Moving to DLQ.", status="dlq", retry_count=job.retry_count)
                            redis_client.lpush(WEBHOOK_DLQ_NAME, job.to_json())
                            redis_client.lrem(WEBHOOK_ACTIVE_QUEUE, 1, payload_str)
                        else:
                            # Re-queue for next attempt
                            log_event(LogEvent.JOB_STARTED, f"Job retrying ({job.retry_count}/{MAX_RETRIES}).", status="retry", retry_count=job.retry_count)
                            redis_client.lpush(WEBHOOK_QUEUE_NAME, job.to_json())
                            redis_client.lrem(WEBHOOK_ACTIVE_QUEUE, 1, payload_str)
                            apply_exponential_backoff(job.retry_count, BASE_RETRY_DELAY_SECONDS)
                
                # Clear context after batch is done
                bind_context(job_id=None)

        except Exception as e:
            log_error(LogEvent.SYSTEM_ERROR, error=e, message="Redis polling error in worker loop")
            time.sleep(2) 

    log_event(LogEvent.WORKER_SHUTDOWN, "Worker shutdown complete")

if __name__ == "__main__":
    start_worker()