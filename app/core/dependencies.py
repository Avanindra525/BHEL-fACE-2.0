"""Shared FastAPI dependencies for authentication, RBAC, and permissions.

Provides:
  - get_current_user: Resolve authenticated user from JWT
  - require_roles: Role-based access control (Admin, HR, Manager, Employee)
  - require_permission: Permission-based access control
  - Idle session timeout enforcement
  - Audit logging helper
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import AuthenticationError, AuthorizationError
from app.core.security import decode_token
from app.models.audit_log import AuditLog
from app.models.user import User

# ─── RBAC Role Hierarchy ────────────────────────────────────────────────────
# Higher number = more privileges

ROLE_HIERARCHY: dict[str, int] = {
    "Super Admin": 100,
    "Admin": 80,
    "HR": 60,
    "Manager": 40,
    "Employee": 20,
    "Guest": 10,
}

# ─── Standard Permissions ──────────────────────────────────────────────────

PERMISSION_NAMES = {
    "employee:read": "View employee details",
    "employee:create": "Create new employees",
    "employee:update": "Update employee details",
    "employee:delete": "Delete employees",
    "employee:status": "Enable/disable employee accounts",
    "department:read": "View departments",
    "department:create": "Create departments",
    "department:update": "Update departments",
    "department:delete": "Delete departments",
    "role:read": "View roles",
    "role:create": "Create roles",
    "role:update": "Update roles",
    "role:delete": "Delete roles",
    "role:assign": "Assign roles to users",
    "permission:read": "View permissions",
    "permission:assign": "Assign permissions to roles",
    "face:register": "Register face biometrics",
    "face:login": "Login with face recognition",
    "face:read": "View face registration data",
    "audit:read": "View audit logs",
    "settings:read": "View system settings",
    "settings:update": "Update system settings",
    "dashboard:read": "View dashboard",
    "statistics:read": "View statistics",
    "admin:full": "Full administrative access",
}

# Default role-permission mapping
DEFAULT_ROLE_PERMISSIONS: dict[str, list[str]] = {
    "Super Admin": list(PERMISSION_NAMES.keys()),
    "Admin": [
        "employee:read", "employee:create", "employee:update", "employee:delete", "employee:status",
        "department:read", "department:create", "department:update", "department:delete",
        "role:read", "role:create", "role:update", "role:delete", "role:assign",
        "permission:read", "permission:assign",
        "face:register", "face:login", "face:read",
        "audit:read",
        "settings:read", "settings:update",
        "dashboard:read", "statistics:read",
    ],
    "HR": [
        "employee:read", "employee:create", "employee:update",
        "department:read",
        "role:read",
        "permission:read",
        "face:register", "face:login", "face:read",
        "audit:read",
        "dashboard:read", "statistics:read",
    ],
    "Manager": [
        "employee:read",
        "department:read",
        "role:read",
        "face:register", "face:login",
        "dashboard:read", "statistics:read",
    ],
    "Employee": [
        "face:register", "face:login",
        "dashboard:read",
    ],
}


def get_current_user(
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the current authenticated user from the bearer token.

    Enforces:
      - Token validity (signature, expiry)
      - User exists and is active
      - Idle session timeout
    """
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    try:
        payload = decode_token(token)
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    username = payload.get("sub")
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if user.is_active != "Y":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User account is inactive")
    if user.is_locked == "Y":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User account is locked")

    # Enforce password expiry
    from app.core.security import check_password_expired
    if check_password_expired(user.password_changed_at):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Password has expired. Please reset your password.",
        )

    return user


def require_roles(*allowed_roles: str):
    """Dependency factory enforcing required roles.

    Supports hierarchical roles — if the user has a role at or above
    the minimum required level, access is granted.

    Example:
        @router.get("/employees")
        def list(admin=Depends(require_roles("Admin", "HR"))): ...
    """

    def _dependency(current_user: Annotated[User, Depends(get_current_user)]) -> User:
        if not current_user.role:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

        user_role_level = ROLE_HIERARCHY.get(current_user.role.name, 0)
        if user_role_level == 100:  # Super Admin always passes
            return current_user

        for role in allowed_roles:
            required_level = ROLE_HIERARCHY.get(role, 0)
            if user_role_level >= required_level:
                return current_user

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied. Required roles: {', '.join(allowed_roles)}",
        )

    return _dependency


def require_permission(permission_name: str):
    """Dependency factory enforcing a specific permission.

    Checks if the user's role has the required permission assigned.
    Super Admin bypasses all permission checks.

    Example:
        @router.post("/employees")
        def create(admin=Depends(require_permission("employee:create"))): ...
    """

    def _dependency(current_user: Annotated[User, Depends(get_current_user)]) -> User:
        if not current_user.role:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

        # Super Admin has all permissions
        if current_user.role.name == "Super Admin":
            return current_user

        # Check if role has the permission
        if any(p.name == permission_name for p in current_user.role.permissions):
            return current_user

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Missing permission: {permission_name}",
        )

    return _dependency


def require_role_or_permission(allowed_roles: list[str] | None = None, permission: str | None = None):
    """Combined dependency: requires at least one of the given roles OR permission.

    Useful for endpoints where HR and above should have access, OR
    the specific permission should grant access regardless of role.
    """

    def _dependency(current_user: Annotated[User, Depends(get_current_user)]) -> User:
        if not current_user.role:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

        # Super Admin always passes
        if current_user.role.name == "Super Admin":
            return current_user

        # Check roles
        if allowed_roles:
            user_level = ROLE_HIERARCHY.get(current_user.role.name, 0)
            for role in allowed_roles:
                if user_level >= ROLE_HIERARCHY.get(role, 0):
                    return current_user

        # Check permission
        if permission:
            if any(p.name == permission for p in current_user.role.permissions):
                return current_user

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    return _dependency


# ─── Audit Helper ──────────────────────────────────────────────────────────


def create_audit_log(
    db: Session,
    user_id: int | None,
    action: str,
    details: str | None = None,
) -> AuditLog:
    """Create an audit log entry and commit.

    Centralized to ensure all audit events are captured consistently.
    """
    log = AuditLog(user_id=user_id, action=action, details=details)
    db.add(log)
    db.commit()
    return log


# ─── Session Timeout Helper ───────────────────────────────────────────────


def check_session_expiry(token_payload: dict[str, Any]) -> None:
    """Check if the session has exceeded the idle timeout.

    This is in addition to JWT expiry — it enforces shorter idle timeout
    even if the JWT hasn't expired yet.
    """
    iat = token_payload.get("iat")
    if not iat:
        return

    issued_at = datetime.fromtimestamp(iat)
    elapsed_minutes = (datetime.utcnow() - issued_at).total_seconds() / 60

    if elapsed_minutes > settings.session_timeout_minutes:
        raise AuthenticationError("Session has expired due to inactivity")

