"""Department CRUD test suite."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.models.department import Department


class TestListDepartments:
    def test_list_success(self, client: TestClient, auth_headers_admin, sample_department) -> None:
        """List returns all departments."""
        response = client.get("/api/departments", headers=auth_headers_admin)
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        names = [d["name"] for d in data]
        assert "Engineering" in names

    def test_list_requires_auth(self, client: TestClient) -> None:
        """Unauthenticated list returns 401."""
        response = client.get("/api/departments")
        assert response.status_code == 401


class TestCreateDepartment:
    def test_create_success(self, client: TestClient, auth_headers_admin) -> None:
        """Create a valid department."""
        response = client.post("/api/departments", json={
            "name": "Marketing",
            "code": "MKT",
            "description": "Marketing department",
        }, headers=auth_headers_admin)
        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "Marketing"
        assert body["code"] == "MKT"
        assert body["is_active"] is True

    def test_create_duplicate(self, client: TestClient, auth_headers_admin, sample_department) -> None:
        """Duplicate name returns 409."""
        response = client.post("/api/departments", json={
            "name": "Engineering",
        }, headers=auth_headers_admin)
        assert response.status_code == 409

    def test_create_requires_auth(self, client: TestClient) -> None:
        """Unauthenticated create returns 401."""
        response = client.post("/api/departments", json={"name": "Test"})
        assert response.status_code == 401


class TestUpdateDepartment:
    def test_update_success(self, client: TestClient, auth_headers_admin, sample_department) -> None:
        """Update department name."""
        response = client.put(
            f"/api/departments/{sample_department.department_id}",
            json={"name": "Engineering Updated", "code": "ENGU"},
            headers=auth_headers_admin,
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Engineering Updated"
        assert response.json()["code"] == "ENGU"

    def test_update_nonexistent(self, client: TestClient, auth_headers_admin) -> None:
        """Update non-existent returns 404."""
        response = client.put(
            "/api/departments/99999",
            json={"name": "Ghost Dept"},
            headers=auth_headers_admin,
        )
        assert response.status_code == 404

    def test_update_requires_auth(self, client: TestClient, sample_department) -> None:
        """Unauthenticated update returns 401."""
        response = client.put(
            f"/api/departments/{sample_department.department_id}",
            json={"name": "Hacked"},
        )
        assert response.status_code == 401

