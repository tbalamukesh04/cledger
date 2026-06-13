# backend/app/services/tenant_resolution_service.py
import logging
from sqlalchemy.orm import Session
from app.models.businesses import Businesses

def resolve_tenant_from_webhook(db: Session, phone_number_id: str = None, waba_id: str = None) -> int:
    """
    Resolves the canonical tenant_id from incoming Meta webhook identifiers.
    Follows strict priority:
    1. metadata.phone_number_id -> businesses.meta_phone_number_id
    2. entry.id (WABA ID) -> businesses.meta_waba_id
    """
    
    # 1. Primary Resolution: Strict phone number mapping
    if phone_number_id:
        business = db.query(Businesses).filter(Businesses.meta_phone_number_id == phone_number_id).first()
        if business:
            return business.id
            
    # 2. Fallback Resolution: WABA ID mapping
    if waba_id:
        business = db.query(Businesses).filter(Businesses.meta_waba_id == waba_id).first()
        if business:
            return business.id
            
    # 3. No match found (Quarantine trigger)
    return None# backend/app/services/tenant_resolution_service.py
import logging
from sqlalchemy.orm import Session
from app.models.businesses import Businesses

def resolve_tenant_from_webhook(db: Session, phone_number_id: str = None, waba_id: str = None) -> int:
    """
    Resolves the canonical tenant_id from incoming Meta webhook identifiers.
    Follows strict priority:
    1. metadata.phone_number_id -> businesses.meta_phone_number_id
    2. entry.id (WABA ID) -> businesses.meta_waba_id
    """
    
    # 1. Primary Resolution: Strict phone number mapping
    if phone_number_id:
        business = db.query(Businesses).filter(Businesses.meta_phone_number_id == phone_number_id).first()
        if business:
            return business.id
            
    # 2. Fallback Resolution: WABA ID mapping
    if waba_id:
        business = db.query(Businesses).filter(Businesses.meta_waba_id == waba_id).first()
        if business:
            return business.id
            
    # 3. No match found (Quarantine trigger)
    return None