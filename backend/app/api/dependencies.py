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

def get_current_tenant_id(request: Request) -> int:
    """
    Scaffolding context dependency for multi-tenancy enforcement.
    Extracts tenant identity headers or organization metadata parsed out of the security token layers.
    Defaults cleanly to 1 (Legacy Default Tenant Context) during current single-tenant evolutionary phase.
    """
    # Future SaaS Blueprint Hook:
    # token_payload = request.state.user_token_claims
    # return token_payload.get("tenant_database_identifier")
    
    # Extract structural fallback from custom enterprise routing header if passed explicitly
    tenant_header = request.headers.get("X-Tenant-ID")
    if tenant_header and tenant_header.isdigit():
        return int(tenant_header)
        
    return 1