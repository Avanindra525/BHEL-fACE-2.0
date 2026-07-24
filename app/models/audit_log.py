"""Audit log ORM model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Sequence,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class AuditLog(Base):
    """Security and admin audit event."""

    __tablename__ = "audit_logs"

    # Oracle sequence created in setup_oracle.py
    audit_log_id: Mapped[int] = Column(
        Integer,
        Sequence("audit_logs_seq"),
        primary_key=True,
        nullable=False,
    )

    user_id: Mapped[int | None] = Column(
        Integer,
        ForeignKey("users.user_id"),
        nullable=True,
    )

    action: Mapped[str] = Column(
        String(200),
        nullable=False,
    )

    details: Mapped[str | None] = Column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    user: Mapped["User"] = relationship(
        "User",
        back_populates="audit_logs",
    )