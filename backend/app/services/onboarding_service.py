import re
import secrets
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.models.businesses import Businesses
from app.models.users import Users
from app.schemas.auth import Auth0TokenPayload

def onboard_tenant_and_user(db: Session, payload: Auth0TokenPayload) -> tuple[Businesses, Users]:
    """
    Idempotently and transactionally provisions a multi-tenant business boundary
    and linked administrator user identity profile from validated Auth0 OIDC claims.
    """
    # Look up matching business enterprise context using Auth0 Organization ID mapping
    business = db.query(Businesses).filter(Businesses.auth0_org_id == payload.org_id).first()
    
    # Pre-calculate a deterministic fallback email identifier if missing from the Access Token claims
    safe_email = payload.email or f"{payload.sub.replace('|', '_')}@placeholder.cledger.com"

    if not business:
        # Resolve company seed nomenclature using provisioning priority matrix
        if getattr(payload, 'org_name', None):
            business_name = payload.org_name
        else:
            # Fallback source calculation derived strictly from the verified email domain
            email_domain = safe_email.split("@")[-1]
            business_name = email_domain.split(".")[0].capitalize()
            
        # Clean slug synthesis compilation logic
        base_slug = business_name.lower().strip()
        base_slug = re.sub(r"[^a-z0-9\s-]", "", base_slug)
        base_slug = re.sub(r"[\s-]+", "-", base_slug)
        base_slug = base_slug.strip("-")
        
        if not base_slug:
            base_slug = "workspace"
            
        slug = base_slug
        
        # Safe evaluation loop to guarantee collision avoidance against duplicate slugs
        while True:
            existing_slug = db.query(Businesses).filter(Businesses.slug == slug).first()
            if not existing_slug:
                break
            short_suffix = secrets.token_hex(2)  # Generates a unique 4-character suffix
            slug = f"{base_slug}-{short_suffix}"
            
        # Instantiate operational business record with explicit onboarding parameters
        business = Businesses(
            name=business_name,
            slug=slug,
            auth0_org_id=payload.org_id,
            is_active=True,
            onboarding_completed=False,
            created_via="auth0_auto_onboard"
        )
        db.add(business)
        db.flush()  # Populates primary key relational identifiers immediately for relational tracking
        
    # Look up user identity boundary within the scope of the resolved business organization
    user = db.query(Users).filter(
        Users.auth0_user_id == payload.sub,
        Users.business_id == business.id
    ).first()
    
    if not user:
        # Fallback username assignment strategy if token display name is missing
        fallback_display_name = payload.name if getattr(payload, 'name', None) else safe_email.split("@")[0]
        
        user = Users(
            business_id=business.id,
            auth0_user_id=payload.sub,
            email=safe_email,
            display_name=fallback_display_name,
            is_active=True
        )
        db.add(user)
        
    try:
        db.commit()
        db.refresh(business)
        db.refresh(user)
    except Exception as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"SaaS multi-tenant infrastructure auto-provisioning transaction block failed: {str(error)}"
        )
        
    return business, user