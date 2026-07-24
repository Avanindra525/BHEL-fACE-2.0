"""Login log ORM model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Sequence, String, Text
from sqlalchemy.orm import Mapped, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class LoginLog(Base):
    """Audit trail for user login activity."""

    __tablename__ = "login_logs"

    login_log_id: Mapped[int] = Column(
        Integer,
        Sequence("login_logs_seq"),
        primary_key=True,
        nullable=False,
    )
    user_id: Mapped[int | None] = Column(Integer, ForeignKey("users.user_id"), nullable=True)
    login_time: Mapped[datetime] = Column(DateTime, default=datetime.utcnow, nullable=False)
    ip_address: Mapped[str | None] = Column(String(100), nullable=True)
    user_agent: Mapped[str | None] = Column(Text, nullable=True)
    success: Mapped[bool] = Column(String(1), default="Y", nullable=False)
    login_method: Mapped[str] = Column(String(50), default="password", nullable=False)
    failure_reason: Mapped[str | None] = Column(Text, nullable=True)

    user: Mapped["User"] = relationship(back_populates="login_logs")
