from fastapi import APIRouter, Depends
from app.core.auth_dependencies import get_current_user, require_admin
from typing import Dict, Any

router = APIRouter(
    prefix="/transactions", 
    tags=["Transactions"],
    dependencies=[Depends(get_current_user)]
)

@router.get("/health")
async def transactions_health():
    """
    Placeholder endpoint to verify the transactions router is reachable
    and authentication integration can be tested.
    """
    return {
        "status": "ok", 
        "message": "Transactions router is active"
    }

@router.get("/me")
async def get_my_transactions_placeholder(
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Protected endpoint to verify the auth dependency correctly injects the current user context.
    """
    return {
        "message": "Authenticated access granted",
        "current_user": current_user
    }

@router.get("/admin-only")
async def admin_only_placeholder(
    current_user: Dict[str, Any] = Depends(require_admin)
):
    """
    Protected endpoint to verify the admin role dependency correctly restricts access.
    """
    return {
        "message": "Admin access granted",
        "current_user": current_user
    }