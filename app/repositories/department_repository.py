"""Department repository."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.department import Department
from app.repositories.base import BaseRepository


class DepartmentRepository(BaseRepository[Department]):
    """Repository for department persistence."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Department)
