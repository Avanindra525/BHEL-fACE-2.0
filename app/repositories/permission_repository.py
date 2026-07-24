"""Permission repository."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.permission import Permission
from app.repositories.base import BaseRepository


class PermissionRepository(BaseRepository[Permission]):
    """Repository for permission persistence."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Permission)
