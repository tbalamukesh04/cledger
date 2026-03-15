# backend/app/schemas/preprocessing.py
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class PreprocessedPayload(BaseModel):
    """
    Structured object containing the normalized message data and metadata 
    prepared for downstream classification and transaction parsing.
    """
    raw_message_id: int = Field(..., description="Internal database ID of the raw message record")
    participant_id: int = Field(..., description="Internal database ID of the sender")
    sender_phone: Optional[str] = Field(None, description="WhatsApp phone number of the sender")
    sender_name: Optional[str] = Field(None, description="Display name of the sender")
    group_id: Optional[int] = Field(None, description="Internal database ID of the group context")
    group_whatsapp_id: Optional[str] = Field(None, description="External WhatsApp group identifier")
    group_name: Optional[str] = Field(None, description="Display name of the group")
    normalized_timestamp: datetime = Field(..., description="Timezone-aware UTC datetime of the message")   
    message_id: str = Field(..., description="External WhatsApp message identifier")
    message_type: str = Field(..., description="The type of webhook event (e.g., text, image)")
    normalized_text: Optional[str] = Field(None, description="Cleaned and standardized message text")
    message_hash: str = Field(..., description="SHA256 hash of the message content")
    idempotency_identifier: str = Field(..., description="Unique identifier for idempotency")