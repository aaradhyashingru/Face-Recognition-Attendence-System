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
    is_active: bool = True


class UserCreate(UserBase):
    password: Optional[str] = None


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    department_id: Optional[int] = None
    is_active: Optional[bool] = None


class UserOut(UserBase):
    id: int
    created_at: datetime
    has_biometric: bool = False
    department_name: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class FaceEnrollRequest(BaseModel):
    user_code: str
    full_name: str
    email: Optional[str] = None
    department_id: Optional[int] = None
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
    punch_type: str = "IN"
    status: str = "ON_TIME"
    notes: Optional[str] = None
