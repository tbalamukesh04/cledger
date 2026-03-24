import time
import logging
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.config import api_security_settings

logger = logging.getLogger(__name__)

class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown_ip"
        redis_client = getattr(request.app.state, "redis", None)

        if redis_client:
            current_window = int(time.time()//api_security_settings.RATE_LIMIT_WINDOW)
            key = f"rate_limit:{client_ip}:{current_window}"
            
            try:
                request_count = redis_client.incr(key)

                if request_count == 1:
                    redis_client.expire(key, api_security_settings.RATE_LIMIT_WINDOW)

                if request_count > api_security_settings.RATE_LIMIT_REQUESTS:
                    logger.warning(f"Rate limit exceeded for {client_ip}")
                    return JSONResponse(
                        status_code=429,
                        content={"detail": "Too Many Requests"}
                    )
            
            except Exception as e:
                logger.error(f"Rate limiting error(Redis Error): {str(e)}")
        else:
            logger.warning("Redis client not found in app state. Rate limiting bypassed")

        response = await call_next(request)
        return response