"""Department ORM model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class Department(Base):
    """Enterprise department model."""

    __tablename__ = "departments"

    department_id: Mapped[int] = Column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = Column(String(150), nullable=False, unique=True)
    code: Mapped[str | None] = Column(String(50), nullable=True, unique=True)
    description: Mapped[str | None] = Column(Text, nullable=True)
    is_active: Mapped[bool] = Column(String(1), default="Y", nullable=False)
    created_at: Mapped[datetime] = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    users: Mapped[list["User"]] = relationship(back_populates="department")
