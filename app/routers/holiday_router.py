from datetime import datetime, date
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.database import get_db
from app.models import Holiday, User, AuditLog
from app.schemas import HolidayCreate, HolidayOut
from app.services.holiday_service import HolidayService

router = APIRouter(prefix="/api/v1/holidays", tags=["Holiday Calendar"])


@router.get("/", response_model=List[HolidayOut])
def list_holidays(
    year: Optional[int] = Query(None, description="Calendar year"),
    db: Session = Depends(get_db),
):
    """List all company & national holidays."""
    query = db.query(Holiday)
    if year:
        query = query.filter(
            Holiday.holiday_date >= date(year, 1, 1),
            Holiday.holiday_date <= date(year, 12, 31),
        )
    return query.order_by(Holiday.holiday_date.asc()).all()


@router.get("/upcoming", response_model=List[HolidayOut])
def get_upcoming_holidays(
    limit: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
):
    """Retrieve next upcoming holidays."""
    return HolidayService.get_upcoming_holidays(db, limit=limit)


@router.post("/", response_model=HolidayOut)
def create_holiday(
    req: HolidayCreate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Add a new company or national holiday (Admin only)."""
    try:
        h_date = datetime.strptime(req.holiday_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Expected YYYY-MM-DD.")

    existing = db.query(Holiday).filter(Holiday.holiday_date == h_date).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"A holiday '{existing.name}' is already scheduled on {h_date}.",
        )

    holiday = Holiday(
        name=req.name.strip(),
        holiday_date=h_date,
        holiday_type=req.holiday_type.upper().strip(),
        description=req.description,
        is_recurring=req.is_recurring,
    )
    db.add(holiday)
    db.commit()
    db.refresh(holiday)

    db.add(AuditLog(
        actor=admin.user_code,
        action="CREATE_HOLIDAY",
        details=f"Added holiday '{holiday.name}' on {h_date} ({holiday.holiday_type}).",
    ))
    db.commit()

    return holiday


@router.delete("/{holiday_id}")
def delete_holiday(
    holiday_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Delete a scheduled holiday (Admin only)."""
    holiday = db.query(Holiday).filter(Holiday.id == holiday_id).first()
    if not holiday:
        raise HTTPException(status_code=404, detail="Holiday not found")

    h_name = holiday.name
    h_date = holiday.holiday_date
    db.delete(holiday)

    db.add(AuditLog(
        actor=admin.user_code,
        action="DELETE_HOLIDAY",
        details=f"Deleted holiday '{h_name}' scheduled on {h_date}.",
    ))
    db.commit()

    return {"success": True, "message": f"Holiday '{h_name}' removed."}
