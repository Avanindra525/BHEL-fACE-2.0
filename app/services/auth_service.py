"""Authentication service with enterprise-grade security.

Features:
  - Registration with password complexity validation + password history
  - Login with brute-force protection (account lockout)
  - JWT access + refresh token management
  - "Remember Me" extended session support
  - Password change with history enforcement (no reuse of last 5)
  - Token refresh with rotation (old tokens revoked)
  - Session revocation (logout all sessions)
  - Comprehensive audit logging
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.core.config import settings
from app.core.exceptions import AuthenticationError, ConflictError, ValidationError
from app.core.logging import logger
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    validate_password_complexity,
    verify_password,
)
from app.models.audit_log import AuditLog
from app.models.login_log import LoginLog
from app.models.password_history import PasswordHistory
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.auth import LoginRequest, RegisterRequest


class AuthService:
    """Business logic for authentication and account lifecycle."""

    def __init__(self, user_repository: UserRepository) -> None:
        self.user_repository = user_repository

    # ─── Registration ────────────────────────────────────────────────────

    def register(
        self,
        payload: RegisterRequest,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        """Register a new user account with full validation.

        Enforces:
          - Username/email uniqueness
          - Password complexity rules
          - Password history (new users have none yet)
        """
        # Check uniqueness
        if self.user_repository.get_by_username(payload.username):
            raise ConflictError("Username already exists")
        if self.user_repository.get_by_email(payload.email):
            raise ConflictError("Email already exists")

        # Validate password complexity
        try:
            validate_password_complexity(payload.password)
        except ValidationError as exc:
            raise ValidationError(str(exc)) from exc

        # Create user
        hashed = hash_password(payload.password)
        user = User(
            username=payload.username,
            email=payload.email,
            full_name=payload.full_name,
            password_hash=hashed,
            staff_number=payload.staff_number,
            profile_completed="Y" if payload.profile_completed else "N",
            is_active="Y",
            face_registered="N",
            password_changed_at=datetime.utcnow(),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        self.user_repository.add(user)

        # Store initial password in history
        history = PasswordHistory(
            user_id=user.user_id,
            password_hash=hashed,
            created_at=datetime.utcnow(),
        )
        self.user_repository.session.add(history)
        self.user_repository.session.commit()

        # Generate tokens
        access_token = create_access_token(user.username)
        refresh_token = create_refresh_token(user.username)

        # Log registration
        logger.info("user_registered", extra={"username": user.username, "ip": ip_address})

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user": user,
        }

    # ─── Login with Brute-Force Protection ───────────────────────────────

    def login(
        self,
        payload: LoginRequest,
        ip_address: str | None = None,
        user_agent: str | None = None,
        remember_me: bool = False,
    ) -> dict[str, Any]:
        """Authenticate with username and password.

        Enforces:
          - Account lockout after N failed attempts
          - Password expiry check
          - Failed attempt tracking
        """
        user = self.user_repository.get_by_username(payload.username)
        if not user:
            # Log failed attempt for non-existent user
            logger.warning("login_failed_user_not_found", extra={"username": payload.username, "ip": ip_address})
            raise AuthenticationError("Invalid username or password")

        # Check account lockout
        if user.is_locked == "Y":
            self._log_login_failed(user, ip_address, user_agent, "Account is locked")
            raise AuthenticationError("Account is locked due to too many failed attempts. Try again later.")

        # Check if account is active
        if user.is_active != "Y":
            self._log_login_failed(user, ip_address, user_agent, "Account is inactive")
            raise AuthenticationError("Account is inactive")

        # Check password
        if not verify_password(payload.password, user.password_hash):
            # Increment failed attempts
            user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
            user.updated_at = datetime.utcnow()

            # Lock account if threshold exceeded
            if user.failed_login_attempts >= settings.max_failed_login_attempts:
                user.is_locked = "Y"

            self.user_repository.update(user)
            self._log_login_failed(user, ip_address, user_agent, "Invalid password")
            logger.warning(
                "login_failed_wrong_password",
                extra={
                    "username": payload.username,
                    "attempts": user.failed_login_attempts,
                    "ip": ip_address,
                },
            )
            raise AuthenticationError("Invalid username or password")

        # Check password expiry
        from app.core.security import check_password_expired
        if check_password_expired(user.password_changed_at):
            self._log_login_failed(user, ip_address, user_agent, "Password expired")
            raise AuthenticationError("Password has expired. Please reset your password.")

        # Success — reset failed attempts
        user.failed_login_attempts = 0
        user.is_locked = "N"
        user.last_login_at = datetime.utcnow()
        user.updated_at = datetime.utcnow()
        self.user_repository.update(user)

        # Generate tokens
        access_token = create_access_token(user.username, remember_me=remember_me)
        refresh_token = create_refresh_token(user.username, remember_me=remember_me)

        # Store refresh token in Oracle
        expires_at = datetime.utcnow() + timedelta(
            days=settings.remember_me_days if remember_me else settings.jwt_refresh_token_expire_days,
        )
        stored_token = RefreshToken(
            user_id=user.user_id,
            token=refresh_token,
            expires_at=expires_at,
            revoked="N",
            created_at=datetime.utcnow(),
        )
        self.user_repository.session.add(stored_token)
        self.user_repository.session.commit()

        # Log success
        logger.info("user_login", extra={"username": user.username, "ip": ip_address, "method": "password"})

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "remember_me": remember_me,
            "user": user,
        }

    # ─── Token Refresh with Rotation ─────────────────────────────────────

    def refresh_tokens(self, refresh_token_str: str) -> dict[str, Any]:
        """Refresh an access token using a valid refresh token.

        Implements token rotation:
          - Old refresh token is revoked
          - New access + refresh tokens are issued
        """
        from app.core.security import decode_token

        try:
            payload = decode_token(refresh_token_str)
        except AuthenticationError as exc:
            raise AuthenticationError("Invalid or expired refresh token") from exc

        if payload.get("type") != "refresh":
            raise AuthenticationError("Invalid token type")

        username = payload.get("sub")
        if not username:
            raise AuthenticationError("Invalid refresh token")

        user = self.user_repository.get_by_username(username)
        if not user or user.is_active != "Y":
            raise AuthenticationError("User account is inactive")

        if user.is_locked == "Y":
            raise AuthenticationError("User account is locked")

        # Revoke old token (rotation)
        self.user_repository.session.query(RefreshToken).filter(
            RefreshToken.token == refresh_token_str,
            RefreshToken.revoked == "N",
        ).update({"revoked": "Y"})
        self.user_repository.session.commit()

        remember_me = payload.get("remember_me", False)

        # Issue new tokens
        new_access = create_access_token(username, remember_me=remember_me)
        new_refresh = create_refresh_token(username, remember_me=remember_me)

        # Store new refresh token
        expires_at = datetime.utcnow() + timedelta(
            days=settings.remember_me_days if remember_me else settings.jwt_refresh_token_expire_days,
        )
        stored_token = RefreshToken(
            user_id=user.user_id,
            token=new_refresh,
            expires_at=expires_at,
            revoked="N",
            created_at=datetime.utcnow(),
        )
        self.user_repository.session.add(stored_token)
        self.user_repository.session.commit()

        return {
            "access_token": new_access,
            "refresh_token": new_refresh,
            "token_type": "bearer",
            "remember_me": remember_me,
        }

    # ─── Logout (Revoke Sessions) ────────────────────────────────────────

    def revoke_all_sessions(self, user: User) -> None:
        """Revoke all refresh tokens for a user (full logout)."""
        self.user_repository.session.query(RefreshToken).filter(
            RefreshToken.user_id == user.user_id,
            RefreshToken.revoked == "N",
        ).update({"revoked": "Y"})
        self.user_repository.session.commit()

        logger.info("all_sessions_revoked", extra={"username": user.username})

    def revoke_token(self, refresh_token_str: str) -> None:
        """Revoke a specific refresh token."""
        self.user_repository.session.query(RefreshToken).filter(
            RefreshToken.token == refresh_token_str,
        ).update({"revoked": "Y"})
        self.user_repository.session.commit()

    # ─── Password Change ─────────────────────────────────────────────────

    def change_password(
        self,
        user: User,
        current_password: str,
        new_password: str,
    ) -> None:
        """Change user password with history enforcement.

        Enforces:
          - Current password verification
          - Password complexity rules
          - Cannot reuse last N passwords
        """
        # Verify current password
        if not verify_password(current_password, user.password_hash):
            raise ValidationError("Current password is incorrect")

        # Validate new password complexity
        try:
            validate_password_complexity(new_password)
        except ValidationError as exc:
            raise ValidationError(str(exc)) from exc

        # Check password history (last N passwords)
        recent = (
            self.user_repository.session.query(PasswordHistory)
            .filter(PasswordHistory.user_id == user.user_id)
            .order_by(PasswordHistory.created_at.desc())
            .limit(settings.password_history_count)
            .all()
        )

        for entry in recent:
            if verify_password(new_password, entry.password_hash):
                raise ValidationError(
                    f"You cannot reuse a recent password. Choose a different one.",
                )

        # Store current password in history
        history_entry = PasswordHistory(
            user_id=user.user_id,
            password_hash=user.password_hash,
            created_at=datetime.utcnow(),
        )
        self.user_repository.session.add(history_entry)

        # Update to new password
        user.password_hash = hash_password(new_password)
        user.password_changed_at = datetime.utcnow()
        user.updated_at = datetime.utcnow()
        self.user_repository.update(user)

        # Audit log
        audit = AuditLog(
            user_id=user.user_id,
            action="password_changed",
            details="Password changed successfully",
        )
        self.user_repository.session.add(audit)
        self.user_repository.session.commit()

        logger.info("password_changed", extra={"username": user.username})

    # ─── Password Reset (Admin) ─────────────────────────────────────────

    def admin_reset_password(self, admin_user: User, target_user: User, new_password: str) -> None:
        """Admin-forced password reset.

        Skips current password verification but enforces complexity.
        """
        try:
            validate_password_complexity(new_password)
        except ValidationError as exc:
            raise ValidationError(str(exc)) from exc

        target_user.password_hash = hash_password(new_password)
        target_user.password_changed_at = datetime.utcnow()
        target_user.updated_at = datetime.utcnow()
        target_user.is_locked = "N"  # Unlock when reset
        self.user_repository.update(target_user)

        # Audit
        audit = AuditLog(
            user_id=admin_user.user_id,
            action="password_reset",
            details=f"Admin reset password for user: {target_user.username}",
        )
        self.user_repository.session.add(audit)
        self.user_repository.session.commit()

        logger.info(
            "password_reset_by_admin",
            extra={"admin": admin_user.username, "target": target_user.username},
        )

    # ─── Private Helpers ─────────────────────────────────────────────────

    def _log_login_failed(
        self,
        user: User,
        ip_address: str | None,
        user_agent: str | None,
        reason: str,
    ) -> None:
        """Log a failed login attempt to Oracle."""
        log = LoginLog(
            user_id=user.user_id,
            login_method="password",
            success="N",
            ip_address=ip_address,
            user_agent=user_agent,
            failure_reason=reason,
            login_time=datetime.utcnow(),
        )
        self.user_repository.session.add(log)
        self.user_repository.session.commit()

