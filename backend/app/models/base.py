from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, DateTime
from sqlalchemy.sql import func

Base = declarative_base()

class TimestampMixin:
    """
    A mixin that adds Standard Timestamp to any model that inherits it. 
    Useful for auditing Financial transactions."""
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False, index=True)