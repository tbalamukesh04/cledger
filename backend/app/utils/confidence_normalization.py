import logging
from typing import Any

logger = logging.getLogger(__name__)

def normalize_confidence(value: Any) -> float:
    """
    Normalizes the confidence score to a float between 0 and 1.
    """
    if value is None:
        return 0.0

    try:
        if isinstance(value, str):
            value = value.replace("%", "").strip()

        float_val = float(value)

        if 1.0 < float_val <=100.0:
            float_val = float_val/100.0

        if float_val < 0.0:
            float_val = 0.0

        elif float_val> 1.0:
            float_val = 1.0

        return round(float_val, 4)

    except (ValueError, TypeError) as e:
        logger.warning(f"Failed to normalize confidence score '{value}': {e}")
        return 0.0
        