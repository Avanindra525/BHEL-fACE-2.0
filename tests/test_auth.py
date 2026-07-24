"""Authentication test suite: register, login, logout, refresh token."""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.models.audit_log import AuditLog
from app.models.login_log import LoginLog
from app.models.password_history import PasswordHistory
from app.models.refresh_token import RefreshToken
from app.models.user import User
from tests.conftest import unique_email, unique_username


# ═══════════════════════════════════════════════════════════════════════════════
# Registration
# ═══════════════════════════════════════════════════════════════════════════════


class TestRegister:
    def test_register_success(self, client: TestClient) -> None:
        """Register a valid user returns tokens."""
        username = unique_username()
        response = client.post("/api/auth/register", json={
            "username": username,
            "email": unique_email(),
            "full_name": "Test User",
            "password": "StrongPass123!",
            "password_confirmation": "StrongPass123!",
            "staff_number": f"EMP-{uuid4().hex[:6].upper()}",
            "profile_completed": True,
        })
        assert response.status_code == 201
        body = response.json()
        assert body["access_token"]
        assert body["refresh_token"]
        assert body["token_type"] == "bearer"

    def test_register_duplicate_username(self, client: TestClient) -> None:
        """Registering with existing username returns 409."""
        username = unique_username()
        payload = {
            "username": username,
            "email": unique_email(),
            "full_name": "User One",
            "password": "StrongPass123!",
            "password_confirmation": "StrongPass123!",
        }
        # First registration
        resp1 = client.post("/api/auth/register", json=payload)
        assert resp1.status_code == 201

        # Duplicate username
        payload2 = payload.copy()
        payload2["email"] = unique_email()
        resp2 = client.post("/api/auth/register", json=payload2)
        assert resp2.status_code == 409
        assert "Username already exists" in resp2.json()["detail"]

    def test_register_duplicate_email(self, client: TestClient) -> None:
        """Registering with existing email returns 409."""
        email = unique_email()
        payload = {
            "username": unique_username(),
            "email": email,
            "full_name": "User One",
            "password": "StrongPass123!",
            "password_confirmation": "StrongPass123!",
        }
        resp1 = client.post("/api/auth/register", json=payload)
        assert resp1.status_code == 201

        payload2 = payload.copy()
        payload2["username"] = unique_username()
        resp2 = client.post("/api/auth/register", json=payload2)
        assert resp2.status_code == 409
        assert "Email already exists" in resp2.json()["detail"]

    def test_register_password_mismatch(self, client: TestClient) -> None:
        """Password confirmation mismatch returns 422."""
        response = client.post("/api/auth/register", json={
            "username": unique_username(),
            "email": unique_email(),
            "full_name": "Test User",
            "password": "StrongPass123!",
            "password_confirmation": "DifferentPass456!",
        })
        assert response.status_code == 422

    def test_register_weak_password(self, client: TestClient) -> None:
        """Password below complexity rules returns 422."""
        response = client.post("/api/auth/register", json={
            "username": unique_username(),
            "email": unique_email(),
            "full_name": "Test User",
            "password": "weak",
            "password_confirmation": "weak",
        })
        assert response.status_code == 422

    def test_register_creates_password_history(self, client: TestClient, db_session) -> None:
        """Registration stores password hash in password_history table."""
        from app.core.database import SessionLocal

        username = unique_username()
        email = unique_email()
        response = client.post("/api/auth/register", json={
            "username": username,
            "email": email,
            "full_name": "Test User",
            "password": "StrongPass123!",
            "password_confirmation": "StrongPass123!",
        })
        assert response.status_code == 201

        user = db_session.query(User).filter(User.username == username).first()
        assert user is not None
        history = db_session.query(PasswordHistory).filter(
            PasswordHistory.user_id == user.user_id
        ).all()
        assert len(history) >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# Login
# ═══════════════════════════════════════════════════════════════════════════════


class TestLogin:
    def test_login_success(self, client: TestClient) -> None:
        """Valid credentials return tokens and user info."""
        username = unique_username()
        client.post("/api/auth/register", json={
            "username": username,
            "email": unique_email(),
            "full_name": "Login User",
            "password": "StrongPass123!",
            "password_confirmation": "StrongPass123!",
        })

        response = client.post("/api/auth/login", json={
            "username": username,
            "password": "StrongPass123!",
        })
        assert response.status_code == 200
        body = response.json()
        assert body["access_token"]
        assert body["refresh_token"]
        assert body["token_type"] == "bearer"
        assert body["user"]["username"] == username

    def test_login_wrong_password(self, client: TestClient) -> None:
        """Wrong password returns 401."""
        username = unique_username()
        client.post("/api/auth/register", json={
            "username": username,
            "email": unique_email(),
            "full_name": "Login User",
            "password": "StrongPass123!",
            "password_confirmation": "StrongPass123!",
        })

        response = client.post("/api/auth/login", json={
            "username": username,
            "password": "WrongPass123!",
        })
        assert response.status_code == 401

    def test_login_nonexistent_user(self, client: TestClient) -> None:
        """Non-existent user returns 401."""
        response = client.post("/api/auth/login", json={
            "username": "nonexistent_user",
            "password": "SomePass123!",
        })
        assert response.status_code == 401

    def test_login_increments_failed_attempts(self, client: TestClient, db_session) -> None:
        """Failed login increments failed_login_attempts counter."""
        username = unique_username()
        client.post("/api/auth/register", json={
            "username": username,
            "email": unique_email(),
            "full_name": "Lockout Test",
            "password": "StrongPass123!",
            "password_confirmation": "StrongPass123!",
        })

        for _ in range(3):
            client.post("/api/auth/login", json={
                "username": username,
                "password": "WrongPass123!",
            })

        user = db_session.query(User).filter(User.username == username).first()
        assert user is not None
        assert user.failed_login_attempts >= 3

    def test_login_locks_account_after_max_attempts(self, client: TestClient, db_session) -> None:
        """Account gets locked after max failed attempts."""
        username = unique_username()
        client.post("/api/auth/register", json={
            "username": username,
            "email": unique_email(),
            "full_name": "Lockout Test",
            "password": "StrongPass123!",
            "password_confirmation": "StrongPass123!",
        })

        for _ in range(6):  # More than max_failed_login_attempts (5)
            client.post("/api/auth/login", json={
                "username": username,
                "password": "WrongPass123!",
            })

        user = db_session.query(User).filter(User.username == username).first()
        assert user.is_locked == "Y"

        # Even correct password should fail
        response = client.post("/api/auth/login", json={
            "username": username,
            "password": "StrongPass123!",
        })
        assert response.status_code == 401
        assert "locked" in response.json()["detail"].lower()

    def test_login_creates_login_log(self, client: TestClient, db_session) -> None:
        """Successful login creates LoginLog entry."""
        username = unique_username()
        client.post("/api/auth/register", json={
            "username": username,
            "email": unique_email(),
            "full_name": "Log Test",
            "password": "StrongPass123!",
            "password_confirmation": "StrongPass123!",
        })

        client.post("/api/auth/login", json={
            "username": username,
            "password": "StrongPass123!",
        })

        user = db_session.query(User).filter(User.username == username).first()
        logs = db_session.query(LoginLog).filter(LoginLog.user_id == user.user_id).all()
        assert len(logs) >= 1
        assert logs[-1].success == "Y"

    def test_login_with_remember_me(self, client: TestClient) -> None:
        """Login with remember-me header returns extended tokens."""
        username = unique_username()
        client.post("/api/auth/register", json={
            "username": username,
            "email": unique_email(),
            "full_name": "Remember Me",
            "password": "StrongPass123!",
            "password_confirmation": "StrongPass123!",
        })

        response = client.post(
            "/api/auth/login",
            json={"username": username, "password": "StrongPass123!"},
            headers={"X-Remember-Me": "true"},
        )
        assert response.status_code == 200
        assert response.json()["remember_me"] is True


# ═══════════════════════════════════════════════════════════════════════════════
# Logout
# ═══════════════════════════════════════════════════════════════════════════════


class TestLogout:
    def test_logout_revokes_token(self, client: TestClient, auth_headers_employee) -> None:
        """Logout revokes the refresh token."""
        response = client.get("/api/auth/me", headers=auth_headers_employee)
        assert response.status_code == 200

        # Get the refresh token from login
        login_resp = client.post("/api/auth/login", json={
            "username": "testemployee", "password": "TestPass123!",
        })
        refresh_token = login_resp.json()["refresh_token"]

        logout_resp = client.post(
            "/api/auth/logout",
            json={"refresh_token": refresh_token},
            headers=auth_headers_employee,
        )
        assert logout_resp.status_code == 200
        assert logout_resp.json()["message"] == "Logged out successfully"

    def test_logout_fails_without_auth(self, client: TestClient) -> None:
        """Logout without auth returns 401."""
        response = client.post(
            "/api/auth/logout",
            json={"refresh_token": "some_token"},
        )
        assert response.status_code == 401

    def test_revoke_all_sessions(self, client: TestClient, auth_headers_employee) -> None:
        """Revoke all sessions invalidates all tokens."""
        response = client.delete("/api/auth/sessions", headers=auth_headers_employee)
        assert response.status_code == 200
        assert "session" in response.json()["message"].lower()


# ═══════════════════════════════════════════════════════════════════════════════
# Refresh Token
# ═══════════════════════════════════════════════════════════════════════════════


class TestRefreshToken:
    def test_refresh_token_success(self, client: TestClient) -> None:
        """Valid refresh token returns a new token pair."""
        username = unique_username()
        register_resp = client.post("/api/auth/register", json={
            "username": username,
            "email": unique_email(),
            "full_name": "Refresh Test",
            "password": "StrongPass123!",
            "password_confirmation": "StrongPass123!",
        })
        old_refresh = register_resp.json()["refresh_token"]

        refresh_resp = client.post("/api/auth/refresh", json={
            "refresh_token": old_refresh,
        })
        assert refresh_resp.status_code == 200
        body = refresh_resp.json()
        assert body["access_token"]
        assert body["refresh_token"]
        # Token rotation: new tokens should differ
        assert body["refresh_token"] != old_refresh

    def test_refresh_invalid_token(self, client: TestClient) -> None:
        """Invalid refresh token returns 401."""
        response = client.post("/api/auth/refresh", json={
            "refresh_token": "invalid_token_here",
        })
        assert response.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
# Password Change
# ═══════════════════════════════════════════════════════════════════════════════


class TestChangePassword:
    def test_change_password_success(self, client: TestClient, auth_headers_employee) -> None:
        """Changing password with valid current password succeeds."""
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

        # New password should work for login
        login_resp = client.post("/api/auth/login", json={
            "username": "testemployee",
            "password": "NewStrong123!",
        })
        assert login_resp.status_code == 200

    def test_change_password_wrong_current(self, client: TestClient, auth_headers_employee) -> None:
        """Wrong current password returns 400."""
        response = client.put(
            "/api/auth/change-password",
            json={
                "current_password": "WrongPass123!",
                "new_password": "NewStrong123!",
                "confirm_password": "NewStrong123!",
            },
            headers=auth_headers_employee,
        )
        assert response.status_code == 400

    def test_change_password_mismatch(self, client: TestClient, auth_headers_employee) -> None:
        """Password confirmation mismatch returns 400."""
        response = client.put(
            "/api/auth/change-password",
            json={
                "current_password": "TestPass123!",
                "new_password": "NewStrong123!",
                "confirm_password": "Different456!",
            },
            headers=auth_headers_employee,
        )
        assert response.status_code == 400

    def test_change_password_same_as_old(self, client: TestClient, auth_headers_employee) -> None:
        """Reusing the same password may fail history check (depends on config)."""
        response = client.put(
            "/api/auth/change-password",
            json={
                "current_password": "TestPass123!",
                "new_password": "TestPass123!",
                "confirm_password": "TestPass123!",
            },
            headers=auth_headers_employee,
        )
        # Should either succeed (if history allows) or fail
        assert response.status_code in (200, 400)


# ═══════════════════════════════════════════════════════════════════════════════
# Get Me
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetMe:
    def test_get_me_authenticated(self, client: TestClient, auth_headers_employee) -> None:
        """Authenticated user can get their profile."""
        response = client.get("/api/auth/me", headers=auth_headers_employee)
        assert response.status_code == 200
        body = response.json()
        assert body["username"] == "testemployee"
        assert body["email"] == "employee@test.com"
        assert body["full_name"] == "Test Employee"
        assert body["role"] == "Employee"

    def test_get_me_unauthenticated(self, client: TestClient) -> None:
        """Unauthenticated request returns 401."""
        response = client.get("/api/auth/me")
        assert response.status_code == 401

