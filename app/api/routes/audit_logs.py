"""Audit log API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.audit_log import AuditLog
from app.models.user import User

router = APIRouter()


@router.get("")
def list_audit_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    action: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict[str, object]:
    """Return audit log entries with pagination and filtering."""

    query = db.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action.ilike(f"%{action}%"))

    total = query.count()
    results = query.order_by(desc(AuditLog.created_at)).offset((page - 1) * page_size).limit(page_size).all()

    return {
        "results": [
            {
                "audit_log_id": log.audit_log_id,
                "action": log.action,
                "details": log.details,
                "user_id": log.user_id,
                "username": log.user.username if log.user else None,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in results
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
