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
    
    # --- Sender Metadata ---
    participant_id: int = Field(..., description="Internal database ID of the sender")
    sender_phone: Optional[str] = Field(None, description="WhatsApp phone number of the sender")
    sender_name: Optional[str] = Field(None, description="Display name of the sender")
    
    # --- Group Metadata ---
    group_id: Optional[int] = Field(None, description="Internal database ID of the group context")
    group_whatsapp_id: Optional[str] = Field(None, description="External WhatsApp group identifier")
    group_name: Optional[str] = Field(None, description="Display name of the group")
    
    # --- Step 7: Normalized Timestamp ---
    normalized_timestamp: datetime = Field(..., description="Timezone-aware UTC datetime of the message")
    
    # --- General Message Metadata ---
    message_id: str = Field(..., description="External WhatsApp message identifier")
    message_type: str = Field(..., description="The type of webhook event (e.g., text, image)")
    normalized_text: Optional[str] = Field(None, description="Cleaned and standardized message text")