"""Authentication helpers using bcrypt and JWT with enterprise security.

Features:
  - Password hashing with bcrypt (rounds=12)
  - JWT access + refresh token generation (with unique jti for refresh tokens)
  - Password complexity validation
  - Password expiry check
  - Account lockout support
  - Rate-limit-compatible token metadata
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import bcrypt
import jwt

from app.core.config import settings
from app.core.exceptions import AuthenticationError, ValidationError


def hash_password(password: str) -> str:
    """Hash a cleartext password using bcrypt."""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a stored hash."""
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


# ─── Password Complexity ────────────────────────────────────────────────────


PASSWORD_COMPLEXITY_RULES = {
    "min_length": settings.password_min_length,
    "min_uppercase": settings.password_min_uppercase,
    "min_lowercase": settings.password_min_lowercase,
    "min_digits": settings.password_min_digits,
    "min_special": settings.password_min_special,
}


def validate_password_complexity(password: str) -> None:
    """Validate password against enterprise complexity rules.

    Raises ValidationError with a descriptive message if any rule fails.
    """
    errors: list[str] = []

    if len(password) < settings.password_min_length:
        errors.append(f"Password must be at least {settings.password_min_length} characters")

    uppercase = sum(1 for c in password if c.isupper())
    if uppercase < settings.password_min_uppercase:
        errors.append(f"Password must contain at least {settings.password_min_uppercase} uppercase letter(s)")

    lowercase = sum(1 for c in password if c.islower())
    if lowercase < settings.password_min_lowercase:
        errors.append(f"Password must contain at least {settings.password_min_lowercase} lowercase letter(s)")

    digits = sum(1 for c in password if c.isdigit())
    if digits < settings.password_min_digits:
        errors.append(f"Password must contain at least {settings.password_min_digits} digit(s)")

    special = sum(1 for c in password if not c.isalnum())
    if special < settings.password_min_special:
        errors.append(f"Password must contain at least {settings.password_min_special} special character(s)")

    if errors:
        raise ValidationError("; ".join(errors))


def check_password_expired(password_changed_at: datetime | None) -> bool:
    """Check if the password has expired (True = expired, needs change)."""
    if not password_changed_at:
        return True  # Never changed, force change
    elapsed = datetime.utcnow() - password_changed_at
    return elapsed.days > settings.password_expiry_days


# ─── JWT Token Management ──────────────────────────────────────────────────


def create_access_token(
    subject: str,
    extra_claims: dict[str, Any] | None = None,
    remember_me: bool = False,
) -> str:
    """Create a signed JWT access token.

    Args:
        subject: The username (sub claim)
        extra_claims: Additional claims to include
        remember_me: If True, uses extended expiry

    Returns:
        Encoded JWT string
    """
    now = datetime.now(timezone.utc)
    expire_minutes = settings.remember_me_days * 24 * 60 if remember_me else settings.jwt_access_token_expire_minutes

    payload: dict[str, Any] = {
        "sub": subject,
        "iat": now,
        "exp": now + timedelta(minutes=expire_minutes),
        "type": "access",
    }
    if extra_claims:
        payload.update(extra_claims)
    if remember_me:
        payload["remember_me"] = True

    return jwt.encode(payload, settings.app_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(subject: str, remember_me: bool = False) -> str:
    """Create a signed JWT refresh token.

    Args:
        subject: The username (sub claim)
        remember_me: If True, uses extended expiry (30 days vs 14)

    Returns:
        Encoded JWT string
    """
    now = datetime.now(timezone.utc)
    expire_days = settings.remember_me_days if remember_me else settings.jwt_refresh_token_expire_days

    payload: dict[str, Any] = {
        "sub": subject,
        "iat": now,
        "exp": now + timedelta(days=expire_days),
        "type": "refresh",
        "jti": uuid4().hex,
        "remember_me": remember_me,
    }
    return jwt.encode(payload, settings.app_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT payload.

    Raises AuthenticationError if token is invalid or expired.
    """
    try:
        return jwt.decode(token, settings.app_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Token has expired") from exc
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Invalid or expired token") from exc


def get_token_expiry(token: str) -> datetime | None:
    """Extract the expiry timestamp from a token without full validation."""
    try:
        payload = jwt.decode(
            token,
            settings.app_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"verify_exp": False},
        )
        exp = payload.get("exp")
        if exp:
            return datetime.fromtimestamp(exp, tz=timezone.utc)
        return None
    except jwt.PyJWTError:
        return None

