import os
import logging
from dotenv import load_dotenv
import redis

load_dotenv()

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

WEBHOOK_QUEUE_NAME = "cledger:webhook_processing_queue"
WEBHOOK_ACTIVE_QUEUE = "cledger:webhook_active_queue"
WEBHOOK_DLQ_NAME = "cledger:webhook_dead_letter_queue"

def get_redis_client() -> redis.Redis:
    """
    Initializes and returns a Redis client.
    Sets decode_responses=True to return strings instead of bytes.
    """
    try:
        client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        return client
    except Exception as e:
        logger.error(f"Failed to initialize Redis client: {e}")
        raise e

redis_client = get_redis_client()

def verify_redis_connection():
    """
    Utility function to verify the Redis connection.
    """
    try:
        if redis_client.ping():
            logger.info("✅ Redis client successfully connected and pinged.")
            return True
    except redis.ConnectionError as e:
        logger.error(f"❌ Redis connection failed: {e}")
        return False