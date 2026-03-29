import uuid
from decimal import Decimal
from datetime import datetime, timezone

from app.database.database import SessionLocal
from app.crud.transaction_crud import create_transaction
from app.models.transactions import TransactionStatus
from app.models.raw_messages import RawMessages
from app.models.groups import Groups
from app.models.participants import Participants

def insert_dummy_transaction():
    db = SessionLocal()
    
    try:
        print("--> Fetching prerequisite Group and Participant...")
        # Fetch an existing group and participant to satisfy strict Foreign Key constraints
        mock_group = db.query(Groups).first()
        mock_participant = db.query(Participants).first()

        if not mock_group or not mock_participant:
            print("❌ Cannot insert: The database must have at least one Group and one Participant saved first to link the RawMessage to.")
            return

        print("--> Creating prerequisite raw message...")
        # 1. Map fields exactly to your RawMessages model
        mock_message = RawMessages(
            tenant_id=1,
            group_id=mock_group.id,                           # Required FK
            sender_id=mock_participant.id,                    # Required FK
            message_id=f"mock_msg_{uuid.uuid4().hex[:8]}",    # Required unique string
            raw_text=f"Mock payment message at {datetime.now()}", # Replaces 'body'
            raw_json={"test": "data"},                        # Required JSONB
            received_at=datetime.now(timezone.utc),           # Replaces 'message_timestamp'
            hash=f"mock_hash_{uuid.uuid4().hex}"              # Required unique string
        )
        db.add(mock_message)
        db.commit()
        db.refresh(mock_message)

        print("--> Inserting new transaction...")
        # 2. Define the transaction payload
        txn_data = {
            "tenant_id": 1,
            "raw_message_id": mock_message.id,
            "amount": Decimal("99.99"),
            "currency": "ZMW",
            "txn_type": "debit",
            "txn_date": datetime.now(timezone.utc),
            "remarks": "Frontend Sync Test Entry",
            "confidence": 0.99,
            "status": TransactionStatus.PARSED,
            "hash": uuid.uuid4().hex
        }

        # 3. Use CRUD function to insert safely
        new_txn = create_transaction(db=db, txn_data=txn_data, commit=True, actor_identifier="manual_seed_script")
        
        print(f"✅ Success! Inserted Transaction ID: {new_txn.id} for Amount: {new_txn.amount}")

    except Exception as e:
        print(f"❌ Error inserting transaction: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    insert_dummy_transaction()