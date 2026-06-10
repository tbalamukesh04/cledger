from sqlalchemy import Integer, Text, Numeric, Float, DateTime, ForeignKey, String, CheckConstraint, Index, UniqueConstraint, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
import enum

from app.models.base import Base, TimestampMixin

class TransactionStatus(str, enum.Enum):
    PARSED = 'parsed'
    REVIEW_NEEDED = "review_needed"
    CORRECTED = "corrected"
    INVALIDATED = "invalidated"

class Transactions(Base, TimestampMixin):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, autoincrement=True, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("businesses.id", ondelete="RESTRICT"), nullable=True, index=True)
    raw_message_id: Mapped[int] = mapped_column(Integer, ForeignKey("raw_messages.id"))
    amount: Mapped[Decimal] = mapped_column(Numeric(18,2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="ZMW")
    txn_type: Mapped[str] = mapped_column(Text, nullable=False)
    txn_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    remarks: Mapped[str] = mapped_column(Text, nullable=True)
    total: Mapped[Decimal] = mapped_column(Numeric(18,2), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=True)
    status: Mapped[TransactionStatus] = mapped_column(Enum(TransactionStatus, name="transaction_status_enum", values_callable=lambda obj: [e.value for e in obj]), server_default=TransactionStatus.REVIEW_NEEDED.value, nullable=False)
    hash: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    parsing_meta: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    business: Mapped[Optional["Businesses"]] = relationship("Businesses", back_populates="transactions")
    raw_message = relationship("RawMessages", backref='transaction')
    
    __table_args__ = (
        CheckConstraint(txn_type.in_(['credit', 'debit']), name='check_txn_type'),
        UniqueConstraint('raw_message_id', name = "uq_transaction_raw_message"),
        Index('idx_txn_hash', 'hash', unique=True)
    )

    def to_dict(self) -> dict[str, Any]:
        """Supports clean serialization for downstream API/worker use."""
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "raw_message_id": self.raw_message_id,
            "amount": float(self.amount) if self.amount is not None else None,
            "currency": self.currency,
            "txn_type": self.txn_type,
            "txn_date": self.txn_date.isoformat() if self.txn_date else None,
            "remarks": self.remarks,
            "total": float(self.total) if self.total is not None else None,
            "confidence": self.confidence,
            "status": self.status.value if self.status else None,
            "hash": self.hash,
            "parsing_meta": self.parsing_meta,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }

    def __repr__(self) -> str:
        return f"<Transaction(id={self.id}, tenant_id={self.tenant_id}, txn_type='{self.txn_type}', amount={self.amount}, status='{self.status}')>"