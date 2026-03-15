from datetime import datetime
from typing import Any, Optional
from sqlalchemy import Text, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

class RawMessages(Base, TimestampMixin):
    __tablename__ = "raw_messages"
    
    id: Mapped[int] = mapped_column(Integer, autoincrement=True, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    group_id: Mapped[int] = mapped_column(Integer, ForeignKey("groups.id"), nullable=False, index=True)
    sender_id: Mapped[int] = mapped_column(Integer, ForeignKey("participants.id"), nullable=False, index=True)
    message_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    raw_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    processed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    is_transaction: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    hash: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)

    processing_status: Mapped[str] = mapped_column(String(50), default = "pending", server_default = "pending", nullable=False)
    processing_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    processing_completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    sender: Mapped[Optional["Participants"]] = relationship("Participants", back_populates="messages")
    group: Mapped[Optional["Groups"]] = relationship("Groups", back_populates="messages")

    def __repr__(self) -> str:
        return f"<RawMessage(id={self.id}, whatsapp_message_id='{self.whatsapp_message_id}', processed={self.processed})>"
