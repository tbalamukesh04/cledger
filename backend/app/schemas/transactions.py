from pydantic import BaseModel, Field, model_validator, ConfigDict
from typing import Optional, Dict, Any, List
from datetime import datetime
from decimal import Decimal
from enum import Enum
from fastapi import HTTPException
from app.core.config import api_security_settings
from app.models.transactions import TransactionStatus

class ParticipantDetail(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    participant_id: int = Field(alias="id")
    participant_name: Optional[str] = Field(None, alias="displayname")
    participant_phone: str = Field(alias="phone")

class MessageMetadata(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    message_id: int
    message_text: str = Field(alias="raw_text")
    message_timestamp: Optional[datetime] = Field(alias="received_at")

class AuditHistoryResponse(BaseModel):
    id: int
    action: str
    performed_by: Optional[str] = None
    old_snapshot: Optional[Dict[str, Any]] = None
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class TransactionDetail(BaseModel):
    id: int
    raw_message_id: Optional[int] = None
    amount: Optional[Decimal] = None
    currency: Optional[str] = None
    remarks: Optional[str] = None
    txn_date: Optional[datetime] = None
    status: Any = None
    confidence: Optional[float] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    participant: Optional[ParticipantDetail] = None
    message_metadata: Optional[MessageMetadata] = None

    @model_validator(mode="before")
    @classmethod
    def extract_nested_relations(cls, values):
        # If it's already a dict, bypass manual ORM extraction
        if isinstance(values, dict):
            return values
            
        # Map ORM object fields to the schema
        res = {
            "id": getattr(values, "id", None),
            "raw_message_id": getattr(values, "raw_message_id", None),
            "amount": getattr(values, "amount", None),
            "currency": getattr(values, "currency", None),
            "remarks": getattr(values, "remarks", None),
            "txn_date": getattr(values, "txn_date", None),
            "status": getattr(values, "status", None),
            "confidence": getattr(values, "confidence", None),
            "created_at": getattr(values, "created_at", None),
            "updated_at": getattr(values, "updated_at", None),
        }
        
        # Safely extract message metadata and participant
        raw_msg = getattr(values, "raw_message", None)
        if raw_msg:
            res["message_metadata"] = MessageMetadata(
                message_id=getattr(raw_msg, "id", ""),
                message_timestamp=getattr(raw_msg, "received_at", None),
                message_text=getattr(raw_msg, "raw_text", "")
            )
            sender = getattr(raw_msg, "sender", None)
            if sender:
                res["participant"] = ParticipantDetail(
                    id=sender.id,
                    phone=getattr(sender, "phone", ""),
                    displayname=getattr(sender, "displayname", None)
                )
        return res

    model_config = ConfigDict(from_attributes=True)

class SingleTransactionResponse(BaseModel):
    transaction: TransactionDetail
    audit_history: List[AuditHistoryResponse] = []
    
    model_config = ConfigDict(from_attributes=True)

class TransactionCorrectionRequest(BaseModel):
    amount: Optional[Decimal] = Field(None, description="Corrected amount")
    currency: Optional[str] = Field(None, description="Corrected currency")
    txn_type: Optional[str] = Field(None, description="Corrected transaction type")
    txn_date: Optional[datetime] = Field(None, description="Corrected transaction date")
    remarks: Optional[str] = Field(None, description="Remarks for correction")

class ReviewAction(str, Enum):
    CORRECT = "correct"
    INVALIDATE = "invalidate"
    
class TransactionReviewRequest(BaseModel):
    action: ReviewAction = Field(..., description = "Fields to modify if action is correct")
    corrected_fields: Optional[Dict[str, Any]] = Field(None, description = "Fields to modify if action is correct")
    
    @model_validator(mode="after")
    def validate_action_fields(self):
        if self.action == ReviewAction.CORRECT and not self.corrected_fields:
            raise ValueError("corrected_fields is required when action is 'correct'")
        if self.action == ReviewAction.INVALIDATE and self.corrected_fields:
            raise ValueError("corrected_fields must be empty when action is 'invalidate'")
        return self
        
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

    @model_validator(mode="after")
    def enforce_pagination_limits(self):
        if self.limit > api_security_settings.MAX_PAGINATION_LIMIT:
            raise HTTPException(status_code=400, detail=f"Limit exceeds maximum allowed value of {api_security_settings.MAX_PAGINATION_LIMIT}")
        if self.limit < 1:
            raise HTTPException(status_code=400, detail="Limit must be at least 1")
        if self.offset < 0:
            raise HTTPException(status_code=400, detail="Offset must be non-negative")
        
        if self.date_from and self.date_to  and self.date_from > self.date_to:
            raise HTTPException(status_code=400, detail="date_from must be before date_to")

        if self.amount_min is not None and self.amount_max is not None and self.amount_min > self.amount_max:
            raise HTTPException(status_code=400, detail="amount_min must be less than or equal to amount_max")
        
        if self.amount_min is not None and self.amount_min < 0:
            raise HTTPException(status_code=400, detail="amount_min must be non-negative")
        
        if self.amount_max is not None and self.amount_max < 0:
            raise HTTPException(status_code=400, detail="amount_max must be non-negative")
        
        if self.status:
            valid_statuses = [e.value for e in TransactionStatus]
            if self.status not in valid_statuses:
                raise HTTPException(status_code=400, detail=f"Invalid status. Allowed values: {', '.join(valid_statuses)}")
        
        if self.participant and len(self.participant.strip()) < 2:
            raise HTTPException(status_code=400, detail="Participant name or phone must be at least 2 characters long")
        return self