from typing import Generator
from fastapi import Request
from sqlalchemy.orm import Session
from redis import Redis

from app.database.database import SessionLocal

def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that provides a database session for a single request.
    Ensures the session is cleanly closed after the request finishes.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_redis(request: Request) -> Redis:
    """
    FastAPI dependency to retrieve the Redis client attached to the app state
    during the application lifecycle startup.
    """
    return request.app.state.redis