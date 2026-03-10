import logging
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from redis import Redis

from app.api.dependencies import get_db, get_redis

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/health", tags=["Monitoring"])
def health_check(
    response: Response,
    db: Session = Depends(get_db),
    redis_client: Redis = Depends(get_redis)
):
    """
    Health check endpoint for infrastructure monitoring.
    Verifies API, Database, and Redis connectivity.
    """
    health_status = {
        "api": "ok",
        "database": "unknown", 
        "redis": "unknown"
    }

    try:
        db.execute(text('SELECT 1'))
        health_status["database"] = "ok"

    except Exception as e:
        logger.error("Database health check failed", exc_info=True)
        health_status["database"] = "unhealthy"

    try:
        if redis_client.ping():
            health_status["redis"] = "ok"
        else:
            health_status['redis'] = "unhealthy"

    except Exception as e:
        logging.error("Redis health check failed", exc_info=True)
        health_status['redis'] = "unhealthy"

    if health_status["database"] != "ok" or health_status["redis"] != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "degraded", "services": health_status}

    return {"status": "healthy", "services": health_status}