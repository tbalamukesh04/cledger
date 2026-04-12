import os
import logging
from dotenv import load_dotenv
import redis
from app.core.log_events import LogEvent
from app.utils.logger import log_event

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

WEBHOOK_QUEUE_NAME = "cledger:webhook_processing_queue"
WEBHOOK_ACTIVE_QUEUE = "cledger:webhook_active_queue"
WEBHOOK_DLQ_NAME = "cledger:webhook_dead_letter_queue"

EXTRACTION_CACHE_PREFIX = "cledger:extraction_cache:"
EXTRACTION_CACHE_TTL = 86400 * 30

def get_redis_client() -> redis.Redis:
    """
    Initializes and returns a Redis client.
    Sets decode_responses=True to return strings instead of bytes.
    """
    try:
        client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        return client
    except Exception as e:
        log_event(LogEvent.SYSTEM_ERROR, error=e, message="Failed to initialize Redis client")
        raise e

redis_client = get_redis_client()

def verify_redis_connection():
    """
    Utility function to verify the Redis connection.
    """
    try:
        if redis_client.ping():
            log_event(LogEvent.REDIS_CONNECTION, "Redis client successfully connected and pinged.", status="connected")
            return True
    except redis.ConnectionError as e:
        log_event(LogEvent.SYSTEM_ERROR, error=e, message="Redis connection failed.")
        return False