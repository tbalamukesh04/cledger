from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.api.dependencies import get_db
from app.models.transactions import Transactions, TransactionStatus

router = APIRouter()

@router.get("/transactions/review")
def get_transactions_for_review(db: Session = Depends(get_db)):
    transactions = db.query(Transactions).filter(
        Transactions.status == TransactionStatus.REVIEW_NEEDED
    ).order_by(Transactions.id.desc()).all()

    return {"data": transactions}
