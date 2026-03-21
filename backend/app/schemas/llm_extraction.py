from pydantic import BaseModel, Field, StrictStr, StrictFloat, field_validator
from typing import Optional
import re
from app.utils.confidence_normalization import normalize_confidence

class LLMExtractionSchema(BaseModel):
    id: int
    amount: Optional[StrictFloat] = None
    currency: Optional[StrictStr] = None
    transaction_verb: Optional[StrictStr] = None
    transaction_date: Optional[StrictStr] = Field(None, alias="transaction_date")
    counterparty: Optional[StrictStr] = None
    reference: Optional[StrictStr] = None
    confidence_score : float = Field(
        ...,
        alias="confidence",
        description="Normalized confidence score representing LLM confidence"
    )
    prompt_version: Optional[str] = Field(
        default=None, 
        description="The version of the system prompt used to generate this extraction."
    )
    @field_validator("amount", mode="before")
    def clean_amount(cls, v):
        """Forgives LLM if it returns a string with commas/symbols, safely coercing to a numeric float."""
        if isinstance(v, str):
            v = v.replace(",", "").replace("$", "").strip()
            if not v:
                return None
            try:
                return float(v)
            except ValueError:
                raise ValueError("Amount must be a parsable numeric value")
        return v

    @field_validator("currency", mode="before")
    def clean_currency(cls, v):
        """Forces uppercase and strips whitespace."""
        if isinstance(v, str):
            cleaned = v.strip().upper()
            if len(cleaned) == 3:
                return cleaned
            raise ValueError(f"Currency must be exactly 3 string characters, got: {cleaned}")
        return v

    @field_validator("transaction_verb", mode="before")
    def clean_transaction_verb(cls, v):
        """Forgives capitalization variations from the LLM."""
        if isinstance(v, str):
            v = v.strip().lower()
            if v not in ["credit", "debit"]:
                raise ValueError(f"transaction_verb must be 'credit' or 'debit', got: {v}")
        return v
        
    @field_validator("transaction_date", mode="before")
    def clean_date(cls, v):
        """Ensures the LLM strictly provided a YYYY-MM-DD string."""
        if isinstance(v, str):
            v = v.strip()
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", v):
                raise ValueError(f"Date must be in string YYYY-MM-DD format, got: {v}")
        return v

    @field_validator("confidence_score", mode="before")
    def clean_confidence(cls, v):
        """Normalizes the confidence score to a float between 0 and 1."""
        return normalize_confidence(v)
        