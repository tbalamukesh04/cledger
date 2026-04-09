import os
import redis 
import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from unittest.mock import patch

from app.models.base import Base
from app.models.raw_messages import RawMessages
from app.models.groups import Groups
from app.models.participants import Participants
from app.models.transactions import Transactions

load_dotenv()

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:5432/cledger_test")
TEST_REDIS_URL = os.getenv("TEST_REDIS_URL", "redis://127.0.0.1:6379/1")

@pytest.fixture(scope="function")
def db_session():
    # Fail fast after 3 seconds instead of hanging infinitely
    engine = create_engine(TEST_DATABASE_URL, connect_args={"connect_timeout": 3})
    
    # Safely drop and recreate tables without triggering a schema-level deadlock
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()

    with patch('app.workers.job_handler.SessionLocal', return_value=session), \
         patch('app.database.database.SessionLocal', return_value=session):
        yield session

    session.close()
    engine.dispose()

@pytest.fixture(scope="function")
def mock_redis():
    # Fail fast after 3 seconds instead of hanging infinitely
    redis_client = redis.Redis.from_url(TEST_REDIS_URL, decode_responses=True, socket_timeout=3)
    redis_client.flushdb()

    with patch('app.database.redis_client.redis_client', redis_client), \
        patch('app.database.redis_client.get_redis_client', return_value=redis_client):
        yield redis_client

# --- Restored missing fixture ---
@pytest.fixture(scope="function")
def mock_gemini():
    """Provides a mocked Gemini API client to prevent real LLM calls."""
    with patch('app.ai.gemini_client.GeminiClient.generate_content') as mock_generate:
        yield mock_generate