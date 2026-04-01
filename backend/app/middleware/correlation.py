import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from app.config.logging_config import request_id_ctx

class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        req_id = request.headers.get("x-correlation-id", str(uuid.uuid4()))
        token = request_id_ctx.set(req_id)
        try:
            response = await call_next(request)
            response.headers["x-correlation-id"] = req_id
            return response
        finally:
            request_id_ctx.reset(token)