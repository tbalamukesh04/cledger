from typing import Optional
from sqlalchemy import String, Text, Integer, Numeric, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

class Groups(Base, TimestampMixin):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(Integer, autoincrement=True, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("businesses.id", ondelete="RESTRICT"), nullable=True, index=True)
    group_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    groupname: Mapped[str] = mapped_column(Text)

    business: Mapped[Optional["Businesses"]] = relationship("Businesses", back_populates="groups")
    messages: Mapped[list["RawMessages"]] = relationship("RawMessages", back_populates="group")

    def __repr__(self):
        return f"<ID: >{self.id}, <Group ID:> {self.group_id}, <Group Name>{self.groupname}"