import enum
from datetime import datetime
from typing import Any

from sqlalchemy import Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.models.base import Base


class TransactionAuditAction(str, enum.Enum):
    CREATED = "transaction_created"
    UPDATED = "transaction_updated"
    STATUS_CHANGED = "transaction_status_changed"
    CORRECTED = "transaction_corrected"
    INVALIDATED = "transaction_invalidated"


class TransactionAudit(Base):
    __tablename__ = "transaction_audit"

    id: Mapped[int] = mapped_column(Integer, autoincrement=True, primary_key=True)
    transaction_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("transactions.id"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(Text, nullable=False)
    old_value: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    new_value: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    actor_identifier: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    business_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    actor_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    transaction = relationship("Transactions", backref="audit_entries")

    def __repr__(self) -> str:
        return (
            f"<TransactionAudit(id={self.id}, transaction_id={self.transaction_id}, "
            f"action='{self.action}', actor='{self.actor_identifier}')>"
        )

