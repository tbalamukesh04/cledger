from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload
from app.core.auth_dependencies import get_current_user, require_admin
from app.api.dependencies import get_db
from app.schemas.transactions import TransactionQueryParams
from app.crud.transaction_crud import get_transactions
from app.models.transactions import Transactions
from app.models.raw_messages import RawMessages
from typing import Dict, Any

# Securing the entire router. All endpoints in this file will now require a valid JWT.
router = APIRouter(
    prefix="/transactions", 
    tags=["Transactions"],
    dependencies=[Depends(get_current_user)]
)

@router.get("/")
async def list_transactions(
    filters: TransactionQueryParams = Depends(),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Retrieve a list of transactions with filtering, pagination, and sorting.
    """
    # Assuming user_id maps to tenant_id in this context
    tenant_id = current_user.get("tenant_id")
    
    # Build the base query with filters, sorting, and pagination
    query = get_transactions(db, tenant_id=tenant_id, filters=filters)
    
    # Eagerly load related entities to prevent N+1 queries during serialization
    query = query.options(
        joinedload(Transactions.raw_message).joinedload(RawMessages.sender)
    )
    
    # To calculate total matching records before pagination, we temporarily strip limit/offset
    total_count = query.limit(None).offset(None).order_by(None).count()
    
    # Execute the paginated query
    transactions = query.all()
    
    # Serialize the response and enrich with joined table data
    serialized_transactions = []
    for txn in transactions:
        txn_dict = txn.to_dict()
        
        # Enrich with related entities if available
        if txn.raw_message:
            txn_dict["message"] = {
                "id": txn.raw_message.id,
                "whatsapp_message_id": txn.raw_message.message_id,
                "received_at": txn.raw_message.received_at.isoformat() if txn.raw_message.received_at else None,
                "raw_text": txn.raw_message.raw_text
            }
            if txn.raw_message.sender:
                txn_dict["participant"] = {
                    "id": txn.raw_message.sender.id,
                    "phone": txn.raw_message.sender.phone,
                    "displayname": txn.raw_message.sender.displayname
                }
                
        serialized_transactions.append(txn_dict)
        
    return {
        "total": total_count,
        "limit": filters.limit,
        "offset": filters.offset,
        "transactions": serialized_transactions
    }
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