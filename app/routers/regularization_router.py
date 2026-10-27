from datetime import datetime, date
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth import get_current_user, get_current_admin
from app.database import get_db
from app.models import RegularizationRequest, User, AuditLog
from app.schemas import RegularizationCreate, RegularizationReview, RegularizationOut
from app.services.regularization_service import RegularizationService

router = APIRouter(prefix="/api/v1/regularizations", tags=["Attendance Regularization"])

ADMIN_ROLES = ["ADMIN", "SUPER_ADMIN", "HR_MANAGER"]


@router.post("/")
def create_regularization(
    req: RegularizationCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Submit an attendance regularization request for a missed or incorrect punch."""
    try:
        att_date = datetime.strptime(req.attendance_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Expected YYYY-MM-DD.")

    success, msg, reg = RegularizationService.create_request(
        db=db,
        user_id=user.id,
        attendance_date=att_date,
        requested_punch_in=req.requested_punch_in,
        requested_punch_out=req.requested_punch_out,
        reason=req.reason,
    )

    if not success:
        raise HTTPException(status_code=400, detail=msg)

    return {
        "success": True,
        "message": msg,
        "request_id": reg.id,
        "status": reg.status,
    }


@router.get("/")
def list_regularization_requests(
    status_filter: Optional[str] = Query(None, alias="status"),
    user_id: Optional[int] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    List regularization requests.
    Admins see all; employees see only their own.
    """
    query = db.query(RegularizationRequest)

    if user.role not in ADMIN_ROLES:
        query = query.filter(RegularizationRequest.user_id == user.id)
    elif user_id:
        query = query.filter(RegularizationRequest.user_id == user_id)

    if status_filter:
        query = query.filter(RegularizationRequest.status == status_filter.upper())

    requests = query.order_by(RegularizationRequest.id.desc()).all()

    results = []
    for r in requests:
        u = r.user
        rev = r.reviewer
        results.append({
            "id": r.id,
            "user_id": r.user_id,
            "user_code": u.user_code if u else "",
            "full_name": u.full_name if u else "Unknown",
            "department_name": u.department.name if (u and u.department) else "General",
            "attendance_date": r.attendance_date.strftime("%Y-%m-%d"),
            "requested_punch_in": r.requested_punch_in,
            "requested_punch_out": r.requested_punch_out,
            "reason": r.reason,
            "status": r.status,
            "reviewer_name": rev.full_name if rev else None,
            "review_notes": r.review_notes,
            "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else "",
            "reviewed_at": r.reviewed_at.strftime("%Y-%m-%d %H:%M:%S") if r.reviewed_at else None,
        })

    return results


@router.put("/{request_id}/review")
def review_regularization(
    request_id: int,
    req: RegularizationReview,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Approve or reject an attendance regularization request (Admin only)."""
    success, msg = RegularizationService.review_request(
        db=db,
        request_id=request_id,
        reviewer_id=admin.id,
        decision=req.status,
        review_notes=req.review_notes,
    )

    if not success:
        raise HTTPException(status_code=400, detail=msg)

    return {"success": True, "message": msg}
