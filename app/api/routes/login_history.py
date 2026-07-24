"""Login history API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.login_log import LoginLog
from app.models.user import User

router = APIRouter()


@router.get("")
def list_login_history(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    method: str | None = Query(default=None),
    status: str | None = Query(default=None),
    ip: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, object]:
    """Return login history for the current user with pagination and filtering."""

    query = db.query(LoginLog).filter(LoginLog.user_id == current_user.user_id)

    if method:
        query = query.filter(LoginLog.login_method == method)
    if status == "success":
        query = query.filter(LoginLog.success == "Y")
    elif status == "failed":
        query = query.filter(LoginLog.success == "N")
    if ip:
        query = query.filter(LoginLog.ip_address.ilike(f"%{ip}%"))

    total = query.count()
    results = query.order_by(desc(LoginLog.login_time)).offset((page - 1) * page_size).limit(page_size).all()

    return {
        "results": [
            {
                "login_log_id": h.login_log_id,
                "login_time": h.login_time.isoformat() if h.login_time else None,
                "created_at": h.created_at.isoformat() if h.created_at else None,
                "login_method": h.login_method,
                "success": h.success,
                "ip_address": h.ip_address,
                "user_agent": h.user_agent,
                "failure_reason": h.failure_reason,
            }
            for h in results
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
