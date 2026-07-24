"""Role CRUD test suite."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.models.role import Role


class TestListRoles:
    def test_list_success(self, client: TestClient, auth_headers_admin, sample_role_employee) -> None:
        """List returns all roles."""
        response = client.get("/api/roles", headers=auth_headers_admin)
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        names = [r["name"] for r in data]
        assert "Employee" in names

    def test_list_requires_auth(self, client: TestClient) -> None:
        """Unauthenticated returns 401."""
        response = client.get("/api/roles")
        assert response.status_code == 401


class TestCreateRole:
    def test_create_success(self, client: TestClient, auth_headers_admin) -> None:
        """Create a valid role."""
        response = client.post("/api/roles", json={
            "name": "Manager",
            "description": "Department managers",
        }, headers=auth_headers_admin)
        assert response.status_code == 201
        assert response.json()["name"] == "Manager"

    def test_create_duplicate(self, client: TestClient, auth_headers_admin, sample_role_employee) -> None:
        """Duplicate name returns 409."""
        response = client.post("/api/roles", json={"name": "Employee"}, headers=auth_headers_admin)
        assert response.status_code == 409

    def test_create_requires_auth(self, client: TestClient) -> None:
        """Unauthenticated returns 401."""
        response = client.post("/api/roles", json={"name": "Test"})
        assert response.status_code == 401


class TestUpdateRole:
    def test_update_success(self, client: TestClient, auth_headers_admin, sample_role_employee) -> None:
        """Update role description."""
        response = client.put(
            f"/api/roles/{sample_role_employee.role_id}",
            json={"description": "Updated description"},
            headers=auth_headers_admin,
        )
        assert response.status_code == 200
        assert response.json()["description"] == "Updated description"

    def test_update_nonexistent(self, client: TestClient, auth_headers_admin) -> None:
        """Update non-existent returns 404."""
        response = client.put("/api/roles/99999", json={"name": "Ghost"}, headers=auth_headers_admin)
        assert response.status_code == 404

