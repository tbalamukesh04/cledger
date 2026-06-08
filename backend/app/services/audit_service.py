import logging
from sqlalchemy.orm import Session

from app.crud.audit_crud import create_audit_entry
from app.models.transaction_audit import TransactionAuditAction
from app.models.transactions import Transactions
from app.utils.transaction_snapshot import serialize_transaction_snapshot

logger = logging.getLogger(__name__)

def create_transaction_audit(
    db: Session, 
    transaction: Transactions,
    action: TransactionAuditAction,
    performed_by: str,
    old_snapshot: dict | None = None
) -> None:
    try:
        new_snapshot = serialize_transaction_snapshot(transaction)
        create_audit_entry(
            db=db,
            transaction_id=transaction.id,
            action=action,
            actor_identifier=performed_by,
            new_value=new_snapshot,
            old_value=old_snapshot
        )
    except Exception as e:
        logger.error({
            "event_type": "transaction_audit_write_failed",
            "transaction_id": transaction.id,
            "action": action.value,
            "performed_by": performed_by,
            "error": str(e)
        })
        raise RuntimeError(
            f"Audit entry creation failed for transaction {transaction.id} "
            f"action '{action.value}': {e}"
        ) from e