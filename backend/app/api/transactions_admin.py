from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core.auth_dependencies import require_admin
from app.middleware.ip_filter import IPFilter
from app.schemas.transactions import TransactionCorrectionRequest, TransactionInvalidationRequest
from app.services.transaction_correction_service import correct_transaction_service, invalidate_transaction_service
from app.utils.logger import log_event, log_error
from app.core.log_events import LogEvent

router = APIRouter(
    tags=["Transactions Admin"], 
    dependencies=[
        Depends(require_admin),
        Depends(IPFilter(allowed_ips_env_key="ADMIN_ALLOWED_IPS"))
    ]
)

@router.post("/transactions/{transaction_id}/correct")
def correct_transaction_endpoint(
    transaction_id: int,
    request: TransactionCorrectionRequest,
    db: Session = Depends(get_db),
):
    try:
        correction_data = request.model_dump(exclude_unset=True)

        updated_txn = correct_transaction_service(
            db=db,
            transaction_id=transaction_id,
            correction_data=correction_data,
            actor_identifier="admin_user"
        )

        if not updated_txn:
            raise HTTPException(status_code=404, detail="Transaction not found")

        db.commit()
        db.refresh(updated_txn)
        
        log_event(LogEvent.REVIEW_FLAGGED, "Transaction successfully corrected by admin", transaction_id=str(transaction_id), status="corrected")
        return {"message": "Transaction corrected successfully", "data": updated_txn.to_dict()}

    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        log_error(LogEvent.SYSTEM_ERROR, error=e, message="Error correcting transaction", transaction_id=str(transaction_id))
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/transactions/{transaction_id}/invalidate")
def invalidate_transaction_endpoint(
    transaction_id: int,
    request: TransactionInvalidationRequest,
    db: Session = Depends(get_db),
):
    try:
        updated_txn = invalidate_transaction_service(
            db=db,
            transaction_id=transaction_id,
            reason=request.reason,
            actor_identifier="admin_user"
        )

        if not updated_txn:
            raise HTTPException(status_code=404, detail="Transaction not found")

        db.commit()
        db.refresh(updated_txn)
        
        log_event(LogEvent.REVIEW_FLAGGED, "Transaction successfully invalidated by admin", transaction_id=str(transaction_id), status="invalidated")
        return {"message": "Transaction invalidated successfully", "data": updated_txn.to_dict()}

    except Exception as e:
        db.rollback()
        log_error(LogEvent.SYSTEM_ERROR, error=e, message="Error invalidating transaction", transaction_id=str(transaction_id))