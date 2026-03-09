import uuid
from decimal import Decimal
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timezone

from app.models.base import Base
from app.database.database import SessionLocal
from app.models.transactions import Transactions
from app.models.audit_logs import AuditLog, EventType, ActorType
from app.models.raw_messages import RawMessages
from app.models.groups import Groups
from app.models.participants import Participants

def run_tests():
    db = SessionLocal()
    test_run_id = str(uuid.uuid4())[:8]
    mock_hash = f"test_hash_{test_run_id}"
    
    print(f"--- Starting Day 7 Validation (Test Run: {test_run_id}) ---")

    try:
        # ---------------------------------------------------------
        # SETUP: Create Parent Records to satisfy Foreign Keys
        # ---------------------------------------------------------
        # 1. Create a dummy Participant (using 'phone' and 'displayname')
        dummy_participant = Participants(
            tenant_id=1, 
            phone=f"+123456{test_run_id[:4]}",
            displayname="Test User"
        )
        db.add(dummy_participant)
        
        # 2. Create a dummy Group (using 'group_id' and 'groupname')
        dummy_group = Groups(
            tenant_id=1, 
            group_id=f"grp_{test_run_id}",
            groupname="Test Group"
        )
        db.add(dummy_group)
        db.commit() # Commit to generate IDs
        
        # 3. Create a dummy RawMessage (using 'received_at' and 'raw_json')
        dummy_message = RawMessages(
            tenant_id=1,
            sender_id=dummy_participant.id,
            group_id=dummy_group.id,
            message_id=f"msg_{test_run_id}",
            hash=f"raw_hash_{test_run_id}",
            received_at=datetime.now(timezone.utc),
            raw_json={"test": "data"}
        )
        db.add(dummy_message)
        db.commit()
        
        valid_raw_message_id = dummy_message.id
        print(f"✅ SETUP PASSED: Created mock RawMessage (ID: {valid_raw_message_id}) to satisfy FKs.")

        # ---------------------------------------------------------
        # TEST 1: Insert Valid Transaction
        # ---------------------------------------------------------
        test_amount = Decimal("1234.56")
        
        new_txn = Transactions(
            tenant_id=1,
            raw_message_id=valid_raw_message_id, # Using the valid ID!
            amount=test_amount,
            currency="ZMW",
            txn_type="credit",
            status="processed",
            hash=mock_hash,
            parsing_meta={"source": "test_script", "confidence": 0.99}
        )
        db.add(new_txn)
        db.commit()
        db.refresh(new_txn)
        print("✅ TEST 1 PASSED: Valid Transaction inserted successfully.")

        # ---------------------------------------------------------
        # TEST 2: Insert Audit Record
        # ---------------------------------------------------------
        audit_entry = AuditLog(
            entity_type="Transactions",
            entity_id=str(new_txn.id),
            event_type=EventType.CREATE,
            actor_type=ActorType.SYSTEM,
            actor_identifier="validation_script",
            new_state={"amount": str(new_txn.amount), "status": new_txn.status},
            reason="Initial transaction parsing"
        )
        db.add(audit_entry)
        db.commit()
        print("✅ TEST 2 PASSED: Audit Log entry inserted successfully.")

        # ---------------------------------------------------------
        # TEST 3: Verify Numeric Precision
        # ---------------------------------------------------------
        fetched_txn = db.query(Transactions).filter(Transactions.id == new_txn.id).first()
        assert fetched_txn.amount == Decimal("1234.56"), f"Precision error! Got {fetched_txn.amount}"
        print("✅ TEST 3 PASSED: Monetary precision strictly maintained (Decimal).")

        # ---------------------------------------------------------
        # TEST 4: Attempt Duplicate Transaction Insertion
        # ---------------------------------------------------------
        duplicate_txn = Transactions(
            tenant_id=1,
            raw_message_id=valid_raw_message_id, 
            amount=Decimal("500.00"),
            currency="ZMW",
            txn_type="debit",
            status="pending",
            hash=f"diff_hash_{test_run_id}", # Different hash...
        )
        db.add(duplicate_txn)
        
        try:
            db.commit()
            print("❌ TEST 4 FAILED: Duplicate transaction was allowed!")
        except IntegrityError as e:
            db.rollback()
            print("✅ TEST 4 PASSED: IntegrityError successfully caught on duplicate raw_message_id.")

    except Exception as e:
        db.rollback()
        print(f"❌ UNEXPECTED ERROR: {e}")
    finally:
        db.close()
        print("--- Validation Complete ---")

if __name__ == "__main__":
    run_tests()