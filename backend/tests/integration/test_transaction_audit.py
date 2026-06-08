
import uuid
from decimal import Decimal
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.exc import InternalError

from app.database.database import SessionLocal
from app.models.participants import Participants
from app.models.groups import Groups
from app.models.raw_messages import RawMessages
from app.models.transactions import Transactions, TransactionStatus
from app.models.transaction_audit import TransactionAudit, TransactionAuditAction
from app.crud.transaction_crud import create_transaction, update_transaction
from app.utils.transaction_snapshot import serialize_transaction_snapshot


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_prerequisites(db, test_run_id: str):
    """
    Creates and commits the minimum set of parent records required to satisfy
    foreign key constraints before inserting a transaction.
    Returns plain integer IDs to avoid lazy-load issues after session expiry.
    """
    participant = Participants(
        tenant_id=1,
        phone=f"+2609{test_run_id[:8]}",
        displayname="Audit Tester",
    )
    db.add(participant)

    group = Groups(
        tenant_id=1,
        group_id=f"grp_audit_{test_run_id}",
        groupname="Audit Test Group",
    )
    db.add(group)
    db.flush()

    raw_message = RawMessages(
        tenant_id=1,
        sender_id=participant.id,
        group_id=group.id,
        message_id=f"wamid.AUDIT_{test_run_id}",
        hash=f"hash_audit_{test_run_id}",
        received_at=datetime.now(timezone.utc),
        raw_json={"test": "audit"},
    )
    db.add(raw_message)
    db.commit()

    # Return plain ints — safe to access after session expiry or flush errors
    return int(participant.id), int(group.id), int(raw_message.id)


def _make_txn_data(raw_message_id: int) -> dict:
    return {
        "tenant_id": 1,
        "raw_message_id": raw_message_id,
        "amount": Decimal("500.00"),
        "currency": "ZMW",
        "txn_type": "debit",
        "txn_date": datetime.now(timezone.utc),
        "confidence": 0.95,
        "status": TransactionStatus.PARSED,
        "hash": uuid.uuid4().hex,
        "remarks": "Audit test transaction",
    }


def _cleanup(db, participant_id=None, group_id=None, raw_message_id=None, txn_id=None):
    """
    Explicitly deletes test rows in dependency order to leave the DB clean.
    """
    try:
        db.rollback()  # Clear any pending failed transaction first
        if txn_id:
            db.execute(text("DELETE FROM transaction_audit WHERE transaction_id = :id"), {"id": txn_id})
            db.execute(text("DELETE FROM transactions WHERE id = :id"), {"id": txn_id})
        if raw_message_id:
            db.execute(text("DELETE FROM raw_messages WHERE id = :id"), {"id": raw_message_id})
        if group_id:
            db.execute(text("DELETE FROM groups WHERE id = :id"), {"id": group_id})
        if participant_id:
            db.execute(text("DELETE FROM participants WHERE id = :id"), {"id": participant_id})
        db.commit()
    except Exception as e:
        db.rollback()


# ---------------------------------------------------------------------------
# Scenario 1 — Transaction Creation
# ---------------------------------------------------------------------------

def test_audit_entry_created_on_transaction_creation():
    db = SessionLocal()
    test_run_id = uuid.uuid4().hex
    participant_id, group_id, raw_message_id = _make_prerequisites(db, test_run_id)
    txn_id = None

    try:
        txn = create_transaction(
            db=db,
            txn_data=_make_txn_data(raw_message_id),
            commit=True,
            actor_identifier="worker-test",
        )
        txn_id = txn.id

        audit = (
            db.query(TransactionAudit)
            .filter(TransactionAudit.transaction_id == txn.id)
            .first()
        )

        assert audit is not None, "Audit entry was not created."
        assert audit.action == TransactionAuditAction.CREATED.value
        assert audit.old_value is None, "old_value must be null for creation."
        assert audit.new_value is not None, "new_value must contain the transaction snapshot."
        assert audit.new_value["id"] == txn.id
        assert audit.new_value["status"] == TransactionStatus.PARSED.value
        assert audit.actor_identifier == "worker-test"

    finally:
        _cleanup(db, participant_id, group_id, raw_message_id, txn_id)
        db.close()


# ---------------------------------------------------------------------------
# Scenario 2 — Transaction Update
# ---------------------------------------------------------------------------

def test_audit_entry_created_on_transaction_update():
    db = SessionLocal()
    test_run_id = uuid.uuid4().hex
    participant_id, group_id, raw_message_id = _make_prerequisites(db, test_run_id)
    txn_id = None

    try:
        txn = create_transaction(
            db=db,
            txn_data=_make_txn_data(raw_message_id),
            commit=True,
            actor_identifier="worker-test",
        )
        txn_id = txn.id

        snapshot_before_update = serialize_transaction_snapshot(txn)

        update_transaction(
            db=db,
            transaction_id=txn.id,
            update_data={"confidence": 0.75, "status": TransactionStatus.REVIEW_NEEDED},
            commit=True,
            actor_identifier="worker-test",
            action=TransactionAuditAction.UPDATED,
        )

        audits = (
            db.query(TransactionAudit)
            .filter(TransactionAudit.transaction_id == txn.id)
            .order_by(TransactionAudit.id)
            .all()
        )

        assert len(audits) == 2, f"Expected 2 audit entries, got {len(audits)}."

        update_audit = audits[1]
        assert update_audit.action == TransactionAuditAction.UPDATED.value
        assert update_audit.old_value is not None
        assert update_audit.new_value is not None
        assert update_audit.old_value["status"] == snapshot_before_update["status"]
        assert update_audit.new_value["status"] == TransactionStatus.REVIEW_NEEDED.value
        assert update_audit.actor_identifier == "worker-test"

    finally:
        _cleanup(db, participant_id, group_id, raw_message_id, txn_id)
        db.close()


# ---------------------------------------------------------------------------
# Scenario 3 — Manual Correction
# ---------------------------------------------------------------------------

def test_audit_entry_created_on_manual_correction():
    db = SessionLocal()
    test_run_id = uuid.uuid4().hex
    participant_id, group_id, raw_message_id = _make_prerequisites(db, test_run_id)
    txn_id = None

    try:
        txn = create_transaction(
            db=db,
            txn_data=_make_txn_data(raw_message_id),
            commit=True,
            actor_identifier="worker-test",
        )
        txn_id = txn.id

        update_transaction(
            db=db,
            transaction_id=txn.id,
            update_data={"status": TransactionStatus.CORRECTED, "remarks": "Manually corrected by admin"},
            commit=True,
            actor_identifier="admin-user",
            action=TransactionAuditAction.CORRECTED,
        )

        audits = (
            db.query(TransactionAudit)
            .filter(TransactionAudit.transaction_id == txn.id)
            .order_by(TransactionAudit.id)
            .all()
        )

        assert len(audits) == 2, f"Expected 2 audit entries, got {len(audits)}."

        correction_audit = audits[1]
        assert correction_audit.action == TransactionAuditAction.CORRECTED.value
        assert correction_audit.old_value["status"] == TransactionStatus.PARSED.value
        assert correction_audit.new_value["status"] == TransactionStatus.CORRECTED.value
        assert correction_audit.actor_identifier == "admin-user"

    finally:
        _cleanup(db, participant_id, group_id, raw_message_id, txn_id)
        db.close()


# ---------------------------------------------------------------------------
# Scenario 4 — Immutability Validation
# ---------------------------------------------------------------------------

def test_audit_record_is_immutable():
    db = SessionLocal()
    test_run_id = uuid.uuid4().hex
    participant_id, group_id, raw_message_id = _make_prerequisites(db, test_run_id)
    txn_id = None

    try:
        txn = create_transaction(
            db=db,
            txn_data=_make_txn_data(raw_message_id),
            commit=True,
            actor_identifier="worker-test",
        )
        txn_id = txn.id

        audit = (
            db.query(TransactionAudit)
            .filter(TransactionAudit.transaction_id == txn.id)
            .first()
        )
        assert audit is not None
        audit_id = int(audit.id)

        # --- Attempt UPDATE ---
        import pytest
        with pytest.raises(InternalError):
            db.execute(
                text("UPDATE transaction_audit SET actor_identifier = 'tampered' WHERE id = :id"),
                {"id": audit_id},
            )
            db.flush()
        db.rollback()

        # --- Attempt DELETE ---
        with pytest.raises(InternalError):
            db.execute(
                text("DELETE FROM transaction_audit WHERE id = :id"),
                {"id": audit_id},
            )
            db.flush()
        db.rollback()

    finally:
        _cleanup(db, participant_id, group_id, raw_message_id, txn_id)
        db.close()


# ---------------------------------------------------------------------------
# Scenario 5 — Invalidation
# ---------------------------------------------------------------------------

def test_audit_entry_created_on_invalidation():
    db = SessionLocal()
    test_run_id = uuid.uuid4().hex
    participant_id, group_id, raw_message_id = _make_prerequisites(db, test_run_id)
    txn_id = None

    try:
        txn = create_transaction(
            db=db,
            txn_data=_make_txn_data(raw_message_id),
            commit=True,
            actor_identifier="worker-test",
        )
        txn_id = txn.id

        update_transaction(
            db=db,
            transaction_id=txn.id,
            update_data={"status": TransactionStatus.INVALIDATED, "remarks": "Marked invalid by admin"},
            commit=True,
            actor_identifier="admin-user",
            action=TransactionAuditAction.INVALIDATED,
        )

        audits = (
            db.query(TransactionAudit)
            .filter(TransactionAudit.transaction_id == txn.id)
            .order_by(TransactionAudit.id)
            .all()
        )

        assert len(audits) == 2, f"Expected 2 audit entries, got {len(audits)}."

        invalidation_audit = audits[1]
        assert invalidation_audit.action == TransactionAuditAction.INVALIDATED.value
        assert invalidation_audit.old_value["status"] == TransactionStatus.PARSED.value
        assert invalidation_audit.new_value["status"] == TransactionStatus.INVALIDATED.value
        assert invalidation_audit.new_value["remarks"] == "Marked invalid by admin"
        assert invalidation_audit.actor_identifier == "admin-user"

    finally:
        _cleanup(db, participant_id, group_id, raw_message_id, txn_id)
        db.close()