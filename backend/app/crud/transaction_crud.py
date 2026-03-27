from typing import Optional, Dict, Any
from sqlalchemy.orm import Session, joinedload, contains_eager
from app.models.transactions import Transactions, TransactionStatus
from app.models.transaction_audit import TransactionAudit, TransactionAuditAction
from app.models.raw_messages import RawMessages
from app.models.participants import Participants
from app.schemas.transactions import TransactionQueryParams
from app.services.audit_service import create_transaction_audit
from app.utils.transaction_snapshot import serialize_transaction_snapshot
from sqlalchemy import or_,asc, desc

def get_transactions(db: Session, tenant_id: int, filters: TransactionQueryParams):
    """
    Builds and returns a SQLAlchemy query for transactions based on provided filters.
    """
    query = db.query(Transactions).join(
        RawMessages, Transactions.raw_message_id == RawMessages.id, isouter=True
    ).join(
        Participants, RawMessages.sender_id == Participants.id, isouter=True
    ).options(
        contains_eager(Transactions.raw_message).contains_eager(RawMessages.sender)
    ).filter(Transactions.tenant_id == tenant_id)
    
    if filters.status:
        query = query.filter(Transactions.status == filters.status)

    if filters.date_from:
        query = query.filter(Transactions.txn_date >= filters.date_from)

    if filters.date_to:
        query = query.filter(Transactions.txn_date <= filters.date_to)

    if filters.amount_min:
        query = query.filter(Transactions.amount >= filters.amount_min)

    if filters.amount_max:
        query = query.filter(Transactions.amount <= filters.amount_max)

    if filters.currency:
        query = query.filter(Transactions.currency == filters.currency)

    if filters.participant:
        query = query.filter(or_(Participants.displayname.ilike(f"%{filters.participant}%"),
                                 Participants.phone.ilike(f"%{filters.participant}%")))
    
    sort_mapping = {
        "transaction_date": Transactions.txn_date,
        "amount": Transactions.amount,
        "created_at": Transactions.created_at,
    }

    sort_column = sort_mapping.get(filters.sort_by, Transactions.created_at)

    if filters.sort_order == "asc":
        query = query.order_by(asc(sort_column))
    else:
        query = query.order_by(desc(sort_column))

    query = query.offset(filters.offset).limit(filters.limit)

    return query

def stream_transactions(db: Session, tenant_id: int, filters: TransactionQueryParams, batch_size: int = 1000):
    query = get_transactions(db, tenant_id=tenant_id, filters=filters)
    query = query.limit(None).offset(None)

    query = query.options(
        joinedload(Transactions.raw_message).joinedload(RawMessages.sender)
    )

    for transaction in query.yield_per(batch_size):
        yield transaction

def get_transaction_by_id(db: Session, transaction_id: int, tenant_id: int) -> Optional[Transactions]:
    """
    Fetch a transaction by its ID and tenant_id, eagerly loading related entities.
    """
    return db.query(Transactions).join(
        RawMessages, Transactions.raw_message_id == RawMessages.id, isouter = True
    ).join(
        Participants, RawMessages.sender_id == Participants.id, isouter = True
    ).options(
        contains_eager(Transactions.raw_message).contains_eager(RawMessages.sender)
    ).filter(
        Transactions.id == transaction_id,
        Transactions.tenant_id == tenant_id
    ).first()

def get_transaction_audit_history(db: Session, transaction_id: int):
    """
    Fetch audit history for a specific transaction ordered by created_at ascending.
    """
    return db.query(TransactionAudit).filter(
        TransactionAudit.transaction_id == transaction_id
    ).order_by(asc(TransactionAudit.created_at)).all()

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

def create_transaction(db: Session, txn_data: Dict[str, Any], commit: bool = False, actor_identifier: str = "system") -> Transactions:
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
    db.flush()
    
    create_transaction_audit(
        db = db,
        transaction = db_txn,
        action = TransactionAuditAction.CREATED,
        performed_by = actor_identifier,
        old_snapshot = None
    )

    # We default commit=False so batch processors (like job_handler) can manage their own commits
    if commit:
        db.commit()
        db.refresh(db_txn)
    else:
        db.flush()
        
    return db_txn

def update_transaction(db: Session, transaction_id: int, update_data: Dict[str, Any], commit: bool = False, actor_identifier: str = "system", action: TransactionAuditAction = TransactionAuditAction.UPDATED) -> Optional[Transactions]:
    """
    Update an existing transaction record (e.g., status correction workflows).
    """
    db_txn = db.query(Transactions).filter(Transactions.id == transaction_id).first()
    if not db_txn:
        return None

    old_snapshot = serialize_transaction_snapshot(db_txn)

    # Handle status enum conversion if updating the status
    if "status" in update_data and isinstance(update_data["status"], str):
        update_data["status"] = TransactionStatus(update_data["status"])

    # Apply updates dynamically
    for key, value in update_data.items():
        if hasattr(db_txn, key):
            setattr(db_txn, key, value)

    db.flush()
    
    create_transaction_audit(
        db = db,
        transaction = db_txn,
        action = action,
        performed_by = actor_identifier,
        old_snapshot = old_snapshot
    )
    
    if commit:
        db.commit()
        db.refresh(db_txn)
    
    return db_txn

def upsert_transaction(db: Session, txn_data: Dict[str, Any], commit: bool = False, actor_identifier: str = "system") -> Optional[Transactions]:
    """
    Create a new transaction or update an existing one based on raw_message_id.
    Human Override Protection: If an existing transaction has a status of CORRECTED 
    or INVALIDATED, it skips the update completely.
    """
    raw_message_id = txn_data.get("raw_message_id")
    if not raw_message_id:
        raise ValueError("raw_message_id is required for upsert operation.")

    # 1. Check if transaction already exists
    existing_txn = get_transaction_by_message(db, raw_message_id)

    # 2. Human Override Protection
    if existing_txn:
        protected_statuses = [TransactionStatus.CORRECTED, TransactionStatus.INVALIDATED]
        if existing_txn.status in protected_statuses:
            return existing_txn
    
        if "hash" in txn_data:
            existing_hash_txn = get_transaction_by_hash(db, txn_data["hash"])
            if existing_hash_txn and existing_hash_txn.id != existing_txn.id:
                raise ValueError(f"Transaction with hash {txn_data['hash']} already exists.")
        
        forbidden_fields = {"raw_message_id", "id", "created_at"}
        update_payload = {}

        for key, value in txn_data.items():
            if key in forbidden_fields:
                continue
            
            if key == "description":
                update_payload["remarks"] = value
            else:
                update_payload[key] = value

        new_status = update_payload.get("status")
        if new_status == TransactionStatus.CORRECTED:
            action = TransactionAuditAction.CORRECTED
        elif new_status == TransactionStatus.INVALIDATED:
            action = TransactionAuditAction.INVALIDATED
        else:
            action = TransactionAuditAction.UPDATED

        return update_transaction(db, existing_txn.id, update_payload, commit=commit, actor_identifier=actor_identifier, action=action)
        
    else:
        if "description" in txn_data:
            txn_data["remarks"] = txn_data.pop("description")

        return create_transaction(db, txn_data, commit=commit)
  
