"""Department Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class DepartmentBase(BaseModel):
    """Common department fields."""

    model_config = ConfigDict(from_attributes=True)

    name: str = Field(min_length=2, max_length=150)
    code: Optional[str] = Field(default=None, max_length=50)
    description: Optional[str] = None


class DepartmentCreate(DepartmentBase):
    """Payload for creating a department."""

    pass


class DepartmentUpdate(BaseModel):
    """Payload for updating a department."""

    model_config = ConfigDict(from_attributes=True)

    name: Optional[str] = Field(default=None, min_length=2, max_length=150)
    code: Optional[str] = Field(default=None, max_length=50)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class DepartmentResponse(DepartmentBase):
    """Department response payload."""

    department_id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
