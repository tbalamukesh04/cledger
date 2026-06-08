from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Dict

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
    text_hash: str = Field(..., description="SHA256 hash of the normalized text")
    idempotency_identifier: str = Field(..., description="Unique identifier for idempotency")

class ScoringResult(BaseModel):
    """
    Stores the extracted boolean signals, rule breakdown, and the computed deterministic score.
    """
    amount_detected: bool = Field(default=False)
    currency_detected: bool = Field(default=False)
    date_detected: bool = Field(default=False)
    transaction_verb_detected: bool = Field(default=False)
    negative_context: bool = Field(default=False)
    
    rule_breakdown: Dict[str, int] = Field(default_factory=dict, description="Detailed breakdown of points awarded/deducted per rule")
    total_score: int = Field(default=0, description="The computed score from the deterministic engine")
    
    is_transaction_candidate: bool = Field(default=False, description="True if total_score >= threshold. Determines if it goes to AI.")

class ProcessingContext(BaseModel):
    """Wraps the preprocessed payload and subsequent pipeline results like scoring."""
    payload: PreprocessedPayload 
    scoring: Optional[ScoringResult] = None
    extraction_confidence: Optional[float] = Field(
        default = None, 
        description = "Normalized confidence score from the LLM extraction, used for downstream routing. "
    )