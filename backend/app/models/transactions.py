from sqlalchemy import Integer, Text, Numeric, Float, DateTime, ForeignKey, String, CheckConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from decimal import Decimal

from app.models.base import Base, TimestampMixin

class Transactions(Base, TimestampMixin):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, autoincrement=True, primary_key=True)
    raw_message_id: Mapped[int] = mapped_column(Integer, ForeignKey("raw_messages.id"))
    amount: Mapped[Decimal] = mapped_column(Numeric(18,2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="ZMW")
    txn_type: Mapped[str] = mapped_column(Text, nullable=False)
    txn_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    remarks: Mapped[str] = mapped_column(Text, nullable=True)
    total: Mapped[Decimal] = mapped_column(Numeric(18,2), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(Text, server_default="NOT PARSED", nullable=False)
    hash: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)

    __table_args__ = (
        CheckConstraint(txn_type.in_(['credit', 'debit']), name='check_txn_type'),
        Index('idx_txn_hash', 'hash', unique=True)
    )

    def __repr__(self) -> str:
        return f"<Transaction(id={self.id}, txn_type='{self.txn_type}', amount={self.amount}, status='{self.status}')>" 