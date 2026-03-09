import enum
from sqlalchemy import Integer, String, Text, DateTime, Enum, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from datetime import datetime
from typing import Any

from app.models.base import Base

class EventType(str, enum.Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"

class ActorType(str, enum.Enum):
    SYSTEM = "system"
    USER = "user"
    WEBHOOK = "webhook"

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id:Mapped[int] = mapped_column(Integer, autoincrement=True, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(Enum(EventType, name="audit_event_type_enum"), nullable=False, index=True)
    actor_type: Mapped[str] = mapped_column(Enum(ActorType, name= "audit_actor_type_enum"), nullable=False)
    actor_identifier: Mapped[str] = mapped_column(String(255), nullable=True, index=True)

    old_state: Mapped[dict[str, Any]|None] = mapped_column(JSONB, nullable = True)
    new_state: Mapped[dict[str, Any]|None] = mapped_column(JSONB, nullable = True)

    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    action_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    def __repr__(self) -> str:
        return f"<AuditLog(id={self.id}, entity='{self.entity_type}:{self.entity_id}', event='{self.event_type}')>"