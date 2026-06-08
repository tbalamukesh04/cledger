
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

SYSTEM_MINIMUM_DATE = datetime(2026, 3, 3, tzinfo=timezone.utc)
FUTURE_TOLERANCE_BUFFER = timedelta(minutes=5)

def convert_epoch_to_utc_datetime(epoch: int | float | None) -> datetime | None:
    """
    Converts a Unix epoch timestamp into a timezone-aware UTC datetime object.
    
    Args:
        epoch: The numeric epoch timestamp (in seconds).
        
    Returns:
        A timezone-aware datetime object in UTC, or None if conversion fails.
    """
    if epoch is None:
        return None
        
    try:
        dt = datetime.fromtimestamp(epoch, tz=timezone.utc)

        if dt < SYSTEM_MINIMUM_DATE:
            logger.warning(f"Timestamp validation failed: {dt.isoformat()} precedes system minimum date of {SYSTEM_MINIMUM_DATE.isoformat()}.")
            return None

        current_time_utc = datetime.now(timezone.utc)
        if dt > (current_time_utc + FUTURE_TOLERANCE_BUFFER):
            logger.warning(f"Timestamp validation failed: {dt.isoformat()} is too far in the future (Current UTC: {current_time_utc.isoformat()})")
            return None

        return dt
        
    except (ValueError, TypeError, OSError, OverflowError) as e:
        logger.warning(f"Failed to convert epoch {epoch} to UTC datetime: {e}")
        return None