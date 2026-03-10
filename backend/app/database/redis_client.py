import os
import logging
from dotenv import load_dotenv
import redis

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

# Fetch the Redis URL from the environment
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

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

# Create a globally available, reusable connection instance
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