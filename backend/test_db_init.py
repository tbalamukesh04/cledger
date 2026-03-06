# backend/test_db_init.py
try:
    from app.database.database import engine, get_db

    print("✅ Module imported successfully!")
    print(f"✅ Database engine initialized: {engine}")
except Exception as e:
    print(f"❌ Error: {e}")
