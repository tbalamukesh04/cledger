from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.api.dependencies import get_db
from app.models.transactions import Transactions

router = APIRouter()

@router.get("/transactions/review")
def get_transactions_for_review(db: Session = Depends(get_db)):
    transactions = db.query(Transactions).filter(
        Transactions.status == "review_required"
    ).order_by(Transactions.id.desc()).all()

    return {"data": transactions}
