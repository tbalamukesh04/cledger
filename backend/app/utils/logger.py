import logging
import time
from typing import Any, Dict, Optional
from app.core.log_events import LogEvent
from app.config.logging_config import request_id_ctx, job_id_ctx

logger = logging.getLogger(__name__)

def bind_context(request_id: Optional[str] = None, job_id: Optional[str] = None) -> None:
    """Binds request/job IDs to the current context for structured logging."""
    if request_id:
        request_id_ctx.set(request_id)
    if job_id:
        job_id_ctx.set(job_id)

def log_event(event: LogEvent, message: str, level: int = logging.INFO, **kwargs: Any) -> None:
    """
    Logs a structured JSON event.
    
    Args:
        event (LogEvent): The canonical event name from the LogEvent enum.
        message (str): A human-readable description of the event.
        level (int): The logging level (default: logging.INFO).
        **kwargs: Additional contextual data (e.g., transaction_id, confidence, duration_ms).
                  These will be automatically PII-redacted by the formatter.
    """
    log_data = {
        "event": event.value,
        "message": message, 
        **kwargs
    }
    logger.log(level, log_data)

def log_error(event: LogEvent, error: Exception, message: Optional[str] = None, **kwargs: Any) -> None:
    """
    Logs a structured error event and automatically attaches exception tracebacks.
    
    Args:
        event (LogEvent): The canonical event name.
        error (Exception): The exception object caught.
        message (str, optional): Custom error message. Defaults to the exception string.
        **kwargs: Additional contextual data.
    """
    log_data = {
        "event": event.value,
        "message": message or str(error),
        "error_type": type(error).__name__,
        "error_details": str(error),
        **kwargs
    }
    logger.error(log_data, exc_info=True)

class LogTimer:
    """
    A simple context manager/utility to track duration in milliseconds 
    for performance logging (e.g., tracking LLM call latency).
    """
    def __init__(self):
        self.start_time = time.perf_counter()

    def get_duration_ms(self) -> int:
        """Returns the elapsed time since initialization in milliseconds."""
        return int((time.perf_counter() - self.start_time) * 1000)