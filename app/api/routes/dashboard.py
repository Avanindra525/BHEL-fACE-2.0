"""Dashboard API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.department import Department
from app.models.permission import Permission
from app.models.role import Role
from app.models.user import User
from app.models.login_log import LoginLog

router = APIRouter()


@router.get("/summary", response_model=dict[str, object])
def dashboard_summary(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict[str, object]:
    """Return a dashboard summary for the current user and the admin workspace."""

    user_count = db.query(User).count()
    department_count = db.query(Department).count()
    role_count = db.query(Role).count()
    permission_count = db.query(Permission).count()
    face_registered_count = db.query(User).filter(User.face_registered == "Y").count()
    last_login = db.query(LoginLog).filter(
        LoginLog.user_id == current_user.user_id,
        LoginLog.success == "Y"
    ).order_by(LoginLog.login_time.desc()).first()

    return {
        "user": current_user.username,
        "full_name": current_user.full_name,
        "role": current_user.role.name if current_user.role else "Guest",
        "face_registered": current_user.face_registered == "Y",
        "profile_completed": current_user.profile_completed == "Y",
        "last_login_at": last_login.login_time.isoformat() if last_login else None,
        "department": current_user.department.name if current_user.department else None,
        "user_count": user_count,
        "department_count": department_count,
        "role_count": role_count,
        "permission_count": permission_count,
        "face_registered_count": face_registered_count,
    }
