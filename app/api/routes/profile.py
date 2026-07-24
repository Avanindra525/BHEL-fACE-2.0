"""Profile API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.security import hash_password, verify_password
from app.models.department import Department
from app.models.user import User
from app.models.password_history import PasswordHistory
from datetime import datetime

router = APIRouter()


class ProfileUpdateRequest(BaseModel):
    full_name: str | None = None
    email: str | None = None
    department_id: int | None = None
    bio: str | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8)
    confirm_password: str = Field(min_length=8)


@router.get("", response_model=dict[str, object])
def get_profile(current_user: User = Depends(get_current_user)) -> dict[str, object]:
    """Return the current user's profile with full details."""

    return {
        "username": current_user.username,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "staff_number": current_user.staff_number,
        "bio": current_user.bio,
        "role": current_user.role.name if current_user.role else None,
        "department_id": current_user.department_id,
        "department": current_user.department.name if current_user.department else None,
        "face_registered": current_user.face_registered == "Y",
        "profile_completed": current_user.profile_completed == "Y",
        "is_active": current_user.is_active == "Y",
        "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
        "updated_at": current_user.updated_at.isoformat() if current_user.updated_at else None,
    }


@router.put("")
def update_profile(
    payload: ProfileUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Update the current user's profile fields."""

    if payload.full_name is not None:
        current_user.full_name = payload.full_name
    if payload.email is not None:
        current_user.email = payload.email
    if payload.bio is not None:
        current_user.bio = payload.bio
    if payload.department_id is not None:
        department = db.query(Department).filter(
            Department.department_id == payload.department_id,
            Department.is_active == "Y",
        ).first()
        if not department:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid department")
        current_user.department_id = department.department_id

    current_user.profile_completed = "Y"
    current_user.updated_at = datetime.utcnow()
    db.commit()
    return {"message": "Profile updated successfully"}


@router.put("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Change the current user's password."""

    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")

    if payload.new_password != payload.confirm_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Passwords do not match")

    # Check password history (last 5 passwords)
    recent_passwords = db.query(PasswordHistory).filter(
        PasswordHistory.user_id == current_user.user_id
    ).order_by(PasswordHistory.created_at.desc()).limit(5).all()

    for entry in recent_passwords:
        if verify_password(payload.new_password, entry.password_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot reuse a recent password",
            )

    # Store old password in history
    history_entry = PasswordHistory(
        user_id=current_user.user_id,
        password_hash=current_user.password_hash,
    )
    db.add(history_entry)

    # Update password
    current_user.password_hash = hash_password(payload.new_password)
    current_user.password_changed_at = datetime.utcnow()
    current_user.updated_at = datetime.utcnow()
    db.commit()
    return {"message": "Password changed successfully"}
