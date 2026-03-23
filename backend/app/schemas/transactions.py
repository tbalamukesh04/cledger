from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from decimal import Decimal

class TransactionCorrectionRequest(BaseModel):
    amount: Optional[Decimal] = Field(None, description="Corrected amount")
    currency: Optional[str] = Field(None, description="Corrected currency")
    txn_type: Optional[str] = Field(None, description="Corrected transaction type")
    txn_date: Optional[datetime] = Field(None, description="Corrected transaction date")
    remarks: Optional[str] = Field(None, description="Remarks for correction")

class TransactionInvalidationRequest(BaseModel):
    reason: Optional[str] = Field(None, description="Reason for invalidation")