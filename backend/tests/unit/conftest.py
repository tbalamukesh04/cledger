import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB
from unittest.mock import patch, MagicMock

# Import Base and all models so SQLAlchemy knows what tables to create
from app.models.base import Base
from app.models.raw_messages import RawMessages
from app.models.groups import Groups
from app.models.participants import Participants
from app.models.transactions import Transactions

# --- SQLite Compatibility Hook ---
# SQLite does not support Postgres JSONB natively. This tells SQLAlchemy 
# to treat JSONB as standard JSON when running our in-memory tests.
@compiles(JSONB, 'sqlite')
def compile_jsonb_sqlite(type_, compiler, **kw):
    return 'JSON'

# --- 1. Database Fixture (In-Memory SQLite) ---
@pytest.fixture(scope="function")
def db_session():
    """Provides an isolated, in-memory SQLite database session for every test."""
    engine = create_engine(
        "sqlite:///:memory:", 
        connect_args={"check_same_thread": False}
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    # Create all tables in the temporary memory
    Base.metadata.create_all(bind=engine)
    
    session = TestingSessionLocal()
    
    # Globally patch SessionLocal so the app/workers use our in-memory DB
    with patch('app.workers.job_handler.SessionLocal', return_value=session), \
         patch('app.database.database.SessionLocal', return_value=session):
        yield session
        
    session.close()
    Base.metadata.drop_all(bind=engine)

# --- 2. Redis Fixture ---
@pytest.fixture(scope="function")
def mock_redis():
    """Provides a mocked Redis client to prevent external network calls."""
    with patch('app.database.redis_client.redis_client') as mock_redis_client:
        # Default behavior: pretend the queue is empty unless overridden
        mock_redis_client.brpop.return_value = None
        yield mock_redis_client

# --- 3. Gemini LLM Fixture ---
@pytest.fixture(scope="function")
def mock_gemini():
    """Provides a mocked Gemini API client to prevent real LLM calls and token usage."""
    with patch('app.ai.gemini_client.GeminiClient.generate_content') as mock_generate:
        yield mock_generate
