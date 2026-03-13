import logging
import json
from datetime import datetime, timezone
from app.schemas.jobs import WebhookJobPayload

logger = logging.getLogger(__name__)
def process_webhook_job(job: WebhookJobPayload) -> bool:
    """
    Core handler for processing webhook jobs dequeued from Redis.
    
    Args:
        job (WebhookJobPayload): The validated job payload.
        
    Returns:
        bool: True if processed successfully, False otherwise.
    """
    try:
        logger.info(json.dumps({
            "event_type": "job_processing_started", 
            "job_id": job.job_id,
            "raw_message_id": job.raw_message_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }))

        return True
    
    except Exception as e:
        logger.error(json.dumps({
            "event_type": "job_processing_failed",
            "job_id": job.job_id,
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }), exc_info=True)
        return False