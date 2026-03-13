import sys
import json
import time
import signal
import logging
from pydantic import ValidationError

import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from app.database.redis_client import get_redis_client, WEBHOOK_QUEUE_NAME
from app.schemas.jobs import WebhookJobPayload
from app.workers.job_handler import process_webhook_job
from app.config.logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

is_running = True

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

    logger.info(json.dumps({"event_type": "worker_listening"}))

    while is_running:
        try:
            result = redis_client.brpop(WEBHOOK_QUEUE_NAME, timeout=5)

            if result:
                queue_name, payload_str = result

                try:
                    payload_dict = json.loads(payload_str)
                    job = WebhookJobPayload(**payload_dict)

                    logger.info(json.dumps({
                        "event_type": "job_dequeued",
                        "job_id": job.job_id,
                        "raw_message_id": job.raw_message_id
                    }))

                    success = process_webhook_job(job)

                    if success:
                        logger.info(json.dumps({
                            "event_type": "job_completed_successfully",
                            "job_id": job.job_id
                        }))

                    else:
                        logger.warning(json.dumps({
                            "event_type": "job_completion_failed",
                            "job_id": job.job_id
                        }))

                except json.JSONDecodeError as e:
                    logger.error(json.dumps({
                        "event_type": "job_deserialize_error",
                        "error": "Invalid JSON string",
                        "raw_payload": payload_str
                    }))

                except ValidationError as e:
                    logger.error(json.dumps({
                        "event_type": "job_validation_error", 
                        "error": str(e.errors()), 
                        "raw_payload": payload_str
                    }))
                except Exception as e:
                    logger.error(json.dumps({
                        "event_type": "job_unhandled_exception", 
                        "error": str(e)
                    }), exc_info=True)
                    
        except Exception as e:
            # Handle Redis connection drops during polling
            logger.error(json.dumps({
                "event_type": "redis_polling_error", 
                "error": str(e)
            }))
            time.sleep(2) # Backoff before retrying to prevent spamming logs

    logger.info(json.dumps({"event_type": "worker_shutdown_complete"}))

if __name__ == "__main__":
    start_worker()