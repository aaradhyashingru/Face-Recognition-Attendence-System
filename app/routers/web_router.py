from datetime import datetime, date, time
from fastapi import APIRouter, Request, Depends, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.auth import get_token_from_request, decode_token
from app.config import TEMPLATES_DIR
from app.database import get_db
from app.models import AttendanceLog, User, Department

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
router = APIRouter(tags=["Web Pages"])


def optional_current_user(request: Request, db: Session) -> User | None:
    """Helper to get logged-in user from cookie without throwing 401."""
    token = get_token_from_request(request)
    if not token:
        return None
    payload = decode_token(token)
    if not payload:
        return None
    user_code = payload.get("sub")
    if not user_code:
        return None
    return db.query(User).filter(User.user_code == user_code, User.is_active == True).first()


@router.get("/", response_class=RedirectResponse)
def root():
    """Default entry point redirects to Kiosk Mode."""
    return RedirectResponse(url="/kiosk", status_code=status.HTTP_302_FOUND)


@router.get("/kiosk", response_class=HTMLResponse)
def kiosk_page(request: Request, db: Session = Depends(get_db)):
    """Fullscreen Touchless Neomorphic Attendance Terminal."""
    user = optional_current_user(request, db)
    return templates.TemplateResponse(
        request=request,
        name="kiosk.html",
        context={
            "current_user": user,
            "today_date": datetime.now().strftime("%A, %d %B %Y"),
        },
    )


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, db: Session = Depends(get_db)):
    """Neomorphic Login Interface."""
    user = optional_current_user(request, db)
    if user and user.role == "ADMIN":
        return RedirectResponse(url="/admin", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse(request=request, name="login.html", context={})


@router.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    """Admin Analytics & KPI Dashboard."""
    user = optional_current_user(request, db)
    if not user or user.role != "ADMIN":
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    # Compute Live Metrics
    today_start = datetime.combine(date.today(), time.min)
    total_users = db.query(User).filter(User.is_active == True).count()
    
    # Unique users who punched today
    present_today = (
        db.query(AttendanceLog.user_id)
        .filter(AttendanceLog.timestamp >= today_start)
        .distinct()
        .count()
    )

    late_count = (
        db.query(AttendanceLog.user_id)
        .filter(AttendanceLog.timestamp >= today_start, AttendanceLog.status == "LATE")
        .distinct()
        .count()
    )

    attendance_rate = round((present_today / total_users * 100) if total_users > 0 else 0.0, 1)

    # Recent 10 Punches
    recent_punches = (
        db.query(AttendanceLog)
        .filter(AttendanceLog.timestamp >= today_start)
        .order_by(AttendanceLog.timestamp.desc())
        .limit(10)
        .all()
    )

    return templates.TemplateResponse(
        request=request,
        name="admin_dashboard.html",
        context={
            "current_user": user,
            "total_users": total_users,
            "present_today": present_today,
            "late_count": late_count,
            "attendance_rate": attendance_rate,
            "recent_punches": recent_punches,
            "today_date": datetime.now().strftime("%A, %d %B %Y"),
        },
    )


@router.get("/admin/users", response_class=HTMLResponse)
def admin_users_page(request: Request, db: Session = Depends(get_db)):
    """User Management & Face Enrollment Page."""
    user = optional_current_user(request, db)
    if not user or user.role != "ADMIN":
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    users = db.query(User).filter(User.is_active == True).order_by(User.id.desc()).all()
    departments = db.query(Department).all()

    return templates.TemplateResponse(
        request=request,
        name="admin_users.html",
        context={
            "current_user": user,
            "users": users,
            "departments": departments,
            "today_date": datetime.now().strftime("%A, %d %B %Y"),
        },
    )


@router.get("/admin/reports", response_class=HTMLResponse)
def admin_reports_page(request: Request, db: Session = Depends(get_db)):
    """Attendance Reporting & Export Page."""
    user = optional_current_user(request, db)
    if not user or user.role != "ADMIN":
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    departments = db.query(Department).all()
    today_str = date.today().strftime("%Y-%m-%d")

    return templates.TemplateResponse(
        request=request,
        name="admin_reports.html",
        context={
            "current_user": user,
            "departments": departments,
            "today_str": today_str,
            "today_date": datetime.now().strftime("%A, %d %B %Y"),
        },
    )
