"""Role repository."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.role import Role
from app.repositories.base import BaseRepository


class RoleRepository(BaseRepository[Role]):
    """Repository for role persistence."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Role)
