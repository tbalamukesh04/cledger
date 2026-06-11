# tbalamukesh04/cledger/cledger-develop/backend/app/models/users.py
from datetime import datetime
from sqlalchemy import Integer, String, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin

class Users(Base, TimestampMixin):
    """
    Dedicated SaaS Application User model providing absolute separation 
    between administrative accounts and external multi-tenant communication actors.
    """
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, autoincrement=True, primary_key=True)
    business_id: Mapped[int] = mapped_column(Integer, ForeignKey("businesses.id", ondelete="RESTRICT"), nullable=False, index=True)
    auth0_user_id: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)

    # Bidirectional Relationship Mapping
    business: Mapped["Businesses"] = relationship("Businesses", back_populates="users")

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email='{self.email}', display_name='{self.display_name}')>"