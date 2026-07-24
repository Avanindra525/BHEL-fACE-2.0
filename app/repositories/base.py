"""Base repository utilities."""

from __future__ import annotations

from typing import Generic, TypeVar

from sqlalchemy.orm import Session

ModelT = TypeVar("ModelT")


class BaseRepository(Generic[ModelT]):
    """Generic CRUD repository wrapper."""

    def __init__(self, session: Session, model: type[ModelT]) -> None:
        self.session = session
        self.model = model

    def get_by_id(self, obj_id: int) -> ModelT | None:
        """Fetch an entity by primary key."""

        return self.session.get(self.model, obj_id)

    def list_all(self) -> list[ModelT]:
        """Return all entities."""

        return self.session.query(self.model).all()

    def add(self, obj: ModelT) -> ModelT:
        """Add an entity to the session."""

        self.session.add(obj)
        self.session.commit()
        self.session.refresh(obj)
        return obj

    def update(self, obj: ModelT) -> ModelT:
        """Persist an updated entity."""

        self.session.commit()
        self.session.refresh(obj)
        return obj

    def delete(self, obj: ModelT) -> None:
        """Delete an entity."""

        self.session.delete(obj)
        self.session.commit()
