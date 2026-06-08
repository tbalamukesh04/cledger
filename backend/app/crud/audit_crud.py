import logging 
from typing import Optional

from sqlalchemy.orm import Session

from app.models.transaction_audit import TransactionAudit, TransactionAuditAction

logger = logging.getLogger(__name__)

def create_audit_entry(
    db: Session,
    transaction_id: int,
    action: TransactionAuditAction,
    actor_identifier: str,
    new_value: dict,
    old_value: Optional[dict] = None
) -> TransactionAudit:
    """
    Create a new transaction audit entry.
    """
    audit_entry = TransactionAudit(
        transaction_id=transaction_id,
        action=action,
        new_value=new_value,
        old_value=old_value,
        actor_identifier=actor_identifier
    )
    db.add(audit_entry)
    db.flush()

    logger.info({
        "event_type": "transaction_audit_entry_created",
        "transaction_id": transaction_id,
        "action": action.value,
        "actor_identifier": actor_identifier,
        })

    return audit_entry
