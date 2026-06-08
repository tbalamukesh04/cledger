import os

from dotenv import load_dotenv
import redis
from sqlalchemy import text

from app.database.database import engine

load_dotenv()

def test_postgres():
    print("Testing PostgreSQL connection...")
    try:
        with engine.connect() as connection:
            result = connection.execute(text("SELECT version();"))
            version = result.scalar()
            print(f"Connection successful! PostgreSQL version: {version}")
    except Exception as e:
        print(f"Connection failed: {e}")
        
def test_redis():
    print("Testing Redis...")
    try:
        redis_url = os.getenv("REDIS_URL")
        if not redis_url:
            raise ValueError("No Redis URL Found")
            
        r = redis.Redis.from_url(redis_url, decode_responses=True)
        
        response = r.ping()
        if response:
            print("Connection successful:)")
        else:
            print("Connection failed:(")
    except Exception as e:
        print(f"Connection failed: {e}")
        
if __name__ == "__main__":
    print("Testing setup...")
    test_postgres()
    test_redis()