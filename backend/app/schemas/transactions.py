from pydantic import BaseModel, Field, model_validator, ConfigDict
from typing import Optional, Dict, Any, List
from datetime import datetime
from decimal import Decimal

class ParticipantDetail(BaseModel):
    id: int
    phone: str
    displayname: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class MessageMetadata(BaseModel):
    id: int
    whatsapp_message_id: str
    received_at: Optional[datetime] = None
    raw_text: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

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
                id=raw_msg.id,
                whatsapp_message_id=getattr(raw_msg, "message_id", ""),
                received_at=getattr(raw_msg, "received_at", None),
                raw_text=getattr(raw_msg, "raw_text", None)
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