"""Employee CRUD test suite: create, read, update, delete."""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.models.audit_log import AuditLog
from app.models.user import User
from tests.conftest import unique_email, unique_username


class TestListEmployees:
    def test_list_empty(self, client: TestClient, auth_headers_admin) -> None:
        """List employees when none exist."""
        response = client.get("/api/employees", headers=auth_headers_admin)
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_list_with_employees(self, client: TestClient, auth_headers_admin, employee_user) -> None:
        """List returns existing employees."""
        response = client.get("/api/employees", headers=auth_headers_admin)
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        usernames = [e["username"] for e in data]
        assert "testemployee" in usernames

    def test_list_requires_auth(self, client: TestClient) -> None:
        """Unauthenticated list returns 401."""
        response = client.get("/api/employees")
        assert response.status_code == 401


class TestCreateEmployee:
    def test_create_success(self, client: TestClient, auth_headers_admin, db_session) -> None:
        """Create a valid employee returns 201."""
        response = client.post("/api/employees", json={
            "username": unique_username(),
            "email": unique_email(),
            "full_name": "New Employee",
            "password": "StrongPass123",
            "staff_number": f"EMP-{uuid4().hex[:6].upper()}",
        }, headers=auth_headers_admin)
        assert response.status_code == 201
        body = response.json()
        assert body["full_name"] == "New Employee"
        assert body["is_active"] is True

    def test_create_duplicate_username(self, client: TestClient, auth_headers_admin, employee_user) -> None:
        """Duplicate username returns 409."""
        response = client.post("/api/employees", json={
            "username": "testemployee",
            "email": unique_email(),
            "full_name": "Duplicate User",
            "password": "StrongPass123",
        }, headers=auth_headers_admin)
        assert response.status_code == 409

    def test_create_duplicate_email(self, client: TestClient, auth_headers_admin, employee_user) -> None:
        """Duplicate email returns 409."""
        response = client.post("/api/employees", json={
            "username": unique_username(),
            "email": "employee@test.com",
            "full_name": "Duplicate Email",
            "password": "StrongPass123",
        }, headers=auth_headers_admin)
        assert response.status_code == 409

    def test_create_with_department(self, client: TestClient, auth_headers_admin, sample_department, db_session) -> None:
        """Create employee with department assignment."""
        response = client.post("/api/employees", json={
            "username": unique_username(),
            "email": unique_email(),
            "full_name": "Dept Employee",
            "password": "StrongPass123",
            "department_id": sample_department.department_id,
        }, headers=auth_headers_admin)
        assert response.status_code == 201
        assert response.json()["department_id"] == sample_department.department_id

    def test_create_creates_audit_log(self, client: TestClient, auth_headers_admin, db_session) -> None:
        """Employee creation creates audit log entry."""
        username = unique_username()
        client.post("/api/employees", json={
            "username": username,
            "email": unique_email(),
            "full_name": "Audit Employee",
            "password": "StrongPass123",
        }, headers=auth_headers_admin)

        user = db_session.query(User).filter(User.username == username).first()
        audit = db_session.query(AuditLog).filter(
            AuditLog.action == "employee_created"
        ).first()
        assert audit is not None
        assert username in (audit.details or "")


class TestUpdateEmployee:
    def test_update_success(self, client: TestClient, auth_headers_admin, employee_user) -> None:
        """Update employee details."""
        response = client.put(
            f"/api/employees/{employee_user.user_id}",
            json={"full_name": "Updated Name"},
            headers=auth_headers_admin,
        )
        assert response.status_code == 200
        assert response.json()["full_name"] == "Updated Name"

    def test_update_nonexistent(self, client: TestClient, auth_headers_admin) -> None:
        """Update non-existent employee returns 404."""
        response = client.put(
            "/api/employees/99999",
            json={"full_name": "Ghost"},
            headers=auth_headers_admin,
        )
        assert response.status_code == 404

    def test_update_partial(self, client: TestClient, auth_headers_admin, employee_user) -> None:
        """Partial update only changes specified fields."""
        response = client.put(
            f"/api/employees/{employee_user.user_id}",
            json={"bio": "New bio text"},
            headers=auth_headers_admin,
        )
        assert response.status_code == 200
        assert response.json()["bio"] == "New bio text"
        assert response.json()["full_name"] == "Test Employee"  # Unchanged

    def test_update_requires_auth(self, client: TestClient, employee_user) -> None:
        """Unauthenticated update returns 401."""
        response = client.put(
            f"/api/employees/{employee_user.user_id}",
            json={"full_name": "Hacker"},
        )
        assert response.status_code == 401


class TestDeleteEmployee:
    def test_delete_success(self, client: TestClient, auth_headers_admin, db_session) -> None:
        """Delete an employee returns success."""
        # Create employee to delete
        username = unique_username()
        create_resp = client.post("/api/employees", json={
            "username": username,
            "email": unique_email(),
            "full_name": "To Delete",
            "password": "StrongPass123",
        }, headers=auth_headers_admin)
        user_id = create_resp.json()["user_id"]

        delete_resp = client.delete(f"/api/employees/{user_id}", headers=auth_headers_admin)
        assert delete_resp.status_code == 200
        assert "deleted" in delete_resp.json()["message"].lower()

        # Verify gone
        user = db_session.query(User).filter(User.user_id == user_id).first()
        assert user is None

    def test_delete_self_not_allowed(self, client: TestClient, auth_headers_employee, employee_user) -> None:
        """Cannot delete your own account."""
        response = client.delete(
            f"/api/employees/{employee_user.user_id}",
            headers=auth_headers_employee,
        )
        assert response.status_code == 400

    def test_delete_nonexistent(self, client: TestClient, auth_headers_admin) -> None:
        """Delete non-existent returns 404."""
        response = client.delete("/api/employees/99999", headers=auth_headers_admin)
        assert response.status_code == 404

