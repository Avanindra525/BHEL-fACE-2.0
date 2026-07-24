"""Shared pytest fixtures for FaceAuth Enterprise tests.

Provides:
  - In-memory SQLite test database (mimics Oracle schema)
  - FastAPI TestClient with overridden dependencies
  - Authenticated user fixtures (Employee, Admin, Super Admin)
  - Sample data fixtures (departments, roles, permissions)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Generator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.dependencies import get_current_user
from app.core.security import hash_password
from app.main import app
from app.middleware.rate_limit import _store
from app.models.audit_log import AuditLog
from app.models.department import Department
from app.models.face_sample import FaceSample
from app.models.login_log import LoginLog
from app.models.password_history import PasswordHistory
from app.models.permission import Permission
from app.models.refresh_token import RefreshToken
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.models.user import User

# ── In-memory SQLite test database ──────────────────────────────────────────

TEST_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    echo=False,
)

# Enable WAL mode and foreign keys for Oracle-like behaviour
@event.listens_for(TEST_ENGINE, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

TEST_SESSION_LOCAL = sessionmaker(autocommit=False, autoflush=False, bind=TEST_ENGINE)


def override_get_db() -> Generator[Session, None, None]:
    """Override FastAPI dependency with test database session."""
    db = TEST_SESSION_LOCAL()
    try:
        yield db
    finally:
        db.close()


def override_get_current_user_employee() -> User:
    """Override auth dependency — returns the test Employee user."""
    db = TEST_SESSION_LOCAL()
    user = db.query(User).filter(User.username == "testemployee").first()
    db.close()
    return user


def override_get_current_user_admin() -> User:
    """Override auth dependency — returns the test Admin user."""
    db = TEST_SESSION_LOCAL()
    user = db.query(User).filter(User.username == "testadmin").first()
    db.close()
    return user


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session", autouse=True)
def setup_database() -> Generator[None, None, None]:
    """Create all tables once per test session."""
    from app.core.config import settings
    # Disable rate limiting for tests
    original_rate_limit = settings.rate_limit_enabled
    settings.rate_limit_enabled = False
    Base.metadata.create_all(bind=TEST_ENGINE)
    yield
    Base.metadata.drop_all(bind=TEST_ENGINE)
    settings.rate_limit_enabled = original_rate_limit


@pytest.fixture(scope="function", autouse=True)
def clean_tables() -> Generator[None, None, None]:
    """Clean all tables before each test (except schema-level setup)."""
    # Reset rate limit store between tests
    _store._windows.clear()
    yield
    with TEST_ENGINE.connect() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
        conn.commit()


@pytest.fixture(scope="function")
def db_session() -> Generator[Session, None, None]:
    """Provide a clean test database session."""
    db = TEST_SESSION_LOCAL()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="function")
def client() -> Generator[TestClient, None, None]:
    """Provide FastAPI test client with overridden DB dependency."""
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def sample_role_employee(db_session: Session) -> Role:
    """Create Employee role with basic permissions."""
    role = Role(name="Employee")
    db_session.add(role)
    db_session.commit()
    db_session.refresh(role)
    return role


@pytest.fixture(scope="function")
def sample_role_admin(db_session: Session) -> Role:
    """Create Admin role with admin permissions."""
    role = Role(name="Admin")
    db_session.add(role)
    db_session.commit()
    db_session.refresh(role)
    return role


@pytest.fixture(scope="function")
def sample_department(db_session: Session) -> Department:
    """Create a test department."""
    dept = Department(name="Engineering", code="ENG")
    db_session.add(dept)
    db_session.commit()
    db_session.refresh(dept)
    return dept


@pytest.fixture(scope="function")
def sample_permission(db_session: Session) -> Permission:
    """Create a test permission."""
    perm = Permission(name="employee:read", description="View employees")
    db_session.add(perm)
    db_session.commit()
    db_session.refresh(perm)
    return perm


@pytest.fixture(scope="function")
def employee_user(db_session: Session, sample_role_employee: Role, sample_department: Department) -> User:
    """Create a test employee user."""
    now = datetime.utcnow()
    user = User(
        username="testemployee",
        email="employee@test.com",
        full_name="Test Employee",
        password_hash=hash_password("TestPass123!"),
        staff_number="EMP-001",
        role_id=sample_role_employee.role_id,
        department_id=sample_department.department_id,
        is_active="Y",
        is_locked="N",
        face_registered="N",
        profile_completed="Y",
        password_changed_at=now,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture(scope="function")
def admin_user(db_session: Session, sample_role_admin: Role, sample_department: Department) -> User:
    """Create a test admin user."""
    now = datetime.utcnow()
    user = User(
        username="testadmin",
        email="admin@test.com",
        full_name="Test Admin",
        password_hash=hash_password("AdminPass123!"),
        staff_number="ADM-001",
        role_id=sample_role_admin.role_id,
        department_id=sample_department.department_id,
        is_active="Y",
        is_locked="N",
        face_registered="Y",
        profile_completed="Y",
        password_changed_at=now,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture(scope="function")
def auth_headers_employee(client: TestClient, employee_user: User) -> dict[str, str]:
    """Authenticate as Employee and return Authorization headers."""
    response = client.post(
        "/api/auth/login",
        json={"username": "testemployee", "password": "TestPass123!"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="function")
def auth_headers_admin(client: TestClient, admin_user: User) -> dict[str, str]:
    """Authenticate as Admin and return Authorization headers."""
    response = client.post(
        "/api/auth/login",
        json={"username": "testadmin", "password": "AdminPass123!"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def unique_username() -> str:
    """Generate a unique username for tests."""
    return f"testuser_{uuid4().hex[:12]}"


def unique_email() -> str:
    """Generate a unique email for tests."""
    return f"test_{uuid4().hex[:12]}@example.com"

