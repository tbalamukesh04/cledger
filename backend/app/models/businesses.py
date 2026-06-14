from datetime import datetime
from sqlalchemy import Integer, String, Boolean, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

class Businesses(Base, TimestampMixin):
    __tablename__ = "businesses"

    id: Mapped[int] = mapped_column(Integer, autoincrement=True, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    auth0_org_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    meta_waba_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    meta_phone_number_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    
    # Meta Graph API Token Storage
    meta_access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    meta_business_account_id: Mapped[str | None] = mapped_column(String, nullable=True)
    meta_token_last_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # WABA Webhook Subscription State
    waba_subscription_status: Mapped[str | None] = mapped_column(String, nullable=True)
    waba_subscription_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    waba_subscription_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    waba_last_subscription_check: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)

    # Onboarding Lifecycle Context Metrics
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    created_via: Mapped[str] = mapped_column(String, default="auth0_auto_onboard", server_default="'auth0_auto_onboard'", nullable=False)
    onboarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Cross-tenant Relationship Mappings
    users: Mapped[list["Users"]] = relationship("Users", back_populates="business")
    groups: Mapped[list["Groups"]] = relationship("Groups", back_populates="business")
    participants: Mapped[list["Participants"]] = relationship("Participants", back_populates="business")
    raw_messages: Mapped[list["RawMessages"]] = relationship("RawMessages", back_populates="business")
    transactions: Mapped[list["Transactions"]] = relationship("Transactions", back_populates="business")

    def __repr__(self) -> str:
        return f"<Business(id={self.id}, name='{self.name}', slug='{self.slug}')>"
