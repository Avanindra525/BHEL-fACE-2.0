"""Password history ORM model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Sequence, String
from sqlalchemy.orm import Mapped, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class PasswordHistory(Base):
    """Prior password hashes for reuse prevention."""

    __tablename__ = "password_history"

    password_history_id: Mapped[int] = Column(
        Integer,
        Sequence("password_history_seq"),
        primary_key=True,
        nullable=False,
    )
    user_id: Mapped[int] = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    password_hash: Mapped[str] = Column(String(255), nullable=False)
    created_at: Mapped[datetime] = Column(DateTime, default=datetime.utcnow, nullable=False)

    user: Mapped["User"] = relationship(back_populates="password_history")
