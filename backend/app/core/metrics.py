import logging
from prometheus_client.core import REGISTRY, CounterMetricFamily, GaugeMetricFamily
from app.database.redis_client import get_redis_client, WEBHOOK_QUEUE_NAME

logger = logging.getLogger(__name__)

class CledgerMetricsCollector:
    """
    Custom Prometheus Collector that pulls live metrics from Redis.
    This solves multi-process metric tracking (API vs Worker) effortlessly.
    """
    def collect(self):
        try:
            # We call get_redis_client here so tests can patch it globally
            redis = get_redis_client()
            
            webhooks = int(redis.get("metrics:total_webhooks") or 0)
            transactions = int(redis.get("metrics:total_transactions") or 0)
            llm_calls = int(redis.get("metrics:llm_calls") or 0)
            llm_failures = int(redis.get("metrics:llm_failures") or 0)
            jobs_pending = redis.llen(WEBHOOK_QUEUE_NAME) or 0
        except Exception as e:
            logger.error(f"Failed to fetch metrics from Redis: {e}")
            webhooks = transactions = llm_calls = llm_failures = jobs_pending = 0

        yield CounterMetricFamily('cledger_total_webhooks', 'Total webhooks received', value=webhooks)
        yield CounterMetricFamily('cledger_total_transactions', 'Total transactions created', value=transactions)
        yield CounterMetricFamily('cledger_llm_calls', 'Total LLM API calls', value=llm_calls)
        yield CounterMetricFamily('cledger_llm_failures', 'Total failed LLM API calls', value=llm_failures)
        yield GaugeMetricFamily('cledger_jobs_pending', 'Current pending jobs in webhook queue', value=jobs_pending)

_is_registered = False

def setup_metrics():
    """Registers the custom collector exactly once to prevent duplicate metrics."""
    global _is_registered
    if not _is_registered:
        REGISTRY.register(CledgerMetricsCollector())
        _is_registered = True

def inc_metric(metric_name: str, amount: int = 1):
    """Increments a fast in-memory metric backed by Redis."""
    try:
        redis = get_redis_client()
        redis.incrby(f"metrics:{metric_name}", amount)
    except Exception as e:
        logger.error(f"Metric increment failed for {metric_name}: {e}")