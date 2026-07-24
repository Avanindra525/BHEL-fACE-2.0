"""Debug script to reproduce the test login issue."""
import sys
sys.path.insert(0, '.')
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.core.database import Base, get_db
from app.main import app
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
from app.core.security import hash_password, verify_password, check_password_expired

# Same setup as conftest
TEST_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    echo=False,
)

@event.listens_for(TEST_ENGINE, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

TEST_SESSION_LOCAL = sessionmaker(autocommit=False, autoflush=False, bind=TEST_ENGINE)

def override_get_db():
    db = TEST_SESSION_LOCAL()
    try:
        yield db
    finally:
        db.close()

# Create tables
Base.metadata.create_all(bind=TEST_ENGINE)

# Verify tables exist
with TEST_ENGINE.connect() as conn:
    tables = [r[0] for r in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"))]
    print("Tables:", tables)

# Create fixture data (same order as conftest.test admin_user uses)
db = TEST_SESSION_LOCAL()
role = Role(name="Admin")
db.add(role)
db.commit()
db.refresh(role)

dept = Department(name="Engineering", code="ENG")
db.add(dept)
db.commit()
db.refresh(dept)

pw = hash_password("AdminPass123!")
user = User(
    username="testadmin",
    email="admin@test.com",
    full_name="Test Admin",
    password_hash=pw,
    staff_number="ADM-001",
    role_id=role.role_id,
    department_id=dept.department_id,
    is_active="Y",
    is_locked="N",
    face_registered="Y",
    profile_completed="Y",
)
db.add(user)
db.commit()
db.refresh(user)
print(f"User created: {user.username}, active={user.is_active}, locked={user.is_locked}, pw_changed_at={user.password_changed_at}")
print(f"Verify password: {verify_password('AdminPass123!', user.password_hash)}")
print(f"Password expired: {check_password_expired(user.password_changed_at)}")
db.close()

# Now try login via TestClient
app.dependency_overrides[get_db] = override_get_db
from fastapi.testclient import TestClient
with TestClient(app) as c:
    response = c.post(
        "/api/auth/login",
        json={"username": "testadmin", "password": "AdminPass123!"},
    )
    print(f"Login status: {response.status_code}")
    if response.status_code != 200:
        print(f"Response body: {response.text}")
    else:
        print(f"Login success! Token: {response.json().get('access_token', 'N/A')[:50]}...")
app.dependency_overrides.clear()

