"""Permission management API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.permission import Permission
from app.schemas.permission import PermissionCreate, PermissionResponse, PermissionUpdate

router = APIRouter()


@router.get("", response_model=list[PermissionResponse])
def list_permissions(db: Session = Depends(get_db), current_user=Depends(get_current_user)) -> list[Permission]:
    """List permissions."""

    return db.query(Permission).all()


@router.post("", response_model=PermissionResponse, status_code=201)
def create_permission(payload: PermissionCreate, db: Session = Depends(get_db), current_user=Depends(get_current_user)) -> Permission:
    """Create a permission."""

    if db.query(Permission).filter(Permission.name == payload.name).first():
        raise HTTPException(status_code=409, detail="Permission already exists")

    permission = Permission(**payload.model_dump())
    db.add(permission)
    db.commit()
    db.refresh(permission)
    return permission


@router.put("/{permission_id}", response_model=PermissionResponse)
def update_permission(permission_id: int, payload: PermissionUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_user)) -> Permission:
    """Update an existing permission."""

    permission = db.query(Permission).filter(Permission.permission_id == permission_id).first()
    if not permission:
        raise HTTPException(status_code=404, detail="Permission not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(permission, field, value)

    db.commit()
    db.refresh(permission)
    return permission
