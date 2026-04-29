import logging
import json
import sys
import os
import contextvars
from logging.handlers import TimedRotatingFileHandler, WatchedFileHandler
from datetime import datetime, timezone
from app.config.pii_policy import apply_field_redaction, redact_unstructured_text

request_id_ctx = contextvars.ContextVar("request_id", default = None)
job_id_ctx = contextvars.ContextVar("job_id", default=None)

PII_KEYS = {
    "phone_number", "email", "account_number", "upi_id", 
    "message_text", "raw_message_text", "name", 
    "api_key", "token", "signature"
}

def redact_dict(d: dict) -> dict:
    redacted = {}
    for k, v in d.items():
        if k.lower() in PII_KEYS:
            redacted[k] = apply_field_redaction(k,v)

        elif isinstance(v, dict):
            redacted[k] = redact_dict(v)

        elif isinstance(v, list):
            redacted[k] = [redact_dict(i) if isinstance(i, dict) else i for i in v]
        else:
            redacted[k] = v
    return redacted

class JSONFormatter(logging.Formatter):
    """
    Custom formatter to output logs as JSON strings.
    """
    def format(self, record: logging.LogRecord) -> str:
        # Construct the structured log dictionary
        log_record = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "name": record.name,
            "service": "cledger-backend", 
        }
        
        req_id = request_id_ctx.get()
        if req_id:
            log_record["request_id"] = req_id
        job_id = job_id_ctx.get()

        if job_id:
            log_record["job_id"] = job_id
        
        if isinstance(record.msg, dict):
            msg_data = record.msg
        else:
            try:
                msg_data = json.loads(record.getMessage())
            except (json.JSONDecodeError, TypeError):
                msg_data = {"message": record.getMessage()}

        for key, value in record.__dict__.items():
            if key not in logging.LogRecord(None, None, "", 0, "", (), None, None).__dict__ and key not in ("message", "asctime"):
                msg_data[key] = value
        
        redacted_msg = redact_dict(msg_data)
        log_record.update(redacted_msg)

        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
        elif record.exc_text:
            log_record["exception"] = record.exc_text

        return json.dumps(log_record)

def setup_logging():
    """
    Configures the root logger and standardizes Uvicorn/FastAPI loggers 
    to output structured JSON.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Clear any existing handlers
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    formatter = JSONFormatter()

    # Set up the console handler with the JSON formatter
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    log_dir_primary = '/var/log/app/'
    log_file_primary = os.path.join(log_dir_primary, 'app.log')
    log_dir_fallback = os.path.join(os.getcwd(), "logs")
    log_file_fallback = os.path.join(log_dir_fallback, "app.log")

    file_handler = None
    try:
        os.makedirs(log_dir_primary, exist_ok=True)
        file_handler = WatchedFileHandler(log_file_primary, encoding="utf-8")
    
    except (PermissionError, OSError):
        os.makedirs(log_dir_fallback, exist_ok=True)
        file_handler = TimedRotatingFileHandler(
            log_file_fallback, when="midnight", interval=1, backupCount=7, encoding="utf-8"
        )
    
    if file_handler:
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # Hijack Uvicorn's loggers to use our JSON formatting
    for logger_name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        uv_logger = logging.getLogger(logger_name)
        uv_logger.handlers.clear()
        uv_logger.addHandler(console_handler)
        if file_handler:
            uv_logger.addHandler(file_handler)
        uv_logger.propagate = False  # Prevent double logging