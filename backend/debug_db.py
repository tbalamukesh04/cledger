from app.database.database import SessionLocal
from sqlalchemy import text

db = SessionLocal()

r = db.execute(text("SELECT COUNT(*) FROM transactions")).scalar()
print("Transactions count:", r)

r2 = db.execute(text("SELECT COUNT(*) FROM transaction_audit")).scalar()
print("Audit rows:", r2)

r3 = db.execute(text("""
    SELECT indexname, indexdef 
    FROM pg_indexes 
    WHERE tablename = 'transactions'
""")).fetchall()
print("Indexes on transactions:")
for row in r3:
    print(" ", row[0], "->", row[1])

r4 = db.execute(text("""
    SELECT conname, contype, pg_get_constraintdef(oid)
    FROM pg_constraint
    WHERE conrelid = 'transactions'::regclass
""")).fetchall()
print("Constraints on transactions:")
for row in r4:
    print(" ", row[0], "->", row[2])

db.close()