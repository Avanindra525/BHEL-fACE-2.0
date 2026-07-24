"""Department management API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.department import Department
from app.schemas.department import DepartmentCreate, DepartmentResponse, DepartmentUpdate

router = APIRouter()


@router.get("", response_model=list[DepartmentResponse])
def list_departments(db: Session = Depends(get_db), current_user=Depends(get_current_user)) -> list[Department]:
    """List departments."""

    return db.query(Department).all()


@router.post("", response_model=DepartmentResponse, status_code=status.HTTP_201_CREATED)
def create_department(payload: DepartmentCreate, db: Session = Depends(get_db), current_user=Depends(get_current_user)) -> Department:
    """Create a department."""

    if db.query(Department).filter(Department.name == payload.name).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Department already exists")

    department = Department(**payload.model_dump())
    db.add(department)
    db.commit()
    db.refresh(department)
    return department


@router.put("/{department_id}", response_model=DepartmentResponse)
def update_department(department_id: int, payload: DepartmentUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_user)) -> Department:
    """Update an existing department."""

    department = db.query(Department).filter(Department.department_id == department_id).first()
    if not department:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(department, field, value)

    db.commit()
    db.refresh(department)
    return department
