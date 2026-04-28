import psutil
import os
import shutil
import logging
import psutil
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

@router.api_route("/health", methods=["GET", "HEAD"], tags=["Monitoring"])
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
        cpu_percent = psutil.cpu_percent(interval=0.1)
        checks['cpu_usage_percent'] = round(cpu_percent, 2)
        checks['cpu'] = 'unhealthy' if cpu_percent >= 95 else 'degraded' if cpu_percent >= 85 else 'ok'

        mem = psutil.virtual_memory()
        checks['memory_usage_percent'] = round(mem.percent, 2)
        checks['memory'] = 'unhealthy' if mem.percent >= 95 else 'degraded' if mem.percent >= 85 else 'ok'

        disk_path = "/" if os.name != "nt" else "C:\\"
        usage = shutil.disk_usage(disk_path)
        disk_percent = (usage.used / usage.total) * 100.0
        checks['disk_usage_percent'] = round(disk_percent, 2)
        checks['disk'] = 'unhealthy' if disk_percent >= (DISK_CRITICAL_THRESHOLD * 100) else 'degraded' if disk_percent >= (DISK_DEGRADED_THRESHOLD * 100) else 'ok'

    except Exception as e:
        log_error(LogEvent.SYSTEM_ERROR, error=e, message="Disk health check failed")
        checks['disk'] = "unknown"
        checks['cpu'] = "unknown"
        checks['memory'] = "unknown"

    if any(checks.get(k) == "unhealthy" for k in ["database", "redis", "queue", "disk", "cpu", "memory"]):
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unhealthy", "checks": checks}
    elif any(checks.get(k) == "degraded" for k in ["queue", "disk", "cpu", "memory"]):
        return {"status": "degraded", "checks": checks}
    else:
        return {"status": "healthy", "checks": checks}