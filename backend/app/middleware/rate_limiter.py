import time
import logging
from fastapi import Request, HTTPException
from app.core.config import api_security_settings

logger = logging.getLogger(__name__)

class RateLimiter:
    def __init__(self, requests: int = None, window: int = None):
        self.requests = requests or api_security_settings.RATE_LIMIT_REQUESTS
        self.window = window or api_security_settings.RATE_LIMIT_WINDOW

    async def __call__(self, request: Request):
        client_ip = request.client.host if request.client else "unknown_ip"
        redis_client = getattr(request.app.state, "redis", None)

        if redis_client:
            current_window = int(time.time() // self.window)
            # Key format includes path for granular limiting per endpoint per IP
            key = f"rate_limit:{request.url.path}:{client_ip}:{current_window}"
            
            try:
                request_count = redis_client.incr(key)

                if request_count == 1:
                    redis_client.expire(key, self.window)

                if request_count > self.requests:
                    logger.warning(f"Rate limit exceeded for {client_ip} on {request.url.path}. Count: {request_count}/{self.requests}")
                    raise HTTPException(status_code=429, detail="Too Many Requests")
            
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Rate limiting error (Redis Error): {str(e)}")
        else:
            logger.warning("Redis client not found in app state. Rate limiting bypassed")
