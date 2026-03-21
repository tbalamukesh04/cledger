import re
from typing import Optional, Literal, Union
from pydantic import BaseModel, Field, field_validator, StrictStr, StrictFloat, StrictInt

class LLMExtractionSchema(BaseModel):
    """
    Strict validation schema for the incoming LLM JSON payload.
    Uses Strict types to prevent silent implicit casting (e.g. converting ints to strings).
    """
    id: StrictStr = Field(..., description="Originating raw_message_id for batch mapping")
    
    # Amount and Confidence must be numeric (accepting both strictly typed ints and floats)
    amount: Optional[Union[StrictFloat, StrictInt]] = Field(..., ge=0.0, description="The monetary amount extracted")
    confidence: Union[StrictFloat, StrictInt] = Field(..., ge=0.0, le=1.0, description="Extraction confidence score")
    
    # Text fields must be strictly strings, preventing list/dict/int hallucinations
    currency: Optional[StrictStr] = Field(..., min_length=3, max_length=3, description="The 3-letter currency code")
    transaction_verb: Optional[Literal["credit", "debit"]] = Field(..., description="The type of transaction")
    transaction_date: Optional[StrictStr] = Field(..., alias="date", description="ISO 8601 date string (YYYY-MM-DD)")
    counterparty: Optional[StrictStr] = Field(..., description="The counterparty of the transaction")
    reference: Optional[StrictStr] = Field(..., description="The reference of the transaction")

    # --- Fallback / Coercion Handlers

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