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

setup_logging()
logging.basicConfig(
    level = logging.INFO, 
    format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Backend Service..")

    try:
        with engine.connect() as conn:
            logger.info("Database connection successful.")

    except Exception as e:
        logger.error(f"Database connection failed: {e}.")
        raise e

    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        logger.warning("REDIS URL environment variable not set. Using default")
        redis_url = "redis://localhost:6379/0"

    try:
        app.state.redis = redis.Redis.from_url(redis_url, decode_responses=True)
        app.state.redis.ping()
        logger.info("Redis connection successful.")

    except Exception as e:
        logger.error(f"Redis connection failed: {e}")
        raise e

    yield

    logger.info("Shutting down Cledger backend service")
    engine.dispose()
    logger.info("Database connection disposed.")
    app.state.redis.close()
    logger.info("Redis connection closed.")

app = FastAPI(
    title = "Cledger Backend API",
    description = "Finance Application Backend",
    version = "1.0.0",
    docs_url = "/docs",
    redoc_url = "/redoc",
    lifespan=lifespan
)

app.include_router(health_router, prefix="/api/v1")
app.include_router(webhook_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")
app.include_router(export_router, prefix="/api/v1")
app.include_router(transactions_admin_router, prefix="/api/v1")
app.include_router(transactions_router, prefix="/api/v1")

@app.get("/", tags=["Root"])
async def root():
    return {"message": "Welcome to Cledger API"}

if __name__ == "__main__":
    uvicorn.run("app.main:app", host= "0.0.0.0", port=8000, reload=True)