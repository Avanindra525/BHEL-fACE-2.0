"""Base repository utilities."""

from __future__ import annotations

from typing import Generic, TypeVar

from sqlalchemy import text
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

    def _assign_primary_key(self, obj: ModelT) -> None:
        """Populate an Oracle-friendly primary key when the ORM is not doing so automatically."""

        pk_column = next(iter(self.model.__table__.primary_key.columns))
        pk_name = pk_column.name
        if getattr(obj, pk_name, None) is not None:
            return

        table_name = self.model.__tablename__
        sequence_name = f"{table_name}_seq"
        try:
            sequence_value = self.session.execute(text(f"SELECT {sequence_name}.NEXTVAL FROM dual")).scalar()
        except Exception:
            sequence_value = self.session.execute(
                text(f"SELECT COALESCE(MAX({pk_name}), 0) + 1 FROM {table_name}")
            ).scalar()

        setattr(obj, pk_name, int(sequence_value))

    def add(self, obj: ModelT) -> ModelT:
        """Add an entity to the session."""

        self._assign_primary_key(obj)
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
