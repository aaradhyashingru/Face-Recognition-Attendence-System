from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.database import get_db
from app.models import Shift, User, Department, AuditLog
from app.schemas import ShiftCreate, ShiftUpdate, ShiftOut

router = APIRouter(prefix="/api/v1/shifts", tags=["Shift Management"])


class ShiftAssignRequest(BaseModel):
    shift_id: int
    user_id: Optional[int] = None
    department_id: Optional[int] = None


@router.get("/", response_model=List[ShiftOut])
def list_shifts(db: Session = Depends(get_db)):
    """List all corporate shifts."""
    return db.query(Shift).filter(Shift.is_active == True).order_by(Shift.id.asc()).all()


@router.post("/", response_model=ShiftOut)
def create_shift(
    req: ShiftCreate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Create a new work shift (Admin only)."""
    existing = db.query(Shift).filter(
        (Shift.name == req.name) | (Shift.code == req.code)
    ).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Shift with name '{req.name}' or code '{req.code}' already exists.",
        )

    shift = Shift(
        name=req.name.strip(),
        code=req.code.strip().upper(),
        start_time=req.start_time.strip(),
        end_time=req.end_time.strip(),
        grace_period_mins=req.grace_period_mins,
        is_night_shift=req.is_night_shift,
        break_duration_mins=req.break_duration_mins,
        is_active=req.is_active,
    )
    db.add(shift)
    db.commit()
    db.refresh(shift)

    db.add(AuditLog(
        actor=admin.user_code,
        action="CREATE_SHIFT",
        details=f"Created shift '{shift.name}' ({shift.code}) {shift.start_time}-{shift.end_time}.",
    ))
    db.commit()

    return shift


@router.put("/{shift_id}", response_model=ShiftOut)
def update_shift(
    shift_id: int,
    req: ShiftUpdate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Update shift parameters (Admin only)."""
    shift = db.query(Shift).filter(Shift.id == shift_id).first()
    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")

    if req.name is not None:
        shift.name = req.name.strip()
    if req.code is not None:
        shift.code = req.code.strip().upper()
    if req.start_time is not None:
        shift.start_time = req.start_time.strip()
    if req.end_time is not None:
        shift.end_time = req.end_time.strip()
    if req.grace_period_mins is not None:
        shift.grace_period_mins = req.grace_period_mins
    if req.is_night_shift is not None:
        shift.is_night_shift = req.is_night_shift
    if req.break_duration_mins is not None:
        shift.break_duration_mins = req.break_duration_mins
    if req.is_active is not None:
        shift.is_active = req.is_active

    db.add(AuditLog(
        actor=admin.user_code,
        action="UPDATE_SHIFT",
        details=f"Updated shift #{shift.id} ({shift.name}).",
    ))
    db.commit()
    db.refresh(shift)

    return shift


@router.post("/assign")
def assign_shift(
    req: ShiftAssignRequest,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Assign a shift to a specific employee or department (Admin only)."""
    shift = db.query(Shift).filter(Shift.id == req.shift_id).first()
    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")

    assigned_to = []
    if req.user_id:
        user = db.query(User).filter(User.id == req.user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        user.shift_id = shift.id
        assigned_to.append(f"User {user.user_code} ({user.full_name})")

    if req.department_id:
        dept = db.query(Department).filter(Department.id == req.department_id).first()
        if not dept:
            raise HTTPException(status_code=404, detail="Department not found")
        dept.shift_id = shift.id
        assigned_to.append(f"Department {dept.name}")

    if not assigned_to:
        raise HTTPException(status_code=400, detail="Must specify either user_id or department_id.")

    msg = f"Assigned shift '{shift.name}' to: {', '.join(assigned_to)}."
    db.add(AuditLog(
        actor=admin.user_code,
        action="ASSIGN_SHIFT",
        details=msg,
    ))
    db.commit()

    return {"success": True, "message": msg}
