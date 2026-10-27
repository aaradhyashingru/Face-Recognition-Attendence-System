from datetime import datetime, date, time
from typing import Optional
from fastapi import APIRouter, Request, Depends, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.auth import get_token_from_request, decode_token
from app.config import TEMPLATES_DIR
from app.database import get_db
from app.models import (
    AttendanceLog,
    User,
    Department,
    LeaveType,
    LeaveRequest,
    LeaveBalance,
    Holiday,
    RegularizationRequest,
    Shift,
)
from app.services.payroll_service import PayrollService
from app.services.leave_service import LeaveService
from app.services.holiday_service import HolidayService

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
router = APIRouter(tags=["Web Pages"])

ADMIN_ROLES = ["ADMIN", "SUPER_ADMIN", "HR_MANAGER"]


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
    """Minimalist live-scanning touchless attendance kiosk."""
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
    """Role-based Portal Sign-In."""
    user = optional_current_user(request, db)
    if user:
        if user.role in ADMIN_ROLES:
            return RedirectResponse(url="/admin", status_code=status.HTTP_302_FOUND)
        return RedirectResponse(url="/portal", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse(request=request, name="login.html", context={})


@router.get("/portal", response_class=HTMLResponse)
def employee_portal_page(request: Request, db: Session = Depends(get_db)):
    """Employee Self-Service Portal Dashboard."""
    user = optional_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    today = date.today()
    y = today.year

    # User's leave balances & leave types
    balances = LeaveService.get_user_balances_summary(db, user.id, y)
    leave_types = db.query(LeaveType).filter(LeaveType.is_active == True).all()

    # User's attendance logs for current month
    month_start = datetime.combine(date(y, today.month, 1), time.min)
    month_end = datetime.combine(today, time.max)
    my_logs = (
        db.query(AttendanceLog)
        .filter(
            AttendanceLog.user_id == user.id,
            AttendanceLog.timestamp >= month_start,
            AttendanceLog.timestamp <= month_end,
        )
        .order_by(AttendanceLog.timestamp.desc())
        .all()
    )

    # User's leave requests
    my_leaves = (
        db.query(LeaveRequest)
        .filter(LeaveRequest.user_id == user.id)
        .order_by(LeaveRequest.id.desc())
        .limit(10)
        .all()
    )

    # User's regularization requests
    my_regularizations = (
        db.query(RegularizationRequest)
        .filter(RegularizationRequest.user_id == user.id)
        .order_by(RegularizationRequest.id.desc())
        .limit(10)
        .all()
    )

    # User's personal payroll estimate for current month
    month_start_str = date(y, today.month, 1).strftime("%Y-%m-%d")
    today_str = today.strftime("%Y-%m-%d")
    my_payroll_data = PayrollService.compute_payroll(
        db, start_date=month_start_str, end_date=today_str, user_id=user.id
    )
    my_payroll = my_payroll_data["records"][0] if my_payroll_data["records"] else None

    # Shift details
    shift_name = "General Day Shift"
    if getattr(user, "shift", None):
        shift_name = user.shift.name
    elif user.department and getattr(user.department, "shift", None):
        shift_name = user.department.shift.name

    # Upcoming holidays
    upcoming_holidays = HolidayService.get_upcoming_holidays(db, limit=3)

    return templates.TemplateResponse(
        request=request,
        name="portal_dashboard.html",
        context={
            "current_user": user,
            "balances": balances,
            "leave_types": leave_types,
            "my_logs": my_logs,
            "my_leaves": my_leaves,
            "my_regularizations": my_regularizations,
            "my_payroll": my_payroll,
            "shift_name": shift_name,
            "upcoming_holidays": upcoming_holidays,
            "today_date": datetime.now().strftime("%A, %d %B %Y"),
            "today_str": today_str,
        },
    )


@router.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    """Role-Based Admin Dashboard with tracking and payroll metrics."""
    user = optional_current_user(request, db)
    if not user or user.role not in ADMIN_ROLES:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    # Compute Live Attendance Tracking Metrics
    today_start = datetime.combine(date.today(), time.min)
    total_users = db.query(User).filter(User.is_active == True).count()

    # Unique users who punched today
    present_today = (
        db.query(func.count(func.distinct(AttendanceLog.user_id)))
        .filter(AttendanceLog.timestamp >= today_start)
        .scalar()
        or 0
    )

    late_count = (
        db.query(func.count(func.distinct(AttendanceLog.user_id)))
        .filter(AttendanceLog.timestamp >= today_start, AttendanceLog.status == "LATE")
        .scalar()
        or 0
    )

    attendance_rate = (
        round((present_today / total_users * 100) if total_users > 0 else 0.0, 1)
    )

    # Recent 10 Punches
    recent_punches = (
        db.query(AttendanceLog)
        .filter(AttendanceLog.timestamp >= today_start)
        .order_by(AttendanceLog.timestamp.desc())
        .limit(10)
        .all()
    )

    # Payroll Quick Overview for Current Month
    payroll_summary = PayrollService.compute_payroll(db)
    departments = db.query(Department).all()

    # Phase 1 Operational Pipeline Metrics
    pending_leaves_count = (
        db.query(LeaveRequest).filter(LeaveRequest.status == "PENDING").count()
    )
    pending_reg_count = (
        db.query(RegularizationRequest).filter(RegularizationRequest.status == "PENDING").count()
    )
    upcoming_holiday = (
        db.query(Holiday)
        .filter(Holiday.holiday_date >= date.today())
        .order_by(Holiday.holiday_date.asc())
        .first()
    )
    total_shifts_count = db.query(Shift).filter(Shift.is_active == True).count()

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
            "payroll_summary": payroll_summary["summary"],
            "payroll_records": payroll_summary["records"][:5],  # top 5 preview
            "departments": departments,
            "pending_leaves_count": pending_leaves_count,
            "pending_reg_count": pending_reg_count,
            "upcoming_holiday": upcoming_holiday,
            "total_shifts_count": total_shifts_count,
            "today_date": datetime.now().strftime("%A, %d %B %Y"),
        },
    )


@router.get("/admin/leaves", response_class=HTMLResponse)
def admin_leaves_page(request: Request, db: Session = Depends(get_db)):
    """Leave & Attendance Regularization Management Dashboard."""
    user = optional_current_user(request, db)
    if not user or user.role not in ADMIN_ROLES:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    pending_leaves = (
        db.query(LeaveRequest)
        .filter(LeaveRequest.status == "PENDING")
        .order_by(LeaveRequest.id.desc())
        .all()
    )
    all_leaves = (
        db.query(LeaveRequest)
        .order_by(LeaveRequest.id.desc())
        .limit(100)
        .all()
    )
    pending_reg = (
        db.query(RegularizationRequest)
        .filter(RegularizationRequest.status == "PENDING")
        .order_by(RegularizationRequest.id.desc())
        .all()
    )
    all_reg = (
        db.query(RegularizationRequest)
        .order_by(RegularizationRequest.id.desc())
        .limit(100)
        .all()
    )
    leave_types = db.query(LeaveType).all()
    users = db.query(User).filter(User.is_active == True).order_by(User.full_name.asc()).all()

    return templates.TemplateResponse(
        request=request,
        name="admin_leaves.html",
        context={
            "current_user": user,
            "pending_leaves": pending_leaves,
            "all_leaves": all_leaves,
            "pending_reg": pending_reg,
            "all_reg": all_reg,
            "leave_types": leave_types,
            "users": users,
            "today_date": datetime.now().strftime("%A, %d %B %Y"),
        },
    )


@router.get("/admin/holidays", response_class=HTMLResponse)
def admin_holidays_page(request: Request, db: Session = Depends(get_db)):
    """Corporate & Statutory Holiday Calendar."""
    user = optional_current_user(request, db)
    if not user or user.role not in ADMIN_ROLES:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    holidays = db.query(Holiday).order_by(Holiday.holiday_date.asc()).all()
    upcoming = HolidayService.get_upcoming_holidays(db, limit=10)

    return templates.TemplateResponse(
        request=request,
        name="admin_holidays.html",
        context={
            "current_user": user,
            "holidays": holidays,
            "upcoming": upcoming,
            "today_date": datetime.now().strftime("%A, %d %B %Y"),
        },
    )


@router.get("/admin/shifts", response_class=HTMLResponse)
def admin_shifts_page(request: Request, db: Session = Depends(get_db)):
    """Enterprise Shift & Rostering Management."""
    user = optional_current_user(request, db)
    if not user or user.role not in ADMIN_ROLES:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    shifts = db.query(Shift).all()
    departments = db.query(Department).all()
    users = db.query(User).filter(User.is_active == True).order_by(User.full_name.asc()).all()

    return templates.TemplateResponse(
        request=request,
        name="admin_shifts.html",
        context={
            "current_user": user,
            "shifts": shifts,
            "departments": departments,
            "users": users,
            "today_date": datetime.now().strftime("%A, %d %B %Y"),
        },
    )


@router.get("/admin/users", response_class=HTMLResponse)
def admin_users_page(request: Request, db: Session = Depends(get_db)):
    """User Management & Face Enrollment Page."""
    user = optional_current_user(request, db)
    if not user or user.role not in ADMIN_ROLES:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    users = db.query(User).filter(User.is_active == True).order_by(User.id.desc()).all()
    departments = db.query(Department).all()
    shifts = db.query(Shift).filter(Shift.is_active == True).all()

    return templates.TemplateResponse(
        request=request,
        name="admin_users.html",
        context={
            "current_user": user,
            "users": users,
            "departments": departments,
            "shifts": shifts,
            "today_date": datetime.now().strftime("%A, %d %B %Y"),
        },
    )


@router.get("/admin/reports", response_class=HTMLResponse)
def admin_reports_page(request: Request, db: Session = Depends(get_db)):
    """Attendance Tracking & Audit Logs."""
    user = optional_current_user(request, db)
    if not user or user.role not in ADMIN_ROLES:
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


@router.get("/admin/payroll", response_class=HTMLResponse)
def admin_payroll_page(request: Request, db: Session = Depends(get_db)):
    """Dedicated Workforce Payroll & Work Hours Management Dashboard."""
    user = optional_current_user(request, db)
    if not user or user.role not in ADMIN_ROLES:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    departments = db.query(Department).all()
    today_str = date.today().strftime("%Y-%m-%d")
    month_start_str = date(date.today().year, date.today().month, 1).strftime("%Y-%m-%d")

    payroll_data = PayrollService.compute_payroll(
        db, start_date=month_start_str, end_date=today_str
    )

    return templates.TemplateResponse(
        request=request,
        name="admin_payroll.html",
        context={
            "current_user": user,
            "departments": departments,
            "payroll_data": payroll_data,
            "month_start_str": month_start_str,
            "today_str": today_str,
            "today_date": datetime.now().strftime("%A, %d %B %Y"),
        },
    )
