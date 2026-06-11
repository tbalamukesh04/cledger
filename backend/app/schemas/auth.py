# app/schemas/auth.py
from datetime import datetime
from typing import Optional
from typing import Optional
from pydantic import BaseModel, Field, EmailStr

class Auth0TokenPayload(BaseModel):
    sub: str
    org_id: str
    email: Optional[EmailStr] = None
    org_name: Optional[str] = Field(None, description="System name of the authenticated organization used for initial database seeding.")
    name: Optional[str] = Field(None, description="Human readable full name or display designation of the authenticating actor.")
    role: str = Field("user", description="System level RBAC role designation mapping.")

class OnboardingRequest(BaseModel):
    """
    Data contract for explicit workspace auto-onboarding requests.
    Identity and tenant properties are cryptographically extracted via the Auth0 JWT.
    """
    additional_metadata: Optional[dict] = Field(default_factory=dict, description="Optional system parameters or client configurations for custom setup extensions.")

class UserTenantMetadata(BaseModel):
    """
    Serialized application representation of an active tenant user identity profile.
    """
    id: int
    business_id: int
    auth0_user_id: str
    email: str
    display_name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class BusinessTenantMetadata(BaseModel):
    """
    Serialized application representation of an active corporate multi-tenant business perimeter.
    """
    id: int
    name: str
    slug: str
    auth0_org_id: str
    is_active: bool
    onboarding_completed: bool
    created_via: str
    onboarded_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class OnboardingResponse(BaseModel):
    """
    Standard successful initialization payload returned upon a safe just-in-time multi-tenant registration block.
    """
    status: str = Field("success", description="Status code indicating registration completed safely.")
    message: str = Field(..., description="Human readable context message outlining account state.")
    business: BusinessTenantMetadata = Field(..., description="The fully provisioned corporate multi-tenant business row metadata.")
    user: UserTenantMetadata = Field(..., description="The fully provisioned application user row metadata mapped to the target enterprise domain.")