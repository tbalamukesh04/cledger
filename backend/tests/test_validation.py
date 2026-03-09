from datetime import datetime, timezone
from sqlalchemy.exc import IntegrityError
from app.database.database import SessionLocal

from app.models.participants import Participants
from app.models.groups import Groups
from app.models.raw_messages import RawMessages

def run_validation_tests():
    db = SessionLocal()
    print("Starting database validation tests...\n")

    try:
        # --- TEST 1: Insert Group & Participant ---
        print("Test 1: Inserting new Group and Participant...")
        test_group = Groups(group_id="whatsapp_group_999", groupname="Validation Squad")
        test_participant = Participants(phone="9998887776", displayname="Validator User")
        
        db.add(test_group)
        db.add(test_participant)
        db.commit()
        print("✅ Success: Group and Participant inserted.")

        # --- TEST 2: Insert Raw Message (Foreign Key Check) ---
        print("\nTest 2: Inserting RawMessage referencing the Group and Participant...")
        test_message = RawMessages(
            group_id=test_group.id,
            sender_id=test_participant.id,
            message_id="wamid.VALIDATION_MSG_001",
            received_at=datetime.now(timezone.utc),
            raw_json={"test": "payload"},
            raw_text="This is a validation test message.",
            hash="hash_validation_001"
        )
        db.add(test_message)
        db.commit()
        print("✅ Success: RawMessage inserted with referential integrity.")

        # --- TEST 3: Attempt Duplicate Message Insertion (Idempotency Check) ---
        print("\nTest 3: Attempting to insert a duplicate message (Should Fail)...")
        duplicate_message = RawMessages(
            group_id=test_group.id,
            sender_id=test_participant.id,
            message_id="wamid.VALIDATION_MSG_001", # Exact same WhatsApp ID
            received_at=datetime.now(timezone.utc),
            raw_json={"test": "payload_duplicate"},
            hash="hash_validation_002"
        )
        db.add(duplicate_message)
        db.commit() # This should trigger the database constraint violation
        
        # If we reach here, the constraint failed to block the duplicate
        print("❌ Failure: Duplicate message was inserted! Constraint is missing.")

    except IntegrityError as e:
        db.rollback()
        print("✅ Success: Database correctly rejected the duplicate message!")
        print(f"   -> Constraint Enforced: {e.orig}")

    except Exception as e:
        db.rollback()
        print(f"❌ Unexpected Error: {e}")
        
    finally:
        db.close()
        print("\nValidation tests complete.")

if __name__ == "__main__":
    run_validation_tests()