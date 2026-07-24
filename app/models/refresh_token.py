"""Refresh token ORM model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Sequence, String
from sqlalchemy.orm import Mapped, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class RefreshToken(Base):
    """JWT refresh token persistence."""

    __tablename__ = "refresh_tokens"

    refresh_token_id: Mapped[int] = Column(
        Integer,
        Sequence("refresh_tokens_seq"),
        primary_key=True,
        nullable=False,
    )
    user_id: Mapped[int] = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    token: Mapped[str] = Column(String(500), nullable=False, unique=True)
    expires_at: Mapped[datetime] = Column(DateTime, nullable=False)
    revoked: Mapped[bool] = Column(String(1), default="N", nullable=False)
    created_at: Mapped[datetime] = Column(DateTime, default=datetime.utcnow, nullable=False)

    user: Mapped["User"] = relationship(back_populates="refresh_tokens")
