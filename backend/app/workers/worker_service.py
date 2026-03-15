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
from app.workers.job_handler import process_webhook_job, RETRYABLE_EXCEPTIONS
from app.config.logging_config import setup_logging
from app.utils.backoff import apply_exponential_backoff

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
    # ==========================================================

    logger.info(json.dumps({"event_type": "worker_listening"}))

    while is_running:
        try:
            # Atomically pop from main queue and push to active processing queue
            payload_str = redis_client.brpoplpush(WEBHOOK_QUEUE_NAME, WEBHOOK_ACTIVE_QUEUE, timeout=5)

            if payload_str:
                job = None
                try:
                    payload_dict = json.loads(payload_str)
                    job = WebhookJobPayload(**payload_dict)

                    logger.info(json.dumps({
                        "event_type": "job_dequeued",
                        "job_id": job.job_id,
                        "raw_message_id": job.raw_message_id
                    }))

                    for attempt in range(1, MAX_RETRIES + 2):
                        try:
                            success = process_webhook_job(job)

                            if success:
                                # Processing succeeded, safely remove from the active queue
                                redis_client.lrem(WEBHOOK_ACTIVE_QUEUE, 1, payload_str)
                                break
                            else:
                                # Permanent business logic failure (e.g., DB parsing error) -> Route to DLQ
                                redis_client.lpush(WEBHOOK_DLQ_NAME, job.to_json())
                                redis_client.lrem(WEBHOOK_ACTIVE_QUEUE, 1, payload_str)
                                logger.warning(json.dumps({
                                    "event_type": "job_routed_to_dlq",
                                    "reason": "handler_returned_false",
                                    "job_id": job.job_id
                                }))
                                break 
                            
                        except RETRYABLE_EXCEPTIONS as e:
                            if attempt <= MAX_RETRIES:
                                job.retry_count += 1
                                logger.warning(json.dumps({
                                    "event_type": "job_transient_failure",
                                    "raw_message_id": job.raw_message_id,
                                    "retry_attempt": job.retry_count,
                                    "max_retries": MAX_RETRIES,
                                    "error_type": type(e).__name__,
                                    "error_message": str(e),
                                    "timestamp": datetime.now(timezone.utc).isoformat()
                                }))
                                apply_exponential_backoff(job.retry_count, BASE_RETRY_DELAY_SECONDS)
                            else:
                                # Max Retries exceeded -> Route to DLQ
                                logger.error(json.dumps({
                                    "event_type": "job_max_retries_exceeded",
                                    "raw_message_id": job.raw_message_id,
                                    "retry_attempt": attempt,
                                    "error_type": type(e).__name__,
                                    "error_message": str(e),
                                    "timestamp": datetime.now(timezone.utc).isoformat()
                                }))
                                redis_client.lpush(WEBHOOK_DLQ_NAME, job.to_json())
                                redis_client.lrem(WEBHOOK_ACTIVE_QUEUE, 1, payload_str)
                                logger.info(json.dumps({
                                    "event_type": "job_routed_to_dlq",
                                    "reason": "max_retries_exceeded",
                                    "job_id": job.job_id
                                }))
                                break

                except (json.JSONDecodeError, ValidationError) as e:
                    # Structural Error -> Immediate DLQ
                    logger.error(json.dumps({
                        "event_type": "job_validation_error",
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                        "raw_payload": payload_str,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }))
                    redis_client.lpush(WEBHOOK_DLQ_NAME, payload_str)
                    redis_client.lrem(WEBHOOK_ACTIVE_QUEUE, 1, payload_str)
                    
                except Exception as e:
                    logger.error(json.dumps({
                        "event_type": "job_unhandled_exception",
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }), exc_info=True)
                    if job:
                        redis_client.lpush(WEBHOOK_DLQ_NAME, job.to_json())
                    else:
                        redis_client.lpush(WEBHOOK_DLQ_NAME, payload_str)
                    redis_client.lrem(WEBHOOK_ACTIVE_QUEUE, 1, payload_str)
                    
        except Exception as e:
            logger.error(json.dumps({
                "event_type": "redis_polling_error", 
                "error": str(e)
            }))
            time.sleep(2) 

    logger.info(json.dumps({"event_type": "worker_shutdown_complete"}))

if __name__ == "__main__":
    start_worker()