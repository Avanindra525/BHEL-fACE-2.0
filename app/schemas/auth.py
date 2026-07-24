"""Authentication-related Pydantic schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class LoginRequest(BaseModel):
    """Login request payload."""

    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=8, max_length=200)


class RegisterRequest(BaseModel):
    """User registration payload."""

    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=100)
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=200)
    password: str = Field(min_length=8, max_length=200)
    password_confirmation: str = Field(min_length=8, max_length=200)
    staff_number: str | None = None
    profile_completed: bool = False

    def model_post_init(self, __context: object) -> None:
        if self.password != self.password_confirmation:
            raise ValueError("passwords do not match")


class TokenResponse(BaseModel):
    """Returned authentication tokens."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
