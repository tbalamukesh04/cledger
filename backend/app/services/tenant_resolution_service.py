import logging
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session

from app.models.businesses import Businesses
from app.utils.logger import log_event
from app.core.log_events import LogEvent

class TenantResolutionService:
    """
    Dedicated service layer for resolving multi-tenant isolation context from incoming Meta webhooks.
    Handles identifier extraction, database mapping, and quarantine logging.
    """
    
    def __init__(self, db: Session):
        self.db = db

    def resolve_tenant(self, value: Dict[str, Any], waba_id: Optional[str] = None) -> Optional[int]:
        """
        Extracts identifiers and resolves the canonical tenant_id.
        Follows strict priority:
        1. metadata.phone_number_id -> businesses.meta_phone_number_id
        2. entry.id (WABA ID) -> businesses.meta_waba_id
        """
        phone_number_id = value.get("metadata", {}).get("phone_number_id")
        
        # 1. Primary Resolution: Strict phone number mapping
        if phone_number_id:
            business = self.db.query(Businesses).filter(Businesses.meta_phone_number_id == phone_number_id).first()
            if business:
                return business.id
                
        # 2. Fallback Resolution: WABA ID mapping
        if waba_id:
            business = self.db.query(Businesses).filter(Businesses.meta_waba_id == waba_id).first()
            if business:
                return business.id
                
        # 3. No match found (Quarantine execution)
        log_event(
            LogEvent.SYSTEM_ERROR, 
            "Unmatched Webhook Quarantined", 
            level=logging.WARNING, 
            reason="tenant_resolution_failed", 
            waba_id=waba_id, 
            phone_number_id=phone_number_id,
            status="quarantined"
        )
        return None