from datetime import datetime, date
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth import get_current_user, get_current_admin
from app.database import get_db
from app.models import User, LeaveType, LeaveRequest, LeaveBalance, AuditLog
from app.schemas import (
    LeaveTypeCreate,
    LeaveTypeOut,
    LeaveRequestCreate,
    LeaveRequestReview,
    LeaveRequestOut,
    LeaveBalanceOut,
    LeaveBalanceAdjust,
)
from app.services.leave_service import LeaveService

router = APIRouter(prefix="/api/v1/leaves", tags=["Leave Management"])

ADMIN_ROLES = ["ADMIN", "SUPER_ADMIN", "HR_MANAGER"]


@router.get("/types", response_model=List[LeaveTypeOut])
def list_leave_types(db: Session = Depends(get_db)):
    """List all available leave types."""
    return db.query(LeaveType).filter(LeaveType.is_active == True).order_by(LeaveType.id.asc()).all()


@router.post("/types", response_model=LeaveTypeOut)
def create_leave_type(
    req: LeaveTypeCreate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Add a new company leave type (Admin only)."""
    existing = db.query(LeaveType).filter(
        (LeaveType.name == req.name) | (LeaveType.code == req.code)
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Leave type with name '{req.name}' or code '{req.code}' already exists.",
        )

    lt = LeaveType(
        name=req.name.strip(),
        code=req.code.strip().upper(),
        default_days_per_year=req.default_days_per_year,
        is_paid=req.is_paid,
        description=req.description,
        is_active=req.is_active,
    )
    db.add(lt)
    db.commit()
    db.refresh(lt)

    db.add(AuditLog(
        actor=admin.user_code,
        action="CREATE_LEAVE_TYPE",
        details=f"Created leave type '{lt.name}' ({lt.code}) with {lt.default_days_per_year} days.",
    ))
    db.commit()

    return lt


@router.get("/balances/me", response_model=List[LeaveBalanceOut])
def get_my_balances(
    year: Optional[int] = Query(None, description="Calendar year"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve personal leave balances for the currently authenticated employee."""
    y = year or datetime.now().year
    raw = LeaveService.get_user_balances_summary(db, user.id, y)
    return raw


@router.get("/balances/{user_id}", response_model=List[LeaveBalanceOut])
def get_user_balances(
    user_id: int,
    year: Optional[int] = Query(None, description="Calendar year"),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Retrieve an employee's leave balances (Admin only)."""
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    y = year or datetime.now().year
    return LeaveService.get_user_balances_summary(db, target.id, y)


@router.post("/balances/adjust")
def adjust_leave_balance(
    req: LeaveBalanceAdjust,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Manually adjust allocated leave balance for an employee (Admin only)."""
    LeaveService.ensure_user_balances(db, req.user_id, req.year)
    bal = (
        db.query(LeaveBalance)
        .filter(
            LeaveBalance.user_id == req.user_id,
            LeaveBalance.leave_type_id == req.leave_type_id,
            LeaveBalance.year == req.year,
        )
        .first()
    )
    if not bal:
        raise HTTPException(status_code=404, detail="Leave balance record not found")

    old_alloc = bal.allocated_days
    bal.allocated_days = req.allocated_days

    db.add(AuditLog(
        actor=admin.user_code,
        action="ADJUST_LEAVE_BALANCE",
        details=f"Adjusted leave balance for user ID {req.user_id}: type {req.leave_type_id}, year {req.year} from {old_alloc} to {req.allocated_days} days.",
    ))
    db.commit()

    return {
        "success": True,
        "message": f"Updated allocated leave to {req.allocated_days} days.",
        "remaining_days": bal.remaining_days,
    }


@router.post("/apply")
def apply_leave(
    req: LeaveRequestCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Submit a leave application for current employee."""
    try:
        s_date = datetime.strptime(req.start_date, "%Y-%m-%d").date()
        e_date = datetime.strptime(req.end_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Expected YYYY-MM-DD.")

    success, msg, leave_req = LeaveService.apply_leave(
        db=db,
        user_id=user.id,
        leave_type_id=req.leave_type_id,
        start_date=s_date,
        end_date=e_date,
        reason=req.reason,
        total_days=req.total_days,
    )

    if not success:
        raise HTTPException(status_code=400, detail=msg)

    return {
        "success": True,
        "message": msg,
        "request_id": leave_req.id,
        "status": leave_req.status,
    }


@router.get("/requests")
def list_leave_requests(
    status_filter: Optional[str] = Query(None, alias="status"),
    user_id: Optional[int] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    List leave requests.
    Admins can see all requests; standard employees only see their own.
    """
    query = db.query(LeaveRequest)

    if user.role not in ADMIN_ROLES:
        query = query.filter(LeaveRequest.user_id == user.id)
    elif user_id:
        query = query.filter(LeaveRequest.user_id == user_id)

    if status_filter:
        query = query.filter(LeaveRequest.status == status_filter.upper())

    requests = query.order_by(LeaveRequest.id.desc()).all()

    results = []
    for r in requests:
        u = r.user
        lt = r.leave_type
        rev = r.reviewer
        results.append({
            "id": r.id,
            "user_id": r.user_id,
            "user_code": u.user_code if u else "",
            "full_name": u.full_name if u else "Unknown",
            "department_name": u.department.name if (u and u.department) else "General",
            "leave_type_id": r.leave_type_id,
            "leave_type_name": lt.name if lt else "Unknown",
            "leave_type_code": lt.code if lt else "UNK",
            "is_paid": lt.is_paid if lt else True,
            "start_date": r.start_date.strftime("%Y-%m-%d"),
            "end_date": r.end_date.strftime("%Y-%m-%d"),
            "total_days": r.total_days,
            "reason": r.reason,
            "status": r.status,
            "reviewer_name": rev.full_name if rev else None,
            "review_notes": r.review_notes,
            "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else "",
            "reviewed_at": r.reviewed_at.strftime("%Y-%m-%d %H:%M:%S") if r.reviewed_at else None,
        })

    return results


@router.put("/requests/{request_id}/review")
def review_leave_request(
    request_id: int,
    req: LeaveRequestReview,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Approve or reject a leave application (Admin only)."""
    success, msg = LeaveService.review_leave(
        db=db,
        request_id=request_id,
        reviewer_id=admin.id,
        decision=req.status,
        review_notes=req.review_notes,
    )
    if not success:
        raise HTTPException(status_code=400, detail=msg)

    db.add(AuditLog(
        actor=admin.user_code,
        action=f"LEAVE_{req.status.upper()}",
        details=f"Reviewed leave request #{request_id}: {req.status}. Notes: {req.review_notes or 'None'}",
    ))
    db.commit()

    return {"success": True, "message": msg}
