"""User-related Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserBase(BaseModel):
    """Common fields for user payloads."""

    model_config = ConfigDict(from_attributes=True)

    username: str = Field(min_length=3, max_length=100)
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=200)
    staff_number: Optional[str] = None
    department_id: Optional[int] = None
    bio: Optional[str] = None
    profile_completed: bool = False
    face_registered: bool = False


class UserCreate(UserBase):
    """Payload for creating a user."""

    password: str = Field(min_length=8, max_length=200)


class UserUpdate(BaseModel):
    """Payload for updating a user."""

    model_config = ConfigDict(from_attributes=True)

    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    bio: Optional[str] = None
    profile_completed: Optional[bool] = None
    face_registered: Optional[bool] = None
    is_active: Optional[str] = None
    is_locked: Optional[str] = None
    department_id: Optional[int] = None


class UserResponse(UserBase):
    """Payload used in responses."""

    user_id: int
    role_id: Optional[int] = None
    department_id: Optional[int] = None
    is_active: bool
    is_locked: bool
    created_at: datetime
    updated_at: datetime
