import json
from datetime import datetime, timezone, date
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Boolean,
    DateTime,
    Date,
    ForeignKey,
    Text,
)
from sqlalchemy.orm import relationship
from app.database import Base


def utc_now():
    return datetime.now(timezone.utc)


class Shift(Base):
    __tablename__ = "shifts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True)  # e.g., "General Shift", "Morning Shift", "Night Shift"
    code = Column(String(20), unique=True, nullable=False, index=True)  # e.g., "GEN", "MORN", "NIGHT"
    start_time = Column(String(10), default="09:00:00", nullable=False)  # "HH:MM:SS"
    end_time = Column(String(10), default="17:00:00", nullable=False)    # "HH:MM:SS"
    grace_period_mins = Column(Integer, default=15, nullable=False)
    is_night_shift = Column(Boolean, default=False, nullable=False)  # Crosses midnight (e.g., 22:00 to 06:00)
    break_duration_mins = Column(Integer, default=60, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)


class Department(Base):
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    shift_start = Column(String(10), default="09:00:00")
    shift_end = Column(String(10), default="17:00:00")
    grace_period_mins = Column(Integer, default=15)
    shift_id = Column(Integer, ForeignKey("shifts.id"), nullable=True)

    shift = relationship("Shift", foreign_keys=[shift_id])
    users = relationship("User", back_populates="department")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    user_code = Column(String(50), unique=True, nullable=False, index=True)  # Roll / Employee ID
    full_name = Column(String(150), nullable=False, index=True)
    email = Column(String(150), unique=True, nullable=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    shift_id = Column(Integer, ForeignKey("shifts.id"), nullable=True)
    role = Column(String(20), default="USER", nullable=False)  # "ADMIN", "SUPER_ADMIN", "HR_MANAGER", "USER"
    designation = Column(String(100), default="Staff", nullable=True)
    hourly_rate = Column(Float, default=25.0, nullable=True)
    grace_period_mins = Column(Integer, default=None, nullable=True)  # Custom grace time override (minutes)
    password_hash = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    department = relationship("Department", back_populates="users")
    shift = relationship("Shift", foreign_keys=[shift_id])
    embeddings = relationship(
        "FaceEmbedding", back_populates="user", cascade="all, delete-orphan"
    )
    attendance_logs = relationship(
        "AttendanceLog", back_populates="user", cascade="all, delete-orphan"
    )
    leave_balances = relationship(
        "LeaveBalance", back_populates="user", cascade="all, delete-orphan"
    )
    leave_requests = relationship(
        "LeaveRequest",
        foreign_keys="[LeaveRequest.user_id]",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    regularization_requests = relationship(
        "RegularizationRequest",
        foreign_keys="[RegularizationRequest.user_id]",
        back_populates="user",
        cascade="all, delete-orphan",
    )


class FaceEmbedding(Base):
    __tablename__ = "face_embeddings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    embedding_json = Column(Text, nullable=False)  # JSON-encoded 128-element float list
    quality_score = Column(Float, default=1.0)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    user = relationship("User", back_populates="embeddings")

    def get_vector(self) -> list[float]:
        return json.loads(self.embedding_json)

    def set_vector(self, vector: list[float]):
        self.embedding_json = json.dumps(vector)


class AttendanceLog(Base):
    __tablename__ = "attendance_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    timestamp = Column(DateTime, default=datetime.now, nullable=False, index=True)
    punch_type = Column(String(10), default="IN", nullable=False)  # "IN", "OUT"
    status = Column(String(20), default="ON_TIME", nullable=False)  # "ON_TIME", "LATE", "HALF_DAY", "EXCUSED", "ON_LEAVE", "HOLIDAY", "REGULARIZED"
    confidence_score = Column(Float, default=1.0)
    device_id = Column(String(50), default="KIOSK-01")

    user = relationship("User", back_populates="attendance_logs")


class LeaveType(Base):
    __tablename__ = "leave_types"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True)  # e.g., "Casual Leave", "Sick Leave", "Paid Leave", "Unpaid Leave"
    code = Column(String(20), unique=True, nullable=False, index=True)  # "CL", "SL", "PL", "UL"
    default_days_per_year = Column(Float, default=12.0, nullable=False)
    is_paid = Column(Boolean, default=True, nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    balances = relationship("LeaveBalance", back_populates="leave_type", cascade="all, delete-orphan")
    requests = relationship("LeaveRequest", back_populates="leave_type")


class LeaveBalance(Base):
    __tablename__ = "leave_balances"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    leave_type_id = Column(Integer, ForeignKey("leave_types.id", ondelete="CASCADE"), nullable=False, index=True)
    year = Column(Integer, nullable=False, default=lambda: datetime.now().year, index=True)
    allocated_days = Column(Float, default=0.0, nullable=False)
    used_days = Column(Float, default=0.0, nullable=False)

    user = relationship("User", back_populates="leave_balances")
    leave_type = relationship("LeaveType", back_populates="balances")

    @property
    def remaining_days(self) -> float:
        return max(0.0, round(float(self.allocated_days) - float(self.used_days), 1))


class LeaveRequest(Base):
    __tablename__ = "leave_requests"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    leave_type_id = Column(Integer, ForeignKey("leave_types.id"), nullable=False)
    start_date = Column(Date, nullable=False, index=True)
    end_date = Column(Date, nullable=False, index=True)
    total_days = Column(Float, default=1.0, nullable=False)  # 0.5 (half day) or 1.0, 2.0...
    reason = Column(Text, nullable=False)
    status = Column(String(20), default="PENDING", nullable=False, index=True)  # "PENDING", "APPROVED", "REJECTED", "CANCELLED"
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    review_notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", foreign_keys=[user_id], back_populates="leave_requests")
    leave_type = relationship("LeaveType", back_populates="requests")
    reviewer = relationship("User", foreign_keys=[reviewed_by])


class Holiday(Base):
    __tablename__ = "holidays"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    holiday_date = Column(Date, unique=True, nullable=False, index=True)
    holiday_type = Column(String(30), default="NATIONAL", nullable=False)  # "NATIONAL", "COMPANY", "OPTIONAL"
    description = Column(Text, nullable=True)
    is_recurring = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)


class RegularizationRequest(Base):
    __tablename__ = "regularization_requests"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    attendance_date = Column(Date, nullable=False, index=True)
    requested_punch_in = Column(String(20), nullable=True)   # "HH:MM:SS" or "HH:MM"
    requested_punch_out = Column(String(20), nullable=True)  # "HH:MM:SS" or "HH:MM"
    reason = Column(Text, nullable=False)
    status = Column(String(20), default="PENDING", nullable=False, index=True)  # "PENDING", "APPROVED", "REJECTED"
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    review_notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", foreign_keys=[user_id], back_populates="regularization_requests")
    reviewer = relationship("User", foreign_keys=[reviewed_by])


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    actor = Column(String(100), nullable=False)
    action = Column(String(100), nullable=False)
    details = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.now, nullable=False)
