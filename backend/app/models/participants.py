from decimal import Decimal
from typing import Optional
from sqlalchemy import String, Text, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin

class Participants(Base, TimestampMixin):
    __tablename__ = "participants"

    id: Mapped[int] = mapped_column(Integer, autoincrement=True, primary_key=True)
    phone: Mapped[str] = mapped_column(String(32), nullable=False)
    displayname: Mapped[str] = mapped_column(String(64), nullable=False)
    username: Mapped[str] = mapped_column(Text, nullable=True, unique=True)
    messages: Mapped[list["RawMessages"]] = relationship("RawMessages", back_populates="sender")

    def __repr__(self)-> str:
        return f"Participants(id={self.id}, displayname={self.displayname}, username={self.username})"