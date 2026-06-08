import time
import logging

logger = logging.getLogger(__name__)

def apply_exponential_backoff(retry_attempt: int, base_delay: int =1, max_delay:int = 60) -> int:
    """
    Calculates and applies an exponential backoff delay based on the retry attempt.
    Progression (base_delay=1): 1s -> 2s -> 4s -> 8s -> 16s...
    
    Args:
        retry_attempt (int): The current retry number (1-indexed).
        base_delay (int): The starting delay in seconds.
        max_delay (int): The maximum allowed delay cap in seconds.
        
    Returns:
        int: The number of seconds the thread slept.
    """
    delay = min(base_delay * (2**(retry_attempt - 1)), max_delay)

    logger.info(f"Applying exponential backoff: sleeping for {delay} seconds before next attempt.")
    time.sleep(delay)

    return delay