"""Face sample ORM model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BLOB, Column, DateTime, ForeignKey, Integer, Sequence, String, Text
from sqlalchemy.orm import Mapped, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class FaceSample(Base):
    """Face biometric sample for registration and recognition."""

    __tablename__ = "face_samples"

    face_sample_id: Mapped[int] = Column(
        Integer,
        Sequence("face_samples_seq"),
        primary_key=True,
        nullable=False,
    )
    user_id: Mapped[int] = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    pose: Mapped[str] = Column(String(50), nullable=False)
    image_path: Mapped[str] = Column(String(500), nullable=False)
    embedding_blob: Mapped[bytes | None] = Column(BLOB, nullable=True)
    quality_score: Mapped[float | None] = Column(Integer, nullable=True)
    created_at: Mapped[datetime] = Column(DateTime, default=datetime.utcnow, nullable=False)

    user: Mapped["User"] = relationship(back_populates="face_samples")
