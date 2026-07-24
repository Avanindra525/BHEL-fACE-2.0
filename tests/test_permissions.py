"""Permission CRUD test suite."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


class TestListPermissions:
    def test_list_success(self, client: TestClient, auth_headers_admin, sample_permission) -> None:
        """List returns all permissions."""
        response = client.get("/api/permissions", headers=auth_headers_admin)
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        names = [p["name"] for p in data]
        assert "employee:read" in names

    def test_list_requires_auth(self, client: TestClient) -> None:
        """Unauthenticated returns 401."""
        response = client.get("/api/permissions")
        assert response.status_code == 401


class TestCreatePermission:
    def test_create_success(self, client: TestClient, auth_headers_admin) -> None:
        """Create a valid permission."""
        response = client.post("/api/permissions", json={
            "name": "employee:delete",
            "description": "Delete employees",
        }, headers=auth_headers_admin)
        assert response.status_code == 201
        assert response.json()["name"] == "employee:delete"

    def test_create_duplicate(self, client: TestClient, auth_headers_admin, sample_permission) -> None:
        """Duplicate name returns 409."""
        response = client.post(
            "/api/permissions", json={"name": "employee:read"}, headers=auth_headers_admin,
        )
        assert response.status_code == 409

    def test_create_requires_auth(self, client: TestClient) -> None:
        """Unauthenticated returns 401."""
        response = client.post("/api/permissions", json={"name": "test"})
        assert response.status_code == 401


class TestUpdatePermission:
    def test_update_success(self, client: TestClient, auth_headers_admin, sample_permission) -> None:
        """Update permission description."""
        response = client.put(
            f"/api/permissions/{sample_permission.permission_id}",
            json={"description": "Updated desc"},
            headers=auth_headers_admin,
        )
        assert response.status_code == 200
        assert response.json()["description"] == "Updated desc"

    def test_update_nonexistent(self, client: TestClient, auth_headers_admin) -> None:
        """Update non-existent returns 404."""
        response = client.put(
            "/api/permissions/99999", json={"name": "ghost"}, headers=auth_headers_admin,
        )
        assert response.status_code == 404

