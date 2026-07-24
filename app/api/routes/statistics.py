"""Statistics & Analytics API routes — Oracle-optimized aggregations.

Provides six specialized endpoints for the analytics module plus export.
All queries use Oracle-compatible SQLAlchemy aggregations.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, extract, case
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.department import Department
from app.models.login_log import LoginLog
from app.models.face_sample import FaceSample
from app.models.audit_log import AuditLog

router = APIRouter()


def _get_date_filter(model, start_date: str | None, end_date: str | None):
    """Build a date filter for Oracle DATE columns."""
    filters = []
    if start_date:
        try:
            sd = datetime.strptime(start_date, "%Y-%m-%d")
            filters.append(model >= sd)
        except ValueError:
            pass
    if end_date:
        try:
            ed = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
            filters.append(model < ed)
        except ValueError:
            pass
    return filters


# ─── /api/statistics/dashboard ──────────────────────────────────────────────


@router.get("/dashboard")
def dashboard_stats(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict[str, object]:
    """Dashboard summary cards with all key metrics."""
    now = datetime.utcnow()
    today_start = datetime(now.year, now.month, now.day)
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    # Employee counts
    total_employees = db.query(User).count()
    active_employees = db.query(User).filter(User.is_active == "Y").count()
    disabled_employees = db.query(User).filter(User.is_active == "N").count()
    face_registered = db.query(User).filter(User.face_registered == "Y").count()
    face_unregistered = total_employees - face_registered

    # Login counts
    today_logins = db.query(LoginLog).filter(LoginLog.login_time >= today_start).count()
    weekly_logins = db.query(LoginLog).filter(LoginLog.login_time >= week_ago).count()
    monthly_logins = db.query(LoginLog).filter(LoginLog.login_time >= month_ago).count()
    total_logins = db.query(LoginLog).count()

    successful_logins = db.query(LoginLog).filter(LoginLog.success == "Y").count()
    failed_logins = db.query(LoginLog).filter(LoginLog.success == "N").count()
    face_logins = db.query(LoginLog).filter(LoginLog.login_method == "face").count()
    password_logins = db.query(LoginLog).filter(LoginLog.login_method == "password").count()

    # Recognition accuracy (face login success rate)
    total_face_attempts = db.query(LoginLog).filter(LoginLog.login_method == "face").count()
    successful_face = db.query(LoginLog).filter(
        LoginLog.login_method == "face", LoginLog.success == "Y"
    ).count()
    recognition_accuracy = round(
        (successful_face / total_face_attempts * 100) if total_face_attempts > 0 else 0, 1
    )

    # Face login success rate (of all logins)
    face_login_success_rate = round(
        (successful_face / face_logins * 100) if face_logins > 0 else 0, 1
    )

    # Average recognition confidence (from FaceSample quality scores)
    avg_confidence = db.query(func.avg(FaceSample.quality_score)).scalar()
    avg_confidence = round(float(avg_confidence), 1) if avg_confidence else 0.0

    # Auth success rate
    auth_success_rate = round(
        (successful_logins / total_logins * 100) if total_logins > 0 else 0, 1
    )

    return {
        "total_employees": total_employees,
        "active_employees": active_employees,
        "disabled_employees": disabled_employees,
        "face_registered": face_registered,
        "face_unregistered": face_unregistered,
        "today_logins": today_logins,
        "weekly_logins": weekly_logins,
        "monthly_logins": monthly_logins,
        "total_logins": total_logins,
        "successful_logins": successful_logins,
        "failed_logins": failed_logins,
        "face_logins": face_logins,
        "password_logins": password_logins,
        "recognition_accuracy": recognition_accuracy,
        "face_login_success_rate": face_login_success_rate,
        "avg_recognition_confidence": avg_confidence,
        "auth_success_rate": auth_success_rate,
        "updated_at": now.isoformat(),
    }


# ─── /api/statistics/login ──────────────────────────────────────────────────


@router.get("/login")
def login_stats(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    department_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict[str, object]:
    """Detailed login analytics with chart-ready time series."""
    now = datetime.utcnow()
    date_filters = _get_date_filter(LoginLog.login_time, start_date, end_date)

    # ── Daily login trend (last 14 days) ──
    daily_labels: list[str] = []
    daily_success: list[int] = []
    daily_failed: list[int] = []
    for i in range(13, -1, -1):
        day = now - timedelta(days=i)
        day_start = datetime(day.year, day.month, day.day)
        day_end = day_start + timedelta(days=1)

        query_success = db.query(func.count(LoginLog.login_log_id)).filter(
            LoginLog.login_time >= day_start,
            LoginLog.login_time < day_end,
            LoginLog.success == "Y",
            *date_filters,
        )
        query_failed = db.query(func.count(LoginLog.login_log_id)).filter(
            LoginLog.login_time >= day_start,
            LoginLog.login_time < day_end,
            LoginLog.success == "N",
            *date_filters,
        )

        if department_id:
            query_success = query_success.join(User).filter(User.department_id == department_id)
            query_failed = query_failed.join(User).filter(User.department_id == department_id)

        daily_labels.append(day.strftime("%d %b"))
        daily_success.append(query_success.scalar() or 0)
        daily_failed.append(query_failed.scalar() or 0)

    # ── Monthly login trend (last 12 months) ──
    monthly_labels: list[str] = []
    monthly_success: list[int] = []
    monthly_failed: list[int] = []
    for i in range(11, -1, -1):
        m = now.month - i
        y = now.year
        if m <= 0:
            m += 12
            y -= 1
        month_start = datetime(y, m, 1)
        if m == 12:
            month_end = datetime(y + 1, 1, 1)
        else:
            month_end = datetime(y, m + 1, 1)

        q_success = db.query(func.count(LoginLog.login_log_id)).filter(
            LoginLog.login_time >= month_start,
            LoginLog.login_time < month_end,
            LoginLog.success == "Y",
            *date_filters,
        )
        q_failed = db.query(func.count(LoginLog.login_log_id)).filter(
            LoginLog.login_time >= month_start,
            LoginLog.login_time < month_end,
            LoginLog.success == "N",
            *date_filters,
        )
        if department_id:
            q_success = q_success.join(User).filter(User.department_id == department_id)
            q_failed = q_failed.join(User).filter(User.department_id == department_id)

        monthly_labels.append(month_start.strftime("%b %Y"))
        monthly_success.append(q_success.scalar() or 0)
        monthly_failed.append(q_failed.scalar() or 0)

    # ── Login heatmap (hour × day of week) ──
    heatmap_data: list[list[int]] = [[0] * 7 for _ in range(24)]
    # Build hour-of-day × day-of-week matrix
    # day_of_week: 0=Mon, 6=Sun  (Oracle: 1=Sun, 2=Mon...)
    heatmap_query = db.query(
        extract("dow", LoginLog.login_time).label("dow"),
        extract("hour", LoginLog.login_time).label("hour"),
        func.count().label("cnt"),
    ).filter(*date_filters)

    if department_id:
        heatmap_query = heatmap_query.join(User).filter(User.department_id == department_id)

    heatmap_rows = heatmap_query.group_by(
        extract("dow", LoginLog.login_time),
        extract("hour", LoginLog.login_time),
    ).all()

    for row in heatmap_rows:
        # Oracle DOW: 1=Sun → map to 0=Mon
        dow = (int(row.dow) - 2) % 7
        hour = int(row.hour)
        if 0 <= hour < 24 and 0 <= dow < 7:
            heatmap_data[hour][dow] = int(row.cnt)

    return {
        "daily_labels": daily_labels,
        "daily_success": daily_success,
        "daily_failed": daily_failed,
        "monthly_labels": monthly_labels,
        "monthly_success": monthly_success,
        "monthly_failed": monthly_failed,
        "heatmap_data": heatmap_data,
        "heatmap_hours": [f"{h:02d}:00" for h in range(24)],
        "heatmap_days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    }


# ─── /api/statistics/employees ──────────────────────────────────────────────


@router.get("/employees")
def employee_stats(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    department_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict[str, object]:
    """Employee growth and status analytics."""
    now = datetime.utcnow()

    # Employee growth over last 12 months
    growth_labels: list[str] = []
    growth_data: list[int] = []
    for i in range(11, -1, -1):
        m = now.month - i
        y = now.year
        if m <= 0:
            m += 12
            y -= 1
        month_end = datetime(y, m, 28)  # Safe date
        count = db.query(User).filter(User.created_at <= month_end).count()
        growth_labels.append(datetime(y, m, 1).strftime("%b %Y"))
        growth_data.append(count)

    # Department breakdown
    departments_data: dict[str, int] = {}
    depts = db.query(Department).all()
    for dept in depts:
        count = db.query(User).filter(User.department_id == dept.department_id).count()
        if count > 0:
            departments_data[dept.name] = count

    # Status breakdown
    active_count = db.query(User).filter(User.is_active == "Y").count()
    inactive_count = db.query(User).filter(User.is_active == "N").count()
    locked_count = db.query(User).filter(User.is_locked == "Y").count()

    return {
        "growth_labels": growth_labels,
        "growth_data": growth_data,
        "departments": departments_data,
        "active_count": active_count,
        "inactive_count": inactive_count,
        "locked_count": locked_count,
    }


# ─── /api/statistics/attendance ────────────────────────────────────────────


@router.get("/attendance")
def attendance_stats(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    department_id: int | None = Query(default=None),
    employee_id: int | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict[str, object]:
    """Attendance report — daily login summaries per user."""
    now = datetime.utcnow()
    if not start_date:
        start_date = (now - timedelta(days=30)).strftime("%Y-%m-%d")
    if not end_date:
        end_date = now.strftime("%Y-%m-%d")

    sd = datetime.strptime(start_date, "%Y-%m-%d")
    ed = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)

    # Aggregated attendance per user
    base_query = db.query(
        User.user_id,
        User.full_name,
        User.staff_number,
        Department.name.label("dept_name"),
        func.count(LoginLog.login_log_id).label("total_logins"),
        func.sum(case((LoginLog.success == "Y", 1), else_=0)).label("successful"),
        func.sum(case((LoginLog.success == "N", 1), else_=0)).label("failed"),
        func.max(LoginLog.login_time).label("last_login"),
    ).outerjoin(
        LoginLog, User.user_id == LoginLog.user_id,
    ).outerjoin(
        Department, User.department_id == Department.department_id,
    ).filter(
        LoginLog.login_time >= sd,
        LoginLog.login_time < ed,
    )

    if department_id:
        base_query = base_query.filter(User.department_id == department_id)
    if employee_id:
        base_query = base_query.filter(User.user_id == employee_id)

    total = base_query.group_by(
        User.user_id, User.full_name, User.staff_number, Department.name,
    ).count()

    rows = base_query.group_by(
        User.user_id, User.full_name, User.staff_number, Department.name,
    ).order_by(
        func.max(LoginLog.login_time).desc().nullslast(),
    ).offset((page - 1) * page_size).limit(page_size).all()

    results = []
    for row in rows:
        results.append({
            "user_id": row.user_id,
            "full_name": row.full_name,
            "staff_number": row.staff_number,
            "department": row.dept_name,
            "total_logins": int(row.total_logins),
            "successful": int(row.successful),
            "failed": int(row.failed),
            "last_login": row.last_login.isoformat() if row.last_login else None,
        })

    return {
        "results": results,
        "total": total,
        "page": page,
        "page_size": page_size,
        "start_date": start_date,
        "end_date": end_date,
    }


# ─── /api/statistics/face ──────────────────────────────────────────────────


@router.get("/face")
def face_stats(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    department_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict[str, object]:
    """Face recognition analytics with accuracy trends."""
    now = datetime.utcnow()
    date_filters = _get_date_filter(FaceSample.created_at, start_date, end_date)

    total_face_registrations = db.query(FaceSample).count()
    unique_users_with_face = db.query(FaceSample.user_id).distinct().count()
    total_embeddings = db.query(FaceSample).filter(FaceSample.embedding_blob.isnot(None)).count()

    # Average quality score per pose
    pose_quality: dict[str, float] = {}
    poses = db.query(FaceSample.pose, func.avg(FaceSample.quality_score)).group_by(FaceSample.pose).all()
    for pose, avg_q in poses:
        pose_quality[pose] = round(float(avg_q), 1) if avg_q else 0.0

    # Face registration over time (monthly)
    monthly_labels: list[str] = []
    monthly_regs: list[int] = []
    for i in range(11, -1, -1):
        m = now.month - i
        y = now.year
        if m <= 0:
            m += 12
            y -= 1
        month_start = datetime(y, m, 1)
        if m == 12:
            month_end = datetime(y + 1, 1, 1)
        else:
            month_end = datetime(y, m + 1, 1)

        count = db.query(FaceSample).filter(
            FaceSample.created_at >= month_start,
            FaceSample.created_at < month_end,
            *date_filters,
        ).count()
        monthly_labels.append(month_start.strftime("%b %Y"))
        monthly_regs.append(count)

    # Recognition accuracy over time (last 30 days)
    accuracy_dates: list[str] = []
    accuracy_values: list[float] = []
    for i in range(29, -1, -1):
        day = now - timedelta(days=i)
        day_start = datetime(day.year, day.month, day.day)
        day_end = day_start + timedelta(days=1)

        total_face = db.query(LoginLog).filter(
            LoginLog.login_time >= day_start,
            LoginLog.login_time < day_end,
            LoginLog.login_method == "face",
        ).count()

        success_face = db.query(LoginLog).filter(
            LoginLog.login_time >= day_start,
            LoginLog.login_time < day_end,
            LoginLog.login_method == "face",
            LoginLog.success == "Y",
        ).count()

        acc = round((success_face / total_face * 100), 1) if total_face > 0 else 0.0
        accuracy_dates.append(day.strftime("%d %b"))
        accuracy_values.append(acc)

    return {
        "total_face_registrations": total_face_registrations,
        "unique_users_with_face": unique_users_with_face,
        "total_embeddings_stored": total_embeddings,
        "pose_quality": pose_quality,
        "monthly_labels": monthly_labels,
        "monthly_registrations": monthly_regs,
        "accuracy_dates": accuracy_dates,
        "accuracy_values": accuracy_values,
        "avg_quality_score": round(
            float(
                db.query(func.avg(FaceSample.quality_score)).scalar() or 0
            ), 1
        ),
    }


# ─── /api/statistics/departments ───────────────────────────────────────────


@router.get("/departments")
def department_stats(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict[str, object]:
    """Department-level analytics."""
    now = datetime.utcnow()
    date_filters = _get_date_filter(User.created_at, start_date, end_date)

    depts = db.query(Department).all()
    dept_data: list[dict[str, Any]] = []

    for dept in depts:
        emp_count = db.query(User).filter(
            User.department_id == dept.department_id,
            *date_filters,
        ).count()
        active_emp = db.query(User).filter(
            User.department_id == dept.department_id,
            User.is_active == "Y",
            *date_filters,
        ).count()
        face_count = db.query(User).filter(
            User.department_id == dept.department_id,
            User.face_registered == "Y",
            *date_filters,
        ).count()

        dept_data.append({
            "department_id": dept.department_id,
            "name": dept.name,
            "code": dept.code,
            "employee_count": emp_count,
            "active_employees": active_emp,
            "face_registered_count": face_count,
        })

    return {
        "departments": dept_data,
        "total_departments": len(depts),
    }


# ─── /api/statistics/export ────────────────────────────────────────────────


@router.get("/export")
def export_statistics(
    report: str = Query(...),
    format: str = Query(default="csv"),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    department_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> Response:
    """Export statistics as CSV (Excel/PDF support via conversion)."""
    now = datetime.utcnow()
    sd = start_date or (now - timedelta(days=30)).strftime("%Y-%m-%d")

    output = io.StringIO()
    writer = csv.writer(output)

    if report == "employees":
        writer.writerow(["User ID", "Full Name", "Email", "Staff Number", "Department", "Status", "Face Registered", "Last Login"])
        users = db.query(User).order_by(User.created_at.desc()).all()
        for u in users:
            writer.writerow([
                u.user_id, u.full_name, u.email, u.staff_number,
                u.department.name if u.department else "N/A",
                "Active" if u.is_active == "Y" else "Inactive",
                "Yes" if u.face_registered == "Y" else "No",
                u.last_login_at.strftime("%Y-%m-%d %H:%M") if u.last_login_at else "Never",
            ])

    elif report == "login":
        writer.writerow(["Login ID", "User", "Method", "Success", "IP Address", "Login Time"])
        logs = db.query(LoginLog).order_by(LoginLog.login_time.desc()).limit(1000).all()
        for log in logs:
            writer.writerow([
                log.login_log_id,
                log.user.username if log.user else "Unknown",
                log.login_method,
                "Yes" if log.success == "Y" else "No",
                log.ip_address or "N/A",
                log.login_time.strftime("%Y-%m-%d %H:%M") if log.login_time else "N/A",
            ])

    elif report == "face_registration":
        writer.writerow(["Sample ID", "User ID", "User Name", "Pose", "Quality Score", "Created At"])
        samples = db.query(FaceSample).order_by(FaceSample.created_at.desc()).all()
        for s in samples:
            writer.writerow([
                s.face_sample_id, s.user_id,
                s.user.full_name if s.user else "Unknown",
                s.pose, s.quality_score,
                s.created_at.strftime("%Y-%m-%d %H:%M") if s.created_at else "N/A",
            ])

    elif report == "attendance":
        writer.writerow(["User ID", "Full Name", "Department", "Total Logins", "Successful", "Failed", "Last Login"])
        rows = db.query(
            User.user_id, User.full_name, Department.name,
            func.count(LoginLog.login_log_id),
            func.sum(case((LoginLog.success == "Y", 1), else_=0)),
            func.sum(case((LoginLog.success == "N", 1), else_=0)),
            func.max(LoginLog.login_time),
        ).outerjoin(LoginLog, User.user_id == LoginLog.user_id
        ).outerjoin(Department, User.department_id == Department.department_id
        ).group_by(User.user_id, User.full_name, Department.name).all()

        for row in rows:
            writer.writerow([
                row.user_id, row.full_name, row.name or "N/A",
                int(row[3]), int(row[4]), int(row[5]),
                row[6].strftime("%Y-%m-%d %H:%M") if row[6] else "Never",
            ])

    elif report == "department":
        writer.writerow(["Department", "Code", "Employees", "Active", "Face Registered"])
        depts = db.query(Department).all()
        for dept in depts:
            emp = db.query(User).filter(User.department_id == dept.department_id).count()
            active = db.query(User).filter(User.department_id == dept.department_id, User.is_active == "Y").count()
            face = db.query(User).filter(User.department_id == dept.department_id, User.face_registered == "Y").count()
            writer.writerow([dept.name, dept.code or "N/A", emp, active, face])

    else:
        writer.writerow(["Report type not supported"])

    csv_content = output.getvalue()
    filename = f"{report}_report_{sd}.csv"

    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )

