from fastapi import APIRouter, Response, Depends
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from app.core.metrics import setup_metrics
from app.core.auth_dependencies import require_admin

router = APIRouter(tags=["Monitoring"], dependencies=[Depends(require_admin)])

# Register the Redis-backed collector on route initialization
setup_metrics()

@router.get("/metrics")
def get_metrics():
    """
    Standard Prometheus metrics endpoint.
    Scraped periodically by Prometheus or Datadog.
    """
    metrics_data = generate_latest()
    return Response(content=metrics_data, media_type=CONTENT_TYPE_LATEST)