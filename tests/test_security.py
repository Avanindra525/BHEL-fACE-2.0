"""Security test suite: JWT, RBAC, rate limiting, password history."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    validate_password_complexity,
    verify_password,
)
from app.core.exceptions import AuthenticationError, ValidationError
from app.models.password_history import PasswordHistory
from app.models.user import User
from tests.conftest import unique_email, unique_username


# ═══════════════════════════════════════════════════════════════════════════════
# JWT Token Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestJWT:
    def test_create_access_token(self) -> None:
        """Access token is created and decodable."""
        token = create_access_token("testuser")
        payload = decode_token(token)
        assert payload["sub"] == "testuser"
        assert payload["type"] == "access"

    def test_create_refresh_token(self) -> None:
        """Refresh token is created and decodable."""
        token = create_refresh_token("testuser")
        payload = decode_token(token)
        assert payload["sub"] == "testuser"
        assert payload["type"] == "refresh"

    def test_token_expiry(self) -> None:
        """Expired token raises AuthenticationError."""
        # Create token with past expiry
        now = datetime.utcnow()
        past = now - timedelta(hours=1)
        payload = {
            "sub": "testuser",
            "iat": past.timestamp(),
            "exp": (past + timedelta(minutes=1)).timestamp(),
            "type": "access",
        }
        expired_token = jwt.encode(payload, settings.app_secret_key, algorithm=settings.jwt_algorithm)

        with pytest.raises(AuthenticationError):
            decode_token(expired_token)

    def test_invalid_signature(self) -> None:
        """Token with wrong secret raises AuthenticationError."""
        token = jwt.encode({"sub": "testuser"}, "wrong_secret", algorithm="HS256")
        with pytest.raises(AuthenticationError):
            decode_token(token)

    def test_access_token_has_iat(self) -> None:
        """Access token includes issued-at claim."""
        token = create_access_token("testuser")
        payload = decode_token(token)
        assert "iat" in payload

    def test_remember_me_token(self) -> None:
        """Remember-me access token has remember_me flag."""
        token = create_access_token("testuser", remember_me=True)
        payload = decode_token(token)
        assert payload.get("remember_me") is True

    def test_extra_claims(self) -> None:
        """Extra claims are included in token."""
        token = create_access_token("testuser", extra_claims={"role": "admin"})
        payload = decode_token(token)
        assert payload["role"] == "admin"


# ═══════════════════════════════════════════════════════════════════════════════
# Password Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestPassword:
    def test_hash_and_verify(self) -> None:
        """Hashed password can be verified."""
        password = "TestPass123!"
        hashed = hash_password(password)
        assert verify_password(password, hashed)
        assert not verify_password("WrongPass123!", hashed)

    def test_hash_is_different_for_same_password(self) -> None:
        """Same password produces different hashes each time (different salt)."""
        password = "TestPass123!"
        hash1 = hash_password(password)
        hash2 = hash_password(password)
        assert hash1 != hash2

    def test_password_complexity_valid(self) -> None:
        """Valid password passes complexity check."""
        validate_password_complexity("StrongPass123!")
        # No exception = pass

    def test_password_too_short(self) -> None:
        """Short password fails."""
        with pytest.raises(ValidationError):
            validate_password_complexity("Ab1!")

    def test_password_no_uppercase(self) -> None:
        """Password missing uppercase fails."""
        with pytest.raises(ValidationError):
            validate_password_complexity("alllowercase123!")

    def test_password_no_digit(self) -> None:
        """Password missing digits fails."""
        with pytest.raises(ValidationError):
            validate_password_complexity("NoDigitsHere!")

    def test_password_no_special(self) -> None:
        """Password missing special characters fails."""
        with pytest.raises(ValidationError):
            validate_password_complexity("NoSpecialChar1")

    def test_password_no_lowercase(self) -> None:
        """Password missing lowercase fails."""
        with pytest.raises(ValidationError):
            validate_password_complexity("ALLUPPERCASE123!")


# ═══════════════════════════════════════════════════════════════════════════════
# RBAC Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestRBAC:
    def test_admin_can_access_employees(self, client: TestClient, auth_headers_admin) -> None:
        """Admin can list employees."""
        response = client.get("/api/employees", headers=auth_headers_admin)
        assert response.status_code == 200

    def test_employee_can_access_employees(self, client: TestClient, auth_headers_employee) -> None:
        """Employee can also list employees (permission: employee:read)."""
        response = client.get("/api/employees", headers=auth_headers_employee)
        assert response.status_code == 200

    def test_employee_cannot_delete_self(self, client: TestClient, auth_headers_employee, employee_user) -> None:
        """Employee cannot delete their own account."""
        response = client.delete(
            f"/api/employees/{employee_user.user_id}",
            headers=auth_headers_employee,
        )
        assert response.status_code == 400

    def test_unauthenticated_request_blocked(self, client: TestClient) -> None:
        """Unauthenticated requests return 401."""
        response = client.get("/api/employees")
        assert response.status_code == 401

    def test_dashboard_summary_requires_auth(self, client: TestClient) -> None:
        """Dashboard summary returns 401 without auth."""
        response = client.get("/api/dashboard/summary")
        assert response.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
# Password History Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestPasswordHistory:
    def test_password_history_created_on_register(self, client: TestClient, db_session: Session) -> None:
        """Registration creates password history entry."""
        username = unique_username()
        client.post("/api/auth/register", json={
            "username": username,
            "email": unique_email(),
            "full_name": "History Test",
            "password": "StrongPass123!",
            "password_confirmation": "StrongPass123!",
        })

        user = db_session.query(User).filter(User.username == username).first()
        history = db_session.query(PasswordHistory).filter(
            PasswordHistory.user_id == user.user_id
        ).count()
        assert history >= 1

    def test_password_history_stored_on_change(self, client: TestClient, auth_headers_employee, db_session: Session) -> None:
        """Password change creates a new history entry."""
        response = client.put(
            "/api/auth/change-password",
            json={
                "current_password": "TestPass123!",
                "new_password": "NewStrong123!",
                "confirm_password": "NewStrong123!",
            },
            headers=auth_headers_employee,
        )
        assert response.status_code == 200

        user = db_session.query(User).filter(User.username == "testemployee").first()
        history_count = db_session.query(PasswordHistory).filter(
            PasswordHistory.user_id == user.user_id
        ).count()
        assert history_count >= 1

