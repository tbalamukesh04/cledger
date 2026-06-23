from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Dict, Any
import uuid 

class WebhookJobPayload(BaseModel):
    """
    Standardized job payload for async webhook processing.
    """
    job_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique identifier for this specific background job")
    tenant_id: int = Field(..., description="The internal database ID of the Tenant (businesses table)")
    business_id: str = Field(..., description="The Meta WABA ID or Business Organization ID mapped to the tenant")
    phone_number_id: str = Field(..., description="The Meta Phone Number ID mapped to the tenant")
    message_id: str = Field(..., description="The original WhatsApp Message ID")
    raw_message_id: int = Field(..., description="The internal database ID of the RawMessages record")
    participant_id: int = Field(..., description="The internal database ID of the Participant sender")
    group_id: int = Field(..., description="The internal database ID of the Group context")
    message_timestamp: datetime = Field(..., description="The exact time the message was sent by the user")
    webhook_event_type: str = Field(..., description="The type of event (e.g., 'text_message', 'image_message')")
    ingestion_time: datetime = Field(..., description="The server time when the webhook was ingested")
    retry_count: int = Field(default=0, description='Number of times the job has been retried.')
    
    def to_json(self) -> str:
        return self.model_dump_json()