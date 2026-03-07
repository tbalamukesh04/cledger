from app.models.base import Base, TimestampMixin
from sqlalchemy.orm import Mapped, mapped_column

class TestModel(Base, TimestampMixin):
    __tablename__ = "test"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(nullable=False)
    description: Mapped[str] = mapped_column(nullable=False)