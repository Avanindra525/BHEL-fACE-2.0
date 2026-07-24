"""Role ORM model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, Integer, Sequence, String, Text
from sqlalchemy.orm import Mapped, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.permission import Permission
    from app.models.role_permission import RolePermission
    from app.models.user import User


class Role(Base):
    """Role that groups permissions."""

    __tablename__ = "roles"

    role_id: Mapped[int] = Column(
        Integer,
        Sequence("roles_seq"),
        primary_key=True,
        nullable=False,
    )
    name: Mapped[str] = Column(String(100), nullable=False, unique=True)
    description: Mapped[str | None] = Column(Text, nullable=True)
    is_active: Mapped[bool] = Column(String(1), default="Y", nullable=False)
    created_at: Mapped[datetime] = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    role_permissions: Mapped[list["RolePermission"]] = relationship(back_populates="role", cascade="all, delete-orphan")
    permissions: Mapped[list["Permission"]] = relationship(secondary="role_permissions", back_populates="roles")
    users: Mapped[list["User"]] = relationship(back_populates="role")
