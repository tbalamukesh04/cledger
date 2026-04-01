import os
import shutil
import logging
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from redis import Redis

from app.api.dependencies import get_db, get_redis
from app.database.redis_client import WEBHOOK_QUEUE_NAME
from app.utils.logger import log_error
from app.core.log_events import LogEvent

router = APIRouter()

QUEUE_CRITICAL_THRESHOLD = int(os.getenv("QUEUE_CRITICAL_THRESHOLD", 100))
QUEUE_DEGRADED_THRESHOLD = int(os.getenv("QUEUE_DEGRADED_THRESHOLD", 80))
DISK_DEGRADED_THRESHOLD = float(os.getenv("DISK_DEGRADED_THRESHOLD", 0.85))
DISK_CRITICAL_THRESHOLD = float(os.getenv("DISK_CRITICAL_THRESHOLD", 0.90))

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
    checks = {
        "database": "unknown", 
        "redis": "unknown",
        "queue": "unknown",
        "disk": "unknown"
    }

    try:
        db.execute(text('SELECT 1'))
        checks["database"] = "ok"

    except Exception as e:
        log_error(LogEvent.SYSTEM_ERROR, error=e, message="Database health check failed")
        checks["database"] = "unhealthy"

    try:
        if redis_client.ping():
            checks["redis"] = "ok"

            queue_depth = redis_client.llen(WEBHOOK_QUEUE_NAME)
            checks['queue_depth'] = queue_depth

            if queue_depth >= QUEUE_CRITICAL_THRESHOLD:
                checks['queue'] = 'unhealthy'
            elif queue_depth >= QUEUE_DEGRADED_THRESHOLD:
                checks['queue'] = 'degraded'
            else:
                checks['queue'] = 'ok'

        else:
            checks['redis'] = "unhealthy"
            checks['queue'] = 'unknown'

    except Exception as e:
        log_error(LogEvent.SYSTEM_ERROR, error=e, message="Redis health check failed")
        checks['redis'] = "unhealthy"
        checks['queue'] = 'unknown'

    try:
        disk_path = "/" if os.name != "nt" else "C:\\"
        usage = shutil.disk_usage(disk_path)
        disk_percent = (usage.used / usage.total) * 100.0
        checks['disk_usage_percent'] = round(disk_percent, 2)

        if disk_percent >= DISK_CRITICAL_THRESHOLD:
            checks['disk'] = 'unhealthy'
        elif disk_percent >= DISK_DEGRADED_THRESHOLD:
            checks['disk'] = 'degraded'
        else:
            checks['disk'] = 'ok'

    except Exception as e:
        log_error(LogEvent.SYSTEM_ERROR, error=e, message="Disk health check failed")
        checks['disk'] = "unknown"

    if checks["database"] == "unhealthy" or checks["redis"] == "unhealthy" or checks["queue"] == "unhealthy" or checks["disk"] == "unhealthy":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unhealthy", "checks": checks}
    elif checks["queue"] == "degraded" or checks["disk"] == "degraded":
        return {"status": "degraded", "checks": checks}
    else:
        return {"status": "healthy", "checks": checks}