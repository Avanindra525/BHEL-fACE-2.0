"""Permission Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class PermissionBase(BaseModel):
    """Common permission fields."""

    model_config = ConfigDict(from_attributes=True)

    name: str = Field(min_length=2, max_length=100)
    description: Optional[str] = None


class PermissionCreate(PermissionBase):
    """Payload for creating a permission."""

    pass


class PermissionUpdate(BaseModel):
    """Payload for updating a permission."""

    model_config = ConfigDict(from_attributes=True)

    name: Optional[str] = Field(default=None, min_length=2, max_length=100)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class PermissionResponse(PermissionBase):
    """Permission response payload."""

    permission_id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
