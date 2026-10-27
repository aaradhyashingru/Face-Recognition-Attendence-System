from datetime import datetime, date
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, EmailStr


# ===================== Shift Schemas =====================
class ShiftBase(BaseModel):
    name: str
    code: str
    start_time: str = "09:00:00"
    end_time: str = "17:00:00"
    grace_period_mins: int = 15
    is_night_shift: bool = False
    break_duration_mins: int = 60
    is_active: bool = True


class ShiftCreate(ShiftBase):
    pass


class ShiftUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    grace_period_mins: Optional[int] = None
    is_night_shift: Optional[bool] = None
    break_duration_mins: Optional[int] = None
    is_active: Optional[bool] = None


class ShiftOut(ShiftBase):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


# ===================== Department Schemas =====================
class DepartmentBase(BaseModel):
    name: str
    shift_start: str = "09:00:00"
    shift_end: str = "17:00:00"
    grace_period_mins: int = 15
    shift_id: Optional[int] = None


class DepartmentCreate(DepartmentBase):
    pass


class DepartmentOut(DepartmentBase):
    id: int
    shift_name: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


# ===================== User Schemas =====================
class UserBase(BaseModel):
    user_code: str
    full_name: str
    email: Optional[str] = None
    department_id: Optional[int] = None
    shift_id: Optional[int] = None
    role: str = "USER"
    designation: Optional[str] = "Staff"
    hourly_rate: Optional[float] = 25.0
    grace_period_mins: Optional[int] = None  # Custom grace time override (mins)
    is_active: bool = True


class UserCreate(UserBase):
    password: Optional[str] = None


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    department_id: Optional[int] = None
    shift_id: Optional[int] = None
    designation: Optional[str] = None
    hourly_rate: Optional[float] = None
    grace_period_mins: Optional[int] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None


class UserOut(UserBase):
    id: int
    created_at: datetime
    has_biometric: bool = False
    department_name: Optional[str] = None
    shift_name: Optional[str] = None
    effective_grace_mins: Optional[int] = 15
    model_config = ConfigDict(from_attributes=True)


# ===================== Biometrics & Kiosk Schemas =====================
class FaceEnrollRequest(BaseModel):
    user_code: str
    full_name: str
    email: Optional[str] = None
    department_id: Optional[int] = None
    shift_id: Optional[int] = None
    designation: Optional[str] = "Staff"
    hourly_rate: Optional[float] = 25.0
    grace_period_mins: Optional[int] = None  # Custom grace time override (mins)
    role: Optional[str] = "USER"
    frames: List[str]  # List of base64 data URLs captured by the browser


class FaceRecognizeRequest(BaseModel):
    frame: str  # Base64 data URL from browser webcam canvas


class FaceRecognizeResponse(BaseModel):
    status: str  # "SUCCESS", "COOLDOWN", "UNKNOWN", "NO_FACE", "SPOOF_DETECTED", "ERROR"
    user_code: Optional[str] = None
    full_name: Optional[str] = None
    department: Optional[str] = None
    punch_type: Optional[str] = None  # "IN", "OUT"
    punch_time: Optional[str] = None
    attendance_status: Optional[str] = None  # "ON_TIME", "LATE"
    confidence: float = 0.0
    bbox: Optional[List[int]] = None  # [x, y, w, h]
    liveness_score: float = 0.0
    message: str = ""


class AttendanceLogOut(BaseModel):
    id: int
    user_id: int
    user_code: str
    full_name: str
    department_name: Optional[str] = None
    timestamp: datetime
    punch_type: str
    status: str
    confidence_score: float
    device_id: str
    model_config = ConfigDict(from_attributes=True)


# ===================== Auth Schemas =====================
class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_code: str
    full_name: str
    role: str


class ManualPunchRequest(BaseModel):
    user_id: int
    punch_type: str = "IN"  # "IN", "OUT", or "BOTH"
    custom_timestamp: Optional[str] = None  # e.g., "2026-10-26T09:00" or "2026-10-26 09:00:00"
    out_timestamp: Optional[str] = None  # Check-out timestamp when punch_type == "BOTH"
    status: str = "ON_TIME"  # "ON_TIME", "LATE", "HALF_DAY", "EXCUSED"
    notes: Optional[str] = None


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


# ===================== Leave Management Schemas =====================
class LeaveTypeBase(BaseModel):
    name: str
    code: str
    default_days_per_year: float = 12.0
    is_paid: bool = True
    description: Optional[str] = None
    is_active: bool = True


class LeaveTypeCreate(LeaveTypeBase):
    pass


class LeaveTypeOut(LeaveTypeBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


class LeaveBalanceOut(BaseModel):
    id: int
    user_id: int
    leave_type_id: int
    leave_type_name: str
    leave_type_code: str
    is_paid: bool
    year: int
    allocated_days: float
    used_days: float
    remaining_days: float
    model_config = ConfigDict(from_attributes=True)


class LeaveBalanceAdjust(BaseModel):
    user_id: int
    leave_type_id: int
    year: int
    allocated_days: float


class LeaveRequestCreate(BaseModel):
    leave_type_id: int
    start_date: str  # "YYYY-MM-DD"
    end_date: str    # "YYYY-MM-DD"
    total_days: float = 1.0
    reason: str


class LeaveRequestReview(BaseModel):
    status: str  # "APPROVED", "REJECTED"
    review_notes: Optional[str] = None


class LeaveRequestOut(BaseModel):
    id: int
    user_id: int
    user_code: str
    full_name: str
    department_name: Optional[str] = None
    leave_type_id: int
    leave_type_name: str
    leave_type_code: str
    is_paid: bool
    start_date: date
    end_date: date
    total_days: float
    reason: str
    status: str
    reviewer_name: Optional[str] = None
    review_notes: Optional[str] = None
    created_at: datetime
    reviewed_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


# ===================== Holiday Calendar Schemas =====================
class HolidayBase(BaseModel):
    name: str
    holiday_date: str  # "YYYY-MM-DD"
    holiday_type: str = "NATIONAL"  # "NATIONAL", "COMPANY", "OPTIONAL"
    description: Optional[str] = None
    is_recurring: bool = False


class HolidayCreate(HolidayBase):
    pass


class HolidayOut(BaseModel):
    id: int
    name: str
    holiday_date: date
    holiday_type: str
    description: Optional[str] = None
    is_recurring: bool = False
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


# ===================== Attendance Regularization Schemas =====================
class RegularizationCreate(BaseModel):
    attendance_date: str  # "YYYY-MM-DD"
    requested_punch_in: Optional[str] = None   # "HH:MM:SS" or "HH:MM"
    requested_punch_out: Optional[str] = None  # "HH:MM:SS" or "HH:MM"
    reason: str


class RegularizationReview(BaseModel):
    status: str  # "APPROVED", "REJECTED"
    review_notes: Optional[str] = None


class RegularizationOut(BaseModel):
    id: int
    user_id: int
    user_code: str
    full_name: str
    department_name: Optional[str] = None
    attendance_date: date
    requested_punch_in: Optional[str] = None
    requested_punch_out: Optional[str] = None
    reason: str
    status: str
    reviewer_name: Optional[str] = None
    review_notes: Optional[str] = None
    created_at: datetime
    reviewed_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)
