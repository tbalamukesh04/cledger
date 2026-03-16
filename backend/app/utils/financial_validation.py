# backend/app/utils/financial_validation.py
import logging
from decimal import Decimal, InvalidOperation
from typing import Optional

logger = logging.getLogger(__name__)

EXTREME_AMOUNT_THRESHOLD = Decimal('1000000000.00')

CURRENCY_SYMBOL_MAP = {
    "$": "USD",
    "₹": "INR",
    "£": "GBP",
    "€": "EUR",
    "K": "ZMW",
    "ZMK": "ZMW"
}

def validate_and_convert_amount(raw_amount: float | str | None) -> Optional[Decimal]:
    """
    Safely converts an AI-extracted amount to a Python Decimal.
    Enforces positive values and flags extreme anomalies.
    """
    if raw_amount is None:
        return None
        
    try:
        # Convert to string first to prevent float precision drift during Decimal cast
        amount = Decimal(str(raw_amount))
        
        if amount <= Decimal('0'):
            logger.warning(f"Numeric Validation Failed: Amount must be positive. Received: {amount}")
            return None
            
        if amount > EXTREME_AMOUNT_THRESHOLD:
            # We don't reject it outright, but we flag it loudly for downstream review
            logger.warning(f"Anomaly Flagged: Extremely large transaction amount extracted -> {amount}")
            
        return amount

    except (InvalidOperation, ValueError, TypeError) as e:
        logger.error(f"Numeric Validation Failed: Could not convert '{raw_amount}' to Decimal. Error: {e}")
        return None

def normalize_currency_code(raw_currency: str | None, default_currency: str = "ZMW") -> str:
    """
    Standardizes currencies by converting symbols to 3-letter ISO codes and enforcing uppercase.
    """
    if not raw_currency:
        return default_currency
        
    cleaned_currency = raw_currency.strip().upper()
    
    if cleaned_currency in CURRENCY_SYMBOL_MAP:
        normalized = CURRENCY_SYMBOL_MAP[cleaned_currency]
        logger.info(f"Currency Normalized: Mapped '{raw_currency}' -> '{normalized}'")
        return normalized 

    if len(cleaned_currency) == 3 and cleaned_currency.isalpha():
        return cleaned_currency
        
    logger.warning(f"Currency Normalization Warning: Unrecognized format '{raw_currency}'. Defaulting to {default_currency}")
    return default_currency