import logging
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from app.models.transactions import Transactions, TransactionStatus
from app.models.transaction_audit import TransactionAuditAction
from app.crud.transaction_crud import update_transaction

logger = logging.getLogger(__name__)

ALLOWED_CORRECTION_FIELDS = {"amount", "currency", "remarks", "txn_date", "txn_type"}

def correct_transaction_service(db:Session, transaction_id: int, tenant_id: int, correction_data:Dict[str, Any], actor_identifier: str) -> Optional[Transactions]:
    db_txn = db.query(Transactions).filter(Transactions.id == transaction_id, Transactions.tenant_id == tenant_id).first()
    if not db_txn:
        logger.warning(f"Correction failed: Transaction {transaction_id} not found or tenant mismatch for tenant {tenant_id}.")
        return None

    filtered_data = {
        k: v for k, v in correction_data.items()
        if k in ALLOWED_CORRECTION_FIELDS and v is not None
    }

    if not filtered_data:
        raise ValueError("No permitted fields provided for correction.")

    filtered_data["status"] = TransactionStatus.CORRECTED

    updated_txn = update_transaction(
        db=db,
        transaction_id=transaction_id, 
        tenant_id=tenant_id,
        update_data=filtered_data, 
        commit=False, 
        actor_identifier=actor_identifier, 
        action=TransactionAuditAction.CORRECTED
        )
    
    logger.info({
        "event_type": "transaction_corrected",
        "transaction_id": transaction_id,
        "actor": actor_identifier,
        "fields_updated": list(filtered_data.keys())
    })
    
    return updated_txn

def invalidate_transaction_service(
    db:Session, 
    transaction_id: int,
    tenant_id: int,
    reason: Optional[str],
    actor_identifier: str
) -> Optional[Transactions]:
    db_txn = db.query(Transactions).filter(Transactions.id == transaction_id, Transactions.tenant_id == tenant_id).first()
    if not db_txn:
        logger.warning(f"Invalidation failed: Transaction {transaction_id} not found or tenant mismatch for tenant {tenant_id}.")
        return None
    
    update_data = {
        "status": TransactionStatus.INVALIDATED,
    }

    if reason:
        existing_remarks = db_txn.remarks or ""
        separator = " | " if existing_remarks else ""
        update_data["remarks"] = f"{existing_remarks}{separator}Invalidated: {reason}"

    updated_txn = update_transaction(
        db=db,
        transaction_id=transaction_id,
        tenant_id=tenant_id,
        update_data=update_data,
        commit=False,
        actor_identifier=actor_identifier,
        action=TransactionAuditAction.INVALIDATED
    )
    logger.info({
        "event_type": "transaction_invalidated",
        "transaction_id": transaction_id,
        "actor": actor_identifier,
        "reason": reason
    })

    return updated_txn