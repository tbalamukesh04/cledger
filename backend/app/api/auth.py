# app/api/auth.py
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core.jwt_utils import verify_jwt_token
from app.schemas.auth import OnboardingRequest, OnboardingResponse, Auth0TokenPayload
from app.services.onboarding_service import onboard_tenant_and_user

router = APIRouter(prefix="/auth", tags=["Authentication & Onboarding"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login")

@router.post("/onboard", response_model=OnboardingResponse, status_code=status.HTTP_200_OK)
def onboard_user_workspace(
    request_data: OnboardingRequest,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """
    Explicit multi-tenant SaaS just-in-time onboarding ingress node.
    Cryptographically decodes verified Auth0 RS256 organization claims, maps boundaries, 
    and provisions workspace clusters transactionally without runtime silent side-effects.
    """
    # Cryptographically decode token signatures and verify audience/issuer metrics
    payload_dict = verify_jwt_token(token)
    
    # Enforce precise presence of required multi-tenant tracking tokens
    if "sub" not in payload_dict or "org_id" not in payload_dict:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provided security bearer token is structurally invalid: missing native OIDC tracking claims ('sub', 'org_id')."
        )
        
    try:
        token_payload = Auth0TokenPayload(
            sub=payload_dict["sub"],
            org_id=payload_dict["org_id"],
            org_name=payload_dict.get("org_name"),
            email=payload_dict.get("email"),
            name=payload_dict.get("name"),
            role=payload_dict.get("role", "user")
        )
    except Exception as validation_err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Inbound identity payload claims failed structure data validation guidelines: {str(validation_err)}"
        )
        
    # Safely coordinate isolated atomic database provisioning block metrics
    business, user = onboard_tenant_and_user(db, token_payload)
    
    message = "Enterprise tenant workspace resolved successfully." if business.onboarding_completed else "Enterprise tenant workspace and identity structures provisioned successfully."
    
    return OnboardingResponse(
        status="success",
        message=message,
        business=business,
        user=user
    )