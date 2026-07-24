"""Basic smoke tests for the FaceAuth Enterprise app."""

from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.models.department import Department
from app.models.face_sample import FaceSample
from app.models.permission import Permission
from app.models.role import Role
from app.models.user import User


client = TestClient(app)


def test_health() -> None:
    """The health endpoint should respond successfully."""

    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_register_and_login_flow() -> None:
    """Registering a user should persist them and return usable auth tokens."""

    username = f"oracle_user_{uuid4().hex[:8]}"
    payload = {
        "username": username,
        "email": f"{username}@example.com",
        "full_name": "Oracle Test User",
        "password": "StrongPass123!",
        "password_confirmation": "StrongPass123!",
        "staff_number": f"EMP-{uuid4().hex[:6].upper()}",
        "profile_completed": True,
    }

    register_response = client.post("/api/auth/register", json=payload)
    assert register_response.status_code == 201
    register_body = register_response.json()
    assert register_body["access_token"]
    assert register_body["refresh_token"]

    login_response = client.post(
        "/api/auth/login",
        json={"username": username, "password": "StrongPass123!"},
    )
    assert login_response.status_code == 200
    login_body = login_response.json()
    assert login_body["access_token"]
    assert login_body["refresh_token"]


def test_dashboard_summary_returns_counts() -> None:
    """The dashboard summary endpoint should expose aggregate counts for the admin views."""

    username = f"summary_user_{uuid4().hex[:8]}"
    payload = {
        "username": username,
        "email": f"{username}@example.com",
        "full_name": "Summary User",
        "password": "StrongPass123!",
        "password_confirmation": "StrongPass123!",
        "staff_number": f"EMP-{uuid4().hex[:6].upper()}",
        "profile_completed": True,
    }

    register_response = client.post("/api/auth/register", json=payload)
    assert register_response.status_code == 201
    access_token = register_response.json()["access_token"]

    response = client.get(
        "/api/dashboard/summary",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["user_count"] >= 1
    assert body["department_count"] >= 0
    assert body["role_count"] >= 0
    assert body["permission_count"] >= 0
    assert body["face_registered_count"] >= 0


def test_admin_page_renders_database_counts() -> None:
    """The admin page should render counts from the database instead of fixed placeholders."""

    db = SessionLocal()
    try:
        user_count = db.query(User).count()
        department_count = db.query(Department).count()
        role_count = db.query(Role).count()
        permission_count = db.query(Permission).count()
    finally:
        db.close()

    response = client.get("/admin")
    assert response.status_code == 200
    html = response.text
    assert str(user_count) in html
    assert str(department_count) in html
    assert str(role_count) in html
    assert str(permission_count) in html


def test_employee_creation_persists_user() -> None:
    """Creating an employee through the API should persist the user in the database."""

    username = f"employee_user_{uuid4().hex[:8]}"
    register_payload = {
        "username": username,
        "email": f"{username}@example.com",
        "full_name": "Employee Test User",
        "password": "StrongPass123!",
        "password_confirmation": "StrongPass123!",
    }

    register_response = client.post("/api/auth/register", json=register_payload)
    assert register_response.status_code == 201
    access_token = register_response.json()["access_token"]

    employee_payload = {
        "username": f"employee_{uuid4().hex[:6]}",
        "email": f"employee_{uuid4().hex[:6]}@example.com",
        "full_name": "Managed Employee",
        "password": "StrongPass123!",
        "staff_number": "EMP-1002",
        "profile_completed": True,
        "face_registered": False,
    }

    create_response = client.post(
        "/api/employees",
        json=employee_payload,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert create_response.status_code == 201

    db = SessionLocal()
    try:
        created_user = db.query(User).filter(User.username == employee_payload["username"]).first()
    finally:
        db.close()

    assert created_user is not None
    assert created_user.full_name == employee_payload["full_name"]


def test_face_registration_updates_user_state() -> None:
    """Uploading a face sample should mark the user as face-registered and create a biometric sample record."""

    username = f"face_user_{uuid4().hex[:8]}"
    register_payload = {
        "username": username,
        "email": f"{username}@example.com",
        "full_name": "Face User",
        "password": "StrongPass123!",
        "password_confirmation": "StrongPass123!",
    }

    register_response = client.post("/api/auth/register", json=register_payload)
    assert register_response.status_code == 201
    access_token = register_response.json()["access_token"]

    response = client.post(
        "/api/face/register",
        headers={"Authorization": f"Bearer {access_token}"},
        files={"file": ("sample.png", b"fake-image-data", "image/png")},
    )
    assert response.status_code == 201

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        samples = db.query(FaceSample).filter(FaceSample.user_id == user.user_id).all()
    finally:
        db.close()

    assert user is not None
    assert user.face_registered == "Y"
    assert user.profile_completed == "Y"
    assert len(samples) >= 1
