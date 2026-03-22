from app.database.database import SessionLocal
from sqlalchemy import text

db = SessionLocal()

r = db.execute(text("""
    SELECT column_name, column_default 
    FROM information_schema.columns 
    WHERE table_name = 'transactions'
""")).fetchall()
print("Column defaults:")
for row in r:
    print(f"  {row[0]}: {row[1]}")

r2 = db.execute(text("""
    SELECT trigger_name, event_manipulation, action_statement
    FROM information_schema.triggers
    WHERE event_object_table = 'transactions'
""")).fetchall()
print("Triggers on transactions:")
for row in r2:
    print(f"  {row[0]} {row[1]}: {row[2]}")

db.close()