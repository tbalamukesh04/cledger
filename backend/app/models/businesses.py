from sqlalchemy import Integer, String, Boolean
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
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)

    # Cross-tenant Relationship Mappings
    groups: Mapped[list["Groups"]] = relationship("Groups", back_populates="business")
    participants: Mapped[list["Participants"]] = relationship("Participants", back_populates="business")
    raw_messages: Mapped[list["RawMessages"]] = relationship("RawMessages", back_populates="business")
    transactions: Mapped[list["Transactions"]] = relationship("Transactions", back_populates="business")

    def __repr__(self) -> str:
        return f"<Business(id={self.id}, name='{self.name}', slug='{self.slug}')>"
