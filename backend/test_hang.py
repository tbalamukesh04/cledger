import os
import redis
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

print("1. Testing Redis Connection...")
try:
    r = redis.Redis.from_url(os.getenv("TEST_REDIS_URL", "redis://127.0.0.1:6379/1"), socket_timeout=3)
    r.ping()
    print("✅ Redis is responsive!")
except Exception as e:
    print(f"❌ Redis failed: {e}")

print("2. Testing Database Connection & Locks...")
try:
    engine = create_engine(os.getenv("TEST_DATABASE_URL", "postgresql://dev_user:dev_password@127.0.0.1:5432/cledger_test"))
    with engine.begin() as conn:
        print("   DB Connected. Attempting to drop schema (checking for locks)...")
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    print("✅ Database is unlocked and responsive!")
except Exception as e:
    print(f"❌ Database failed: {e}")

print("Done.")