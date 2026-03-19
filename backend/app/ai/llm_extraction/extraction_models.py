from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import date

class TransactionExtractionResult(BaseModel):
    """
    Structured object representing the extracted transaction fields.
    Enforces strict typing and allows clean JSON serialization.
    """
    amount: Optional[float] = Field(None, description="The extracted monetary amount")
    currency: Optional[str] = Field(None, min_length=3, max_length=3, description="The 3-letter currency code (e.g., ZMW, USD)")
    transaction_verb: Optional[Literal["credit", "debit"]] = Field(None, description="Whether the transaction is a credit (in) or debit (out)")
    transaction_date: Optional[date] = Field(None, description="The resolved date of the transaction")
    counterparty: Optional[str] = Field(None, description="The other party involved (sender/receiver)")
    reference: Optional[str] = Field(None, description="Contextual note or reference for the transaction")
    confidence: float = Field(0.0, ge=0.0, le=1.0, description="AI extraction confidence score")
    model_version: str = Field(..., description="The Gemini model version utilized")
    prompt_version: str = Field(..., description="The prompt template version utilized")

    def to_dict(self) -> dict:
        return self.model_dump(mode='json')