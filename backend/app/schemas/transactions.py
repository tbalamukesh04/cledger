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

class TransactionQueryParams(BaseModel):
    status: Optional[str] = Field(None, description="Filter by transaction status")
    date_from: Optional[datetime] = Field(None, description="Start date for filtering")
    date_to: Optional[datetime] = Field(None, description="End date for filtering")
    amount_min: Optional[Decimal] = Field(None, description="Minimum amount")
    amount_max: Optional[Decimal] = Field(None, description="Maximum amount")
    participant: Optional[str] = Field(None, description="Filter by participant name or phone")
    currency: Optional[str] = Field(None, description="Filter by currency (e.g., USD, INR)")
    limit: int = Field(50, ge=1, le=200, description="Number of records to return (max 200)")
    offset: int = Field(0, ge=0, description="Number of records to skip")
    sort_by: str = Field("created_at", description="Field to sort by (e.g., created_at, txn_date, amount)")
    sort_order: str = Field("desc", description="Sort order (asc or desc)")