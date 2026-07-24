"""Authentication API routes with enterprise security.

Endpoints:
  POST /api/auth/register      — Register with password complexity + history
  POST /api/auth/login         — Login with brute-force protection + lockout
  POST /api/auth/refresh       — Token refresh with rotation
  POST /api/auth/logout        — Logout (revoke specific refresh token)
  DELETE /api/auth/sessions    — Revoke all sessions
  GET  /api/auth/me            — Current user info
  PUT  /api/auth/change-password  — Change password with history check
  POST /api/auth/reset-password   — Admin password reset
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_roles
from app.core.exceptions import AuthenticationError, ConflictError, ValidationError
from app.core.logging import logger
from app.core.security import create_access_token, decode_token
from app.models.audit_log import AuditLog
from app.models.login_log import LoginLog
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.services.auth_service import AuthService
from app.repositories.user_repository import UserRepository

router = APIRouter()


# ─── Request Schemas ──────────────────────────────────────────────────────


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8)
    confirm_password: str = Field(min_length=8)


class ResetPasswordRequest(BaseModel):
    user_id: int
    new_password: str = Field(min_length=12)


# ─── Helpers ──────────────────────────────────────────────────────────────


def get_auth_service(db: Session = Depends(get_db)) -> AuthService:
    return AuthService(UserRepository(db))


def get_client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def _audit(db: Session, user_id: int | None, action: str, details: str | None = None) -> None:
    """Helper to write audit logs to Oracle."""
    log = AuditLog(user_id=user_id, action=action, details=details)
    db.add(log)
    db.commit()


def _log_login(db: Session, user_id: int, method: str, success: bool, ip: str | None, ua: str | None, reason: str | None = None) -> None:
    """Helper to write login logs to Oracle."""
    log = LoginLog(
        user_id=user_id,
        login_method=method,
        success="Y" if success else "N",
        ip_address=ip,
        user_agent=ua,
        failure_reason=reason,
        login_time=datetime.utcnow(),
    )
    db.add(log)
    db.commit()


# ─── Endpoints ────────────────────────────────────────────────────────────


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    request: Request,
    db: Session = Depends(get_db),
    service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    """Register a new user account.

    Enforces password complexity rules and stores password history.
    """
    try:
        result = service.register(
            payload,
            ip_address=get_client_ip(request),
            user_agent=request.headers.get("User-Agent"),
        )
    except ConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    # Audit
    _audit(db, result["user"].user_id, "user_registered", f"User registered: {payload.username}")

    return TokenResponse(access_token=result["access_token"], refresh_token=result["refresh_token"])


@router.post("/login", response_model=dict[str, Any])
def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
    service: AuthService = Depends(get_auth_service),
) -> dict[str, Any]:
    try:
        result = service.login(
            payload,
            ip_address=get_client_ip(request),
            user_agent=request.headers.get("User-Agent"),
            remember_me=False,
        )

        user = result["user"]

        return {
            "access_token": result["access_token"],
            "refresh_token": result["refresh_token"],
            "token_type": "bearer",
            "user": {
                "user_id": user.user_id,
                "username": user.username,
            },
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(
    payload: RefreshRequest,
    db: Session = Depends(get_db),
    service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    """Refresh an access token using a valid refresh token.

    Implements token rotation — the old refresh token is revoked
    and a new pair is issued. This prevents replay attacks.
    """
    try:
        result = service.refresh_tokens(payload.refresh_token)
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    return TokenResponse(access_token=result["access_token"], refresh_token=result["refresh_token"])


@router.post("/logout")
def logout(
    payload: LogoutRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Logout by revoking the provided refresh token."""
    try:
        # Revoke the specific token
        db.query(RefreshToken).filter(
            RefreshToken.token == payload.refresh_token,
            RefreshToken.user_id == current_user.user_id,
        ).update({"revoked": "Y"})
        db.commit()

        _audit(db, current_user.user_id, "user_logout", "User logged out")

    except Exception as exc:
        logger.warning("logout_error", extra={"error": str(exc)})

    return {"message": "Logged out successfully"}


@router.delete("/sessions")
def revoke_sessions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Revoke ALL refresh tokens for the current user.

    Use this for "Logout from all devices" functionality.
    """
    count = db.query(RefreshToken).filter(
        RefreshToken.user_id == current_user.user_id,
        RefreshToken.revoked == "N",
    ).update({"revoked": "Y"})
    db.commit()

    _audit(db, current_user.user_id, "sessions_revoked", f"Revoked {count} session(s)")

    return {"message": f"All {count} session(s) revoked"}


@router.get("/me")
def get_me(
    current_user: User = Depends(get_current_user),
) -> dict[str, object]:
    """Return the current authenticated user's details."""
    return {
        "user_id": current_user.user_id,
        "username": current_user.username,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "staff_number": current_user.staff_number,
        "role": current_user.role.name if current_user.role else None,
        "role_id": current_user.role_id,
        "department": current_user.department.name if current_user.department else None,
        "department_id": current_user.department_id,
        "is_active": current_user.is_active == "Y",
        "is_locked": current_user.is_locked == "Y",
        "face_registered": current_user.face_registered == "Y",
        "profile_completed": current_user.profile_completed == "Y",
        "bio": current_user.bio,
        "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
    }


@router.put("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    service: AuthService = Depends(get_auth_service),
) -> dict[str, str]:
    """Change the current user's password.

    Enforces:
      - Current password verification
      - Password complexity rules
      - Cannot reuse last 5 passwords (stored in password_history)
    """
    if payload.new_password != payload.confirm_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Passwords do not match")

    try:
        service.change_password(current_user, payload.current_password, payload.new_password)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    _audit(db, current_user.user_id, "password_changed", "User changed their password")

    return {"message": "Password changed successfully"}


@router.post("/reset-password")
def reset_password(
    payload: ResetPasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "Super Admin")),
    service: AuthService = Depends(get_auth_service),
) -> dict[str, str]:
    """Admin-only: Reset another user's password.

    This bypasses current password check but still enforces complexity.
    Also unlocks the account if it was locked.
    """
    target_user = db.query(User).filter(User.user_id == payload.user_id).first()
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    try:
        service.admin_reset_password(current_user, target_user, payload.new_password)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    _audit(
        db,
        current_user.user_id,
        "password_reset",
        f"Admin {current_user.username} reset password for {target_user.username}",
    )

    return {"message": f"Password reset for {target_user.username} completed"}


@router.get("/active-sessions")
def list_active_sessions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    """List all active refresh tokens for the current user."""
    tokens = (
        db.query(RefreshToken)
        .filter(
            RefreshToken.user_id == current_user.user_id,
            RefreshToken.revoked == "N",
        )
        .order_by(RefreshToken.created_at.desc())
        .all()
    )

    return [
        {
            "token_id": t.refresh_token_id,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "expires_at": t.expires_at.isoformat() if t.expires_at else None,
        }
        for t in tokens
    ]

