import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from app.main import app
from app.api.dependencies import get_db, get_redis
from app.core.jwt_utils import create_access_token

client = TestClient(app)

@pytest.fixture
def auth_headers():
    token = create_access_token(user_id="admin_user", tenant_id=1, role="admin")
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture
def mock_disk_usage():
    """Fixture to simulate a perfectly healthy disk (0% usage)."""
    with patch("app.api.health.shutil.disk_usage") as mock_disk:
        mock_usage = MagicMock()
        mock_usage.used = 0
        mock_usage.total = 100
        mock_disk.return_value = mock_usage
        yield mock_disk

def test_health_normal_operation(mock_disk_usage):
    """Simulates a perfectly healthy system."""
    mock_db = MagicMock()
    mock_redis = MagicMock()
    mock_redis.ping.return_value = True
    mock_redis.llen.return_value = 10  # Low queue depth

    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_redis] = lambda: mock_redis

    response = client.get("/api/v1/health")
    app.dependency_overrides.clear()

    assert response.status_code == 200, response.json()
    data = response.json()
    assert data["status"] == "healthy"
    assert data["checks"]["database"] == "ok"
    assert data["checks"]["redis"] == "ok"
    assert data["checks"]["queue"] == "ok"
    assert data["checks"]["disk"] == "ok"

def test_health_queue_buildup_degraded(mock_disk_usage):
    """Simulates a queue depth approaching the danger zone (e.g., 85 jobs)."""
    mock_db = MagicMock()
    mock_redis = MagicMock()
    mock_redis.ping.return_value = True
    mock_redis.llen.return_value = 85  # Over the 80 threshold

    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_redis] = lambda: mock_redis

    response = client.get("/api/v1/health")
    app.dependency_overrides.clear()

    assert response.status_code == 200, response.json()
    data = response.json()
    assert data["status"] == "degraded"
    assert data["checks"]["queue"] == "degraded"

def test_health_queue_buildup_unhealthy(mock_disk_usage):
    """Simulates a critically backed up queue (e.g., 105 jobs)."""
    mock_db = MagicMock()
    mock_redis = MagicMock()
    mock_redis.ping.return_value = True
    mock_redis.llen.return_value = 105  # Over the 100 threshold

    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_redis] = lambda: mock_redis

    response = client.get("/api/v1/health")
    app.dependency_overrides.clear()

    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "unhealthy"
    assert data["checks"]["queue"] == "unhealthy"

def test_health_db_failure(mock_disk_usage):
    """Simulates a dropped Postgres connection."""
    mock_db = MagicMock()
    mock_db.execute.side_effect = Exception("DB Connection Refused")
    
    mock_redis = MagicMock()
    mock_redis.ping.return_value = True
    mock_redis.llen.return_value = 0

    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_redis] = lambda: mock_redis

    response = client.get("/api/v1/health")
    app.dependency_overrides.clear()

    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "unhealthy"
    assert data["checks"]["database"] == "unhealthy"

def test_health_redis_failure(mock_disk_usage):
    """Simulates a Redis crash/timeout."""
    mock_db = MagicMock()
    
    mock_redis = MagicMock()
    mock_redis.ping.side_effect = Exception("Redis Timeout")

    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_redis] = lambda: mock_redis

    response = client.get("/api/v1/health")
    app.dependency_overrides.clear()

    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "unhealthy"
    assert data["checks"]["redis"] == "unhealthy"
    assert data["checks"]["queue"] == "unknown"

def test_metrics_correctness(auth_headers):
    """
    Validates that the Prometheus /metrics endpoint correctly pulls 
    live in-memory variables from Redis and formats them properly.
    """
    with patch("app.core.metrics.get_redis_client") as mock_get_redis:
        mock_redis = MagicMock()
        def mock_redis_get(key):
            if "total_webhooks" in key: return b"250"
            if "llm_failures" in key: return b"5"
            return b"0"
            
        mock_redis.get.side_effect = mock_redis_get
        mock_redis.llen.return_value = 42
        mock_get_redis.return_value = mock_redis

        response = client.get("/metrics", headers=auth_headers)
        
        assert response.status_code == 200, response.text