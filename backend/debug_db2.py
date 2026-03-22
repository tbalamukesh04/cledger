from app.database.database import SessionLocal, engine
from sqlalchemy import text

print("DB URL:", engine.url)

db = SessionLocal()

r = db.execute(text("SELECT current_database(), current_schema()")).fetchone()
print("Connected to database:", r[0], "schema:", r[1])

r2 = db.execute(text("SELECT COUNT(*) FROM transactions")).scalar()
print("Transactions in current schema:", r2)

r3 = db.execute(text("""
    SELECT schemaname, tablename 
    FROM pg_tables 
    WHERE tablename = 'transactions'
""")).fetchall()
print("All 'transactions' tables across schemas:", r3)

r4 = db.execute(text("""
    SELECT last_value FROM transactions_id_seq
""")).scalar()
print("transactions_id_seq last value:", r4)

r5 = db.execute(text("""
    SELECT last_value FROM raw_messages_id_seq
""")).scalar()
print("raw_messages_id_seq last value:", r5)

db.close()