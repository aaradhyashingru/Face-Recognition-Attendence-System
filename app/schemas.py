from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, EmailStr


class DepartmentBase(BaseModel):
    name: str
    shift_start: str = "09:00:00"
    shift_end: str = "17:00:00"
    grace_period_mins: int = 15


class DepartmentCreate(DepartmentBase):
    pass


class DepartmentOut(DepartmentBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


class UserBase(BaseModel):
    user_code: str
    full_name: str
    email: Optional[str] = None
    department_id: Optional[int] = None
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
    effective_grace_mins: Optional[int] = 15
    model_config = ConfigDict(from_attributes=True)


class FaceEnrollRequest(BaseModel):
    user_code: str
    full_name: str
    email: Optional[str] = None
    department_id: Optional[int] = None
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
