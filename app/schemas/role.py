"""Role Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class RoleBase(BaseModel):
    """Common role fields."""

    model_config = ConfigDict(from_attributes=True)

    name: str = Field(min_length=2, max_length=100)
    description: Optional[str] = None


class RoleCreate(RoleBase):
    """Payload for creating a role."""

    pass


class RoleUpdate(BaseModel):
    """Payload for updating a role."""

    model_config = ConfigDict(from_attributes=True)

    name: Optional[str] = Field(default=None, min_length=2, max_length=100)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class RoleResponse(RoleBase):
    """Role response payload."""

    role_id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
