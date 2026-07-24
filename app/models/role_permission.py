"""Association model for roles and permissions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Column, ForeignKey, Integer, Sequence
from sqlalchemy.orm import Mapped, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.permission import Permission
    from app.models.role import Role


class RolePermission(Base):
    """Join table for role-permission assignments."""

    __tablename__ = "role_permissions"

    role_permission_id: Mapped[int] = Column(
        Integer,
        Sequence("role_permissions_seq"),
        primary_key=True,
        nullable=False,
    )
    role_id: Mapped[int] = Column(Integer, ForeignKey("roles.role_id"), nullable=False)
    permission_id: Mapped[int] = Column(Integer, ForeignKey("permissions.permission_id"), nullable=False)

    role: Mapped["Role"] = relationship(back_populates="role_permissions")
    permission: Mapped["Permission"] = relationship(back_populates="role_permissions")
