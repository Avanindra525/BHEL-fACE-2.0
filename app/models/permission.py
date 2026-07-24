"""Permission ORM model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.role import Role
    from app.models.role_permission import RolePermission


class Permission(Base):
    """Fine-grained permission model."""

    __tablename__ = "permissions"

    permission_id: Mapped[int] = Column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = Column(String(100), nullable=False, unique=True)
    description: Mapped[str | None] = Column(Text, nullable=True)
    is_active: Mapped[bool] = Column(String(1), default="Y", nullable=False)
    created_at: Mapped[datetime] = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    role_permissions: Mapped[list["RolePermission"]] = relationship(back_populates="permission", cascade="all, delete-orphan")
    roles: Mapped[list["Role"]] = relationship(secondary="role_permissions", back_populates="permissions")
