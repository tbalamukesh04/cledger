from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.schemas.transactions import TransactionCorrectionRequest, TransactionInvalidationRequest
from app.services.transaction_correction_service import correct_transaction_service, invalidate_transaction_service

router = APIRouter(tags=["Transactions Admin"])

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

        return {"message": "Transaction corrected successfully", "data": updated_txn.to_dict()}

    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Error correcting transaction {transaction_id}: {e}")
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

        return {"message": "Transaction invalidated successfully", "data": updated_txn.to_dict()}

    except Exception as e:
        db.rollback()
        logger.error(f"Error invalidating transaction {transaction_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
