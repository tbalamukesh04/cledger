from sqlalchemy import Integer, String, Numeric, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from decimal import Decimal

from app.models.base import Base, TimestampMixin

class BankAccount(Base, TimestampMixin):
    __tablename__ = "bank_accounts"

    # Primary Identifiers
    id: Mapped[int] = mapped_column(Integer, autoincrement=True, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=True, index=True) # Essential for multi-tenant isolation
    
    # Core Transaction Data
    transaction_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    transaction_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    transaction_type: Mapped[str] = mapped_column(String(50), nullable=False) # e.g., "credit", "debit", "fee"
    
    # External References for Reconciliation
    reference_identifier: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    
    # Operator/Entity Details
    operator_identifier: Mapped[str | None] = mapped_column(String(100), nullable=True)
    operator_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    
    # Ledger State
    resulting_balance: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    __table_args__ = (
        UniqueConstraint('tenant_id', 'reference_identifier', name='uq_tenant_bank_reference'),
    )

    def __repr__(self) -> str:
        return f"<BankAccount(id={self.id}, ref='{self.reference_identifier}', amount={self.transaction_amount}, type='{self.transaction_type}')>"