from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from app.models.transactions import Transactions, TransactionStatus

def get_transaction_by_message(db: Session, raw_message_id: int) -> Optional[Transactions]:
    """
    Fetch a transaction by its associated raw message ID.
    """
    return db.query(Transactions).filter(Transactions.raw_message_id == raw_message_id).first()

def get_transaction_by_hash(db: Session, txn_hash: str) -> Optional[Transactions]:
    """
    Fetch a transaction by its unique idempotency hash.
    """
    return db.query(Transactions).filter(Transactions.hash == txn_hash).first()

def create_transaction(db: Session, txn_data: Dict[str, Any], commit: bool = False) -> Transactions:
    """
    Create a new transaction record.
    Enforces application-level uniqueness before insert and handles status assignment.
    """
    # 1. Enforce application-level uniqueness on raw_message_id
    raw_message_id = txn_data.get("raw_message_id")
    if raw_message_id:
        existing_txn = get_transaction_by_message(db, raw_message_id)
        if existing_txn:
            raise ValueError(f"Transaction for raw_message_id {raw_message_id} already exists.")
            
    # 2. Enforce application-level uniqueness on hash
    txn_hash = txn_data.get("hash")
    if txn_hash:
        existing_hash = get_transaction_by_hash(db, txn_hash)
        if existing_hash:
            raise ValueError(f"Transaction with hash {txn_hash} already exists.")

    # 3. Handle Status Assignment
    if "status" not in txn_data or not txn_data["status"]:
        txn_data["status"] = TransactionStatus.REVIEW_NEEDED
    elif isinstance(txn_data["status"], str):
        # Safely cast string to Enum if passed
        txn_data["status"] = TransactionStatus(txn_data["status"])

    # 4. Insert Logic
    db_txn = Transactions(**txn_data)
    db.add(db_txn)
    
    # We default commit=False so batch processors (like job_handler) can manage their own commits
    if commit:
        db.commit()
        db.refresh(db_txn)
    else:
        db.flush()
        
    return db_txn

def update_transaction(db: Session, transaction_id: int, update_data: Dict[str, Any], commit: bool = False) -> Optional[Transactions]:
    """
    Update an existing transaction record (e.g., status correction workflows).
    """
    db_txn = db.query(Transactions).filter(Transactions.id == transaction_id).first()
    if not db_txn:
        return None

    # Handle status enum conversion if updating the status
    if "status" in update_data and isinstance(update_data["status"], str):
        update_data["status"] = TransactionStatus(update_data["status"])

    # Apply updates dynamically
    for key, value in update_data.items():
        if hasattr(db_txn, key):
            setattr(db_txn, key, value)

    if commit:
        db.commit()
        db.refresh(db_txn)
    else:
        db.flush()

    return db_txn