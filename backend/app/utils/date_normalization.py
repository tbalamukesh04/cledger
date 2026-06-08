import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

def normalize_extracted_date(raw_date: Optional[str], context_timestamp: datetime) -> datetime:
    """
    Normalizes various AI-extracted date string formats to a timezone-aware UTC datetime object.
    Falls back safely to the context_timestamp if parsing fails or if raw_date is None.
    """
    if not raw_date:
        return context_timestamp

    cleaned_date = raw_date.strip().lower()

    try:
        if cleaned_date == "today":
            return context_timestamp
        elif cleaned_date == "yesterday":
            return context_timestamp - timedelta(days=1)
        elif cleaned_date == "tomorrow":
            return context_timestamp + timedelta(days=1)
        elif cleaned_date == "last week":
            return context_timestamp - timedelta(days=7)

        if re.match(r"^\d{4}-\d{2}-\d{2}$", cleaned_date):
            parsed = datetime.strptime(cleaned_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            return _validate_date_range(parsed, context_timestamp)

        match = re.match(r"^([a-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?$", cleaned_date)
        if match:
            month_str, day_str = match.groups()
            for fmt in ("%B %d", "%b %d"):
                try:
                    parsed_no_year = datetime.strptime(f"{month_str.capitalize()} {day_str}", fmt)
                    parsed = parsed_no_year.replace(year=context_timestamp.year, tzinfo=timezone.utc)
                    
                    if parsed > context_timestamp + timedelta(days=30):
                        parsed = parsed.replace(year=context_timestamp.year - 1)
                        
                    return _validate_date_range(parsed, context_timestamp)
                except ValueError:
                    continue

        logger.warning(f"Unrecognized AI date format: '{raw_date}'. Defaulting to context timestamp.")
        return context_timestamp

    except Exception as e:
        logger.error(f"Failed to normalize date '{raw_date}': {e}. Defaulting to context timestamp.")
        return context_timestamp

def _validate_date_range(parsed_date: datetime, context_timestamp: datetime) -> datetime:
    """
    Ensures the AI didn't hallucinate wildly out-of-bounds dates.
    Valid Range: 1 year in the past up to 30 days in the future.
    """
    min_date = context_timestamp - timedelta(days=365)
    max_date = context_timestamp + timedelta(days=30)
    
    if parsed_date < min_date or parsed_date > max_date:
        logger.warning(f"Anomaly Flagged: AI date {parsed_date.date()} is out of logical bounds. Overriding with context timestamp.")
        return context_timestamp
        
    return parsed_date