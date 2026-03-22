from app.database.database import SessionLocal
from sqlalchemy import text

db = SessionLocal()

# Check if the index and table are out of sync
r = db.execute(text("""
    SELECT COUNT(*) FROM transactions
""")).scalar()
print("Table row count:", r)

# Force an index scan specifically
r2 = db.execute(text("""
    SELECT COUNT(*) FROM transactions WHERE hash IS NOT NULL
""")).scalar()
print("Rows with non-null hash:", r2)

# Check if the hash exists via index
r3 = db.execute(text("""
    SELECT hash FROM transactions WHERE hash = 'a5c6b069994249a7b10a115c884cb9f8'
""")).fetchall()
print("Direct hash lookup:", r3)

# Check pg_stat for the index
r4 = db.execute(text("""
    SELECT relname, n_live_tup, n_dead_tup 
    FROM pg_stat_user_tables 
    WHERE relname = 'transactions'
""")).fetchone()
print("Live tuples:", r4)

db.close()
