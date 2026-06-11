from typing import Dict, Any
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.core.jwt_utils import verify_jwt_token
from app.api.dependencies import get_db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login")

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    FastAPI dependency to extract and verify the JWT token from the Authorization header.
    Ensures side-effect-free cryptographic multi-tenant state and user record isolation alignment.
    """
    payload = verify_jwt_token(token)
    
    # Handle Auth0 Native Multi-Tenant Organization Claims
    if "sub" in payload and "org_id" in payload:
        auth0_user_id = payload["sub"]
        auth0_org_id = payload["org_id"]
        
        from app.models.businesses import Businesses
        from app.models.users import Users
        
        business = db.query(Businesses).filter(Businesses.auth0_org_id == auth0_org_id).first()
        if not business:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Organization tenant workspace not provisioned. Onboarding required.",
                headers={"WWW-Authenticate": "Bearer", "X-Onboarding-Required": "true"},
            )
            
        if not business.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Business tenant organization is suspended."
            )
            
        user = db.query(Users).filter(Users.auth0_user_id == auth0_user_id, Users.business_id == business.id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User identity profile not provisioned. Onboarding required.",
                headers={"WWW-Authenticate": "Bearer", "X-Onboarding-Required": "true"},
            )
            
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User application identity profile has been deactivated."
            )
            
        return {
            "user_id": user.id,
            "tenant_id": business.id,
            "auth0_user_id": user.auth0_user_id,
            "auth0_org_id": business.auth0_org_id,
            "role": payload.get("role", "user")
        }
        
    # Legacy Fallback Strategy for local integration/E2E test tracking scripts
    user_id = payload.get("user_id")
    tenant_id = payload.get("tenant_id")
    
    if user_id is None or tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token payload missing required identity vector coordinates",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return {
        "user_id": user_id,
        "tenant_id": tenant_id,
        "role": payload.get("role", "user")
    }

def require_admin(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """
    FastAPI dependency to ensure the authenticated user has an admin role.
    """
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions to access this resource"
        )
    return current_user