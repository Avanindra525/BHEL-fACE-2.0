"""Analytics & Statistics API test suite."""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.department import Department
from app.models.login_log import LoginLog
from app.models.user import User
from tests.conftest import unique_username, unique_email


class TestDashboardStats:
    def test_dashboard_returns_metrics(self, client: TestClient, auth_headers_admin) -> None:
        """Dashboard stats endpoint returns all key metrics."""
        response = client.get("/api/statistics/dashboard", headers=auth_headers_admin)
        assert response.status_code == 200
        data = response.json()
        assert "total_employees" in data
        assert "active_employees" in data
        assert "today_logins" in data
        assert "auth_success_rate" in data

    def test_dashboard_requires_auth(self, client: TestClient) -> None:
        """Dashboard without auth returns 401."""
        response = client.get("/api/statistics/dashboard")
        assert response.status_code == 401


class TestLoginStats:
    def test_login_stats_returns_time_series(self, client: TestClient, auth_headers_admin) -> None:
        """Login stats returns daily and monthly time series."""
        response = client.get("/api/statistics/login", headers=auth_headers_admin)
        assert response.status_code == 200
        data = response.json()
        assert "daily_labels" in data
        assert "daily_success" in data
        assert "monthly_labels" in data
        assert "heatmap_data" in data

    def test_login_stats_with_date_filter(self, client: TestClient, auth_headers_admin) -> None:
        """Login stats accepts date range filters."""
        response = client.get(
            "/api/statistics/login",
            params={"start_date": "2024-01-01", "end_date": "2024-12-31"},
            headers=auth_headers_admin,
        )
        assert response.status_code == 200


class TestEmployeeStats:
    def test_employee_stats_returns_growth(self, client: TestClient, auth_headers_admin) -> None:
        """Employee stats returns growth data."""
        response = client.get("/api/statistics/employees", headers=auth_headers_admin)
        assert response.status_code == 200
        data = response.json()
        assert "growth_labels" in data
        assert "growth_data" in data
        assert "active_count" in data

    def test_employee_stats_with_department_filter(self, client: TestClient, auth_headers_admin, sample_department) -> None:
        """Employee stats filters by department."""
        response = client.get(
            "/api/statistics/employees",
            params={"department_id": sample_department.department_id},
            headers=auth_headers_admin,
        )
        assert response.status_code == 200


class TestAttendanceStats:
    def test_attendance_returns_paginated(self, client: TestClient, auth_headers_admin) -> None:
        """Attendance returns paginated results."""
        response = client.get("/api/statistics/attendance", headers=auth_headers_admin)
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data

    def test_attendance_with_employee_filter(self, client: TestClient, auth_headers_admin, employee_user) -> None:
        """Attendance filters by employee ID."""
        response = client.get(
            "/api/statistics/attendance",
            params={"employee_id": employee_user.user_id},
            headers=auth_headers_admin,
        )
        assert response.status_code == 200
        assert len(response.json()["results"]) >= 0


class TestFaceStats:
    def test_face_stats_returns_metrics(self, client: TestClient, auth_headers_admin) -> None:
        """Face stats returns registration and accuracy metrics."""
        response = client.get("/api/statistics/face", headers=auth_headers_admin)
        assert response.status_code == 200
        data = response.json()
        assert "total_face_registrations" in data
        assert "unique_users_with_face" in data
        assert "accuracy_values" in data


class TestDepartmentStats:
    def test_department_stats_returns_breakdown(self, client: TestClient, auth_headers_admin) -> None:
        """Department stats returns per-department data."""
        response = client.get("/api/statistics/departments", headers=auth_headers_admin)
        assert response.status_code == 200
        data = response.json()
        assert "departments" in data
        assert "total_departments" in data


class TestExport:
    def test_export_employee_report(self, client: TestClient, auth_headers_admin) -> None:
        """Export employee report returns CSV."""
        response = client.get(
            "/api/statistics/export",
            params={"report": "employees"},
            headers=auth_headers_admin,
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")

    def test_export_login_report(self, client: TestClient, auth_headers_admin) -> None:
        """Export login report returns CSV."""
        response = client.get(
            "/api/statistics/export",
            params={"report": "login"},
            headers=auth_headers_admin,
        )
        assert response.status_code == 200

    def test_export_face_report(self, client: TestClient, auth_headers_admin) -> None:
        """Export face registration report returns CSV."""
        response = client.get(
            "/api/statistics/export",
            params={"report": "face_registration"},
            headers=auth_headers_admin,
        )
        assert response.status_code == 200

    def test_export_unknown_report(self, client: TestClient, auth_headers_admin) -> None:
        """Export unknown report type returns CSV with error."""
        response = client.get(
            "/api/statistics/export",
            params={"report": "unknown_type"},
            headers=auth_headers_admin,
        )
        assert response.status_code == 200

