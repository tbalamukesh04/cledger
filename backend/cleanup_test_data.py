from app.database.database import SessionLocal
from sqlalchemy import text

db = SessionLocal()
try:
    db.execute(text("DELETE FROM transaction_audit WHERE actor_identifier = 'worker-test'"))
    db.execute(text("DELETE FROM transactions WHERE remarks = 'Audit test transaction'"))
    db.execute(text("DELETE FROM raw_messages WHERE message_id LIKE 'wamid.AUDIT_%'"))
    db.execute(text("DELETE FROM groups WHERE group_id LIKE 'grp_audit_%'"))
    db.execute(text("DELETE FROM participants WHERE displayname = 'Audit Tester'"))
    db.commit()
    print("Cleanup done.")
except Exception as e:
    db.rollback()
    print(f"Cleanup failed: {e}")
finally:
    db.close()