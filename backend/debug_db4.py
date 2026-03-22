import uuid
from decimal import Decimal
from datetime import datetime, timezone
from app.database.database import SessionLocal
from app.models.transactions import TransactionStatus
from app.models.participants import Participants
from app.models.groups import Groups
from app.models.raw_messages import RawMessages
from app.crud.transaction_crud import create_transaction
from sqlalchemy import text

db = SessionLocal()

# Create prerequisites
p = Participants(tenant_id=1, phone="+260999888777", displayname="Debug Tester")
db.add(p)
g = Groups(tenant_id=1, group_id="grp_debug_test", groupname="Debug Group")
db.add(g)
db.flush()

rm = RawMessages(
    tenant_id=1, sender_id=p.id, group_id=g.id,
    message_id="wamid.DEBUG_TEST_001",
    hash="hash_debug_test_001",
    received_at=datetime.now(timezone.utc),
    raw_json={"test": "debug"}
)
db.add(rm)
db.commit()

test_hash = uuid.uuid4().hex
print("Hash we are inserting:", test_hash)

txn_data = {
    "tenant_id": 1,
    "raw_message_id": rm.id,
    "amount": Decimal("500.00"),
    "currency": "ZMW",
    "txn_type": "debit",
    "txn_date": datetime.now(timezone.utc),
    "confidence": 0.95,
    "status": TransactionStatus.PARSED,
    "hash": test_hash,
    "remarks": "Debug test",
}

try:
    txn = create_transaction(db=db, txn_data=txn_data, commit=True, actor_identifier="debug")
    print("Transaction created with hash:", txn.hash)
    print("Hash matches input:", txn.hash == test_hash)
    
    # Check what's actually in the DB
    r = db.execute(text("SELECT id, hash FROM transactions ORDER BY id DESC LIMIT 3")).fetchall()
    print("Latest transactions in DB:", r)
except Exception as e:
    print("Error:", e)
finally:
    db.execute(text("DELETE FROM transaction_audit WHERE actor_identifier = 'debug'"))
    db.execute(text("DELETE FROM transactions WHERE remarks = 'Debug test'"))
    db.execute(text("DELETE FROM raw_messages WHERE message_id = 'wamid.DEBUG_TEST_001'"))
    db.execute(text("DELETE FROM groups WHERE group_id = 'grp_debug_test'"))
    db.execute(text("DELETE FROM participants WHERE phone = '+260999888777'"))
    db.commit()
    db.close()
    print("Cleaned up.")