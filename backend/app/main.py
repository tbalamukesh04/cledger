import uvicorn 
from fastapi import FastAPI
import logging
import os
import redis
from contextlib import asynccontextmanager
from app.database.database import engine
from app.config.logging_config import setup_logging

from app.api.health import router as health_router
from app.api.webhook import router as webhook_router
from app.api.admin import router as admin_router
from app.api.export import router as export_router
from app.api.transactions_admin import router as transactions_admin_router
from app.api.transactions import router as transactions_router
from app.api.metrics import router as metrics_router
from app.api.version import router as version_router
from app.api.auth import router as auth_router
from app.api.whatsapp_auth import router as whatsapp_auth_router
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from app.middleware.correlation import CorrelationIdMiddleware
from app.utils.logger import log_event, log_error, LogTimer
from app.core.log_events import LogEvent

setup_logging()
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    log_event(LogEvent.WORKER_STARTUP, "Starting Backend Service..")

    try:
        with engine.connect() as conn:
            log_event(LogEvent.DB_CONNECTION, "Database connection successful.")

    except Exception as e:
        log_event(LogEvent.SYSTEM_ERROR, error=str(e), message="Database connection failed.")
        raise e

    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        log_event(LogEvent.SYSTEM_ERROR, message="REDIS URL environment variable not set. Using default", level=logging.WARNING)
        redis_url = "redis://localhost:6379/0"

    try:
        app.state.redis = redis.Redis.from_url(redis_url, decode_responses=True)
        app.state.redis.ping()
        log_event(LogEvent.REDIS_CONNECTION, "Redis connection successful.", status="connected")

    except Exception as e:
        log_event(LogEvent.SYSTEM_ERROR, error=str(e), message="Redis connection failed.")
        raise e

    yield

    log_event(LogEvent.WORKER_SHUTDOWN, "Shutting down Cledger backend service")
    engine.dispose()
    log_event(LogEvent.DB_CONNECTION, "Database connection disposed.", status="closed")
    app.state.redis.close()
    log_event(LogEvent.REDIS_CONNECTION, "Redis connection closed.", status="closed")

app = FastAPI(
    title = "Cledger Backend API",
    description = "Finance Application Backend",
    version = "1.0.0",
    docs_url = "/docs",
    redoc_url = "/redoc",
    lifespan=lifespan
)

app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")
app.add_middleware(CorrelationIdMiddleware)

from app.utils.api_errors import setup_exception_handlers
setup_exception_handlers(app)

app.include_router(auth_router, prefix="/api/v1")
app.include_router(whatsapp_auth_router, prefix="/api/v1")
app.include_router(health_router, prefix="/api/v1")
app.include_router(webhook_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")
app.include_router(export_router, prefix="/api/v1")
app.include_router(transactions_admin_router, prefix="/api/v1")
app.include_router(transactions_router, prefix="/api/v1")
app.include_router(version_router, prefix="/api/v1")
app.include_router(metrics_router)

@app.get("/", tags=["Root"])
async def root():
    return {"message": "Welcome to Cledger API"}

@app.get("/dev-token", tags=["Root"])
async def get_dev_token():
    """
    Temporary unprotected endpoint to generate a valid JWT token 
    for Flutter E2E testing.
    """
    from app.core.jwt_utils import create_access_token
    # Signed with the server's actual SECRET_KEY
    token = create_access_token(user_id=1, tenant_id=1, role="admin")
    return {"access_token": token}

# if __name__ == "__main__":
#     is_dev = os.getenv("ENVIRONMENT", "production").lower() == "development"
#     api_host = os.getenv("API_HOST", "127.0.0.1")
#     api_port = int(os.getenv("API_PORT", 8000))
    
#     uvicorn.run("app.main:app", host=api_host, port=api_port, reload=is_dev)

if __name__ == "__main__":
    is_dev = os.getenv("ENVIRONMENT", "production").lower() == "development"
    # Fallback to 0.0.0.0 to allow mobile interfaces to bridge sockets cleanly
    api_host = os.getenv("API_HOST", "0.0.0.0")
    api_port = int(os.getenv("API_PORT", 8000))
    
    uvicorn.run("app.main:app", host=api_host, port=api_port, reload=is_dev)
