"""User ORM model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Sequence, String, Text
from sqlalchemy.orm import Mapped, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.audit_log import AuditLog
    from app.models.department import Department
    from app.models.face_sample import FaceSample
    from app.models.login_log import LoginLog
    from app.models.password_history import PasswordHistory
    from app.models.refresh_token import RefreshToken
    from app.models.role import Role


class User(Base):
    """Employee/user account model."""

    __tablename__ = "users"

    user_id: Mapped[int] = Column(
        Integer,
        Sequence("users_seq"),
        primary_key=True,
        nullable=False,
    )
    username: Mapped[str] = Column(String(100), nullable=False, unique=True)
    email: Mapped[str] = Column(String(255), nullable=False, unique=True)
    staff_number: Mapped[str | None] = Column(String(50), nullable=True, unique=True)
    full_name: Mapped[str] = Column(String(200), nullable=False)
    password_hash: Mapped[str] = Column(String(255), nullable=False)
    role_id: Mapped[int | None] = Column(Integer, ForeignKey("roles.role_id"), nullable=True)
    department_id: Mapped[int | None] = Column(Integer, ForeignKey("departments.department_id"), nullable=True)
    is_active: Mapped[bool] = Column(String(1), default="Y", nullable=False)
    is_locked: Mapped[bool] = Column(String(1), default="N", nullable=False)
    failed_login_attempts: Mapped[int] = Column(Integer, default=0, nullable=False)
    last_login_at: Mapped[datetime | None] = Column(DateTime, nullable=True)
    password_changed_at: Mapped[datetime | None] = Column(DateTime, nullable=True)
    profile_completed: Mapped[bool] = Column(String(1), default="N", nullable=False)
    face_registered: Mapped[bool] = Column(String(1), default="N", nullable=False)
    created_at: Mapped[datetime] = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    bio: Mapped[str | None] = Column(Text, nullable=True)

    role: Mapped["Role"] = relationship(back_populates="users")
    department: Mapped["Department"] = relationship(back_populates="users")
    face_samples: Mapped[list["FaceSample"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    login_logs: Mapped[list["LoginLog"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    password_history: Mapped[list["PasswordHistory"]] = relationship(back_populates="user", cascade="all, delete-orphan")
