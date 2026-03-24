from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload
from app.core.auth_dependencies import get_current_user, require_admin
from app.api.dependencies import get_db
from app.schemas.transactions import TransactionQueryParams, SingleTransactionResponse, TransactionReviewRequest, ReviewAction
from app.crud.transaction_crud import get_transactions, get_transaction_by_id, get_transaction_audit_history, stream_transactions
from app.models.transactions import Transactions, TransactionStatus
from app.models.raw_messages import RawMessages
from app.services.transaction_correction_service import correct_transaction_service, invalidate_transaction_service
from app.services.transaction_csv_export import generate_transaction_csv_rows
from typing import Dict, Any

# Securing the entire router. All endpoints in this file will now require a valid JWT.
router = APIRouter(
    prefix="/transactions", 
    tags=["Transactions"],
    dependencies=[Depends(get_current_user)]
)

EXPORT_CSV_HEADERS = [
    "transaction_id",
    "amount",
    "currency",
    "remarks",
    "status",
    "transaction_date",
    "created_at",
    "participant_id",
    "participant_name",
    "participant_phone",
    "message_id",
    "message_text",
    "message_timestamp"
]

@router.get("/")
async def list_transactions(
    filters: TransactionQueryParams = Depends(),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Retrieve a list of transactions with filtering, pagination, and sorting.
    """
    tenant_id = current_user.get("tenant_id")
    
    # Build the base query with filters, sorting, and pagination
    query = get_transactions(db, tenant_id=tenant_id, filters=filters)
    
    if filters.limit:
        query = query.limit(filters.limit)
    
    if filters.offset:
        query = query.offset(filters.offset)

    transactions = query.all()

    serialized_transactions = []

    for txn in transactions:
        participant_data = None
        message_data = None

        if txn.raw_message:
            message_data = {
                "id": txn.raw_message.message_id,
                "text": txn.raw_message.raw_text,
                "timestamp": txn.raw_message.received_at
            }

            if txn.raw_message.sender:
                participant_data = {
                    "id": txn.raw_message.sender.id,
                    "phone": txn.raw_message.sender.phone,
                    "name": txn.raw_message.sender.displayname
                }

        serialized_transactions.append({
            "id": txn.id,
            "amount": txn.amount,
            "currency": txn.currency,
            "remarks": txn.remarks,
            "status": txn.status,
            "transaction_date": txn.txn_date,
            "created_at": txn.created_at,
            "participant": participant_data,
            "message": message_data
        })

    return {
        "limit": filters.limit, 
        "offset": filters.offset, 
        "transactions": serialized_transactions
    }

@router.get("/export")
async def export_transactions_csv(
    filters: TransactionQueryParams = Depends(),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    from app.core.config import api_security_settings

    tenant_id = current_user.get("tenant_id")
    query = get_transactions(db, tenant_id=tenant_id, filters=filters)

    total_count = query.count()
    if total_count > api_security_settings.MAX_EXPORT_ROWS:
        raise HTTPException(
            status_code = 413, 
            detail = f"Export payload too large. Maximum {api_security_settings.MAX_EXPORT_ROWS} rows allowed."
        )

    transaction_stream = stream_transactions(
        db = db,
        tenant_id = tenant_id,
        filters = filters,
        batch_size=1000
    )

    csv_generator = generate_transaction_csv_rows(transaction_stream, EXPORT_CSV_HEADERS)

    return StreamingResponse(
        content = csv_generator,
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=transactions.csv"
        }
    )

@router.get("/{transaction_id}", response_model=SingleTransactionResponse)
async def get_single_transaction(
    transaction_id: int,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Retrieve detailed information for a single transaction by ID, including its audit history.
    """
    tenant_id = current_user.get("tenant_id")
    
    transaction = get_transaction_by_id(db, transaction_id=transaction_id, tenant_id=tenant_id)
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
        
    audit_history = get_transaction_audit_history(db, transaction_id=transaction_id)
    
    return {
        "transaction": transaction,
        "audit_history": audit_history
    }

@router.post("/{transaction_id}/review", response_model=SingleTransactionResponse)
async def review_transaction(
    transaction_id: int,
    review_request: TransactionReviewRequest,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Review a transaction (admin only). Allows correcting or invalidating a transaction.
    """
    tenant_id = current_user.get("tenant_id")
    
    transaction = get_transaction_by_id(db, transaction_id=transaction_id, tenant_id=tenant_id)
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
        
    if transaction.status != TransactionStatus.REVIEW_NEEDED:
        raise HTTPException(
            status_code=400,
            detail="Transaction is not in REVIEW_NEEDED state"
        )
    
    if review_request.action == ReviewAction.CORRECT:
        if not review_request.corrected_fields:
            raise HTTPException(status_code=400, detail="corrected_fields is required when action is 'correct'")
        
    actor_identifier = current_user.get("sub", "admin_user")

    if review_request.action == ReviewAction.CORRECT:
        try:
            updated_transaction = correct_transaction_service(
                db = db,
                transaction_id= transaction_id,
                correction_data = review_request.corrected_fields,
                actor_identifier = actor_identifier
            )
            if not updated_transaction:
                raise HTTPException(status = 500, detail = "Failed to correct transaction")
            db.commit()
            db.refresh(updated_transaction)
            transaction = updated_transaction
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    elif review_request.action == ReviewAction.INVALIDATE:
        try:
            updated_transaction = invalidate_transaction_service(
                db = db,
                transaction_id= transaction_id,
                actor_identifier = actor_identifier
            )
            if not updated_transaction:
                raise HTTPException(status = 500, detail = "Failed to invalidate transaction")
            db.commit()
            db.refresh(updated_transaction)
            transaction = updated_transaction

        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        
    audit_history = get_transaction_audit_history(db, transaction_id=transaction_id)
    
    return {
        "transaction": transaction,
        "audit_history": audit_history
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