"""User repository."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    """Repository for user persistence."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, User)

    def get_by_username(self, username: str) -> User | None:
        """Fetch a user by username."""

        return self.session.query(User).filter(User.username == username).first()

    def get_by_email(self, email: str) -> User | None:
        """Fetch a user by email address."""

        return self.session.query(User).filter(User.email == email).first()

    def get_by_staff_number(self, staff_number: str) -> User | None:
        """Fetch a user by staff number."""

        return self.session.query(User).filter(User.staff_number == staff_number).first()
