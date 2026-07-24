"""Employee management API routes."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.department import Department
from app.models.user import User
from app.schemas.user import UserCreate, UserResponse, UserUpdate
from app.core.security import hash_password
from app.models.audit_log import AuditLog
from app.models.face_sample import FaceSample
from app.models.login_log import LoginLog
from app.models.refresh_token import RefreshToken

router = APIRouter()


@router.get("", response_model=list[dict[str, object]])
def list_employees(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> list[dict[str, object]]:
    """List all employees with enriched data."""

    users = db.query(User).order_by(User.created_at.desc()).all()
    return [
        {
            "user_id": u.user_id,
            "username": u.username,
            "email": u.email,
            "full_name": u.full_name,
            "staff_number": u.staff_number,
            "role": u.role.name if u.role else None,
            "department": u.department.name if u.department else None,
            "department_id": u.department_id,
            "is_active": u.is_active,
            "is_locked": u.is_locked,
            "face_registered": u.face_registered,
            "profile_completed": u.profile_completed,
            "bio": u.bio,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "updated_at": u.updated_at.isoformat() if u.updated_at else None,
        }
        for u in users
    ]


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_employee(payload: UserCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> User:
    """Create a new employee account."""

    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")
    if db.query(User).filter(User.email == str(payload.email)).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")

    department = None
    if payload.department_id:
        department = db.query(Department).filter(Department.department_id == payload.department_id).first()

    user = User(
        username=payload.username,
        email=str(payload.email),
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        staff_number=payload.staff_number,
        department_id=department.department_id if department else None,
        profile_completed="Y" if payload.profile_completed else "N",
        face_registered="Y" if payload.face_registered else "N",
        is_active="Y",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Log audit
    audit = AuditLog(user_id=current_user.user_id, action="employee_created", details=f"Created employee: {user.username}")
    db.add(audit)
    db.commit()

    return user


@router.put("/{user_id}", response_model=UserResponse)
def update_employee(user_id: int, payload: UserUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> User:
    """Update an existing employee account."""

    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, field, value)

    user.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(user)

    # Log audit
    audit = AuditLog(user_id=current_user.user_id, action="employee_updated", details=f"Updated employee: {user.username}")
    db.add(audit)
    db.commit()

    return user


@router.delete("/{user_id}")
def delete_employee(user_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> dict[str, str]:
    """Delete an employee account permanently."""

    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")

    # Prevent self-deletion
    if user.user_id == current_user.user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete your own account")

    # Delete related records
    db.query(FaceSample).filter(FaceSample.user_id == user_id).delete()
    db.query(LoginLog).filter(LoginLog.user_id == user_id).delete()
    db.query(AuditLog).filter(AuditLog.user_id == user_id).delete()
    db.query(RefreshToken).filter(RefreshToken.user_id == user_id).delete()
    db.delete(user)
    db.commit()

    # Log audit
    audit = AuditLog(user_id=current_user.user_id, action="employee_deleted", details=f"Deleted employee: {user.username}")
    db.add(audit)
    db.commit()

    return {"message": "Employee deleted successfully"}
