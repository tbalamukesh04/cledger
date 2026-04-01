from enum import Enum
from typing import TypedDict, Any, Optional

class LogEvent(str, Enum):
    """Canonical list of system events for structured logging."""
    WEBHOOK_RECEIVED = "webhook_received"
    JOB_STARTED = "job_started"
    JOB_FAILED = "job_failed"
    TRANSACTION_CREATED = "transaction_created"
    LLM_CALLED = "llm_called"
    LLM_ERROR = "llm_error"
    REVIEW_FLAGGED = "review_flagged"
    
    # Operational events
    WORKER_STARTUP = "worker_startup"
    WORKER_SHUTDOWN = "worker_shutdown"
    REDIS_CONNECTION = "redis_connection"
    DB_CONNECTION = "db_connection"
    SYSTEM_ERROR = "system_error"

class LogSchema(TypedDict, total=False):
    """
    Standardized schema for structured JSON logging.
    Used to enforce field consistency across the backend and workers.
    """
    event: LogEvent
    message: str
    
    # Correlation & Tracing
    request_id: Optional[str]
    job_id: Optional[str]
    raw_message_id: Optional[str]
    transaction_id: Optional[str]
    
    # AI / Processing Metrics
    confidence: Optional[float]
    duration_ms: Optional[int]
    status: Optional[str]
    error_code: Optional[str]
    
    # Catch-all for extra contextual data
    details: Optional[dict[str, Any]]