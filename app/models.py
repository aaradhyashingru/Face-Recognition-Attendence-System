import json
from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    Text,
    func,
)
from sqlalchemy.orm import relationship
from app.database import Base


class Department(Base):
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    shift_start = Column(String(10), default="09:00:00")
    shift_end = Column(String(10), default="17:00:00")
    grace_period_mins = Column(Integer, default=15)

    users = relationship("User", back_populates="department")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    user_code = Column(String(50), unique=True, nullable=False, index=True)  # Roll / Employee ID
    full_name = Column(String(150), nullable=False, index=True)
    email = Column(String(150), unique=True, nullable=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    role = Column(String(20), default="USER", nullable=False)  # "ADMIN", "USER"
    password_hash = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    department = relationship("Department", back_populates="users")
    embeddings = relationship(
        "FaceEmbedding", back_populates="user", cascade="all, delete-orphan"
    )
    attendance_logs = relationship(
        "AttendanceLog", back_populates="user", cascade="all, delete-orphan"
    )


class FaceEmbedding(Base):
    __tablename__ = "face_embeddings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    embedding_json = Column(Text, nullable=False)  # JSON-encoded 128-element float list
    quality_score = Column(Float, default=1.0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

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
    status = Column(String(20), default="ON_TIME", nullable=False)  # "ON_TIME", "LATE", "HALF_DAY"
    confidence_score = Column(Float, default=1.0)
    device_id = Column(String(50), default="KIOSK-01")

    user = relationship("User", back_populates="attendance_logs")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    actor = Column(String(100), nullable=False)
    action = Column(String(100), nullable=False)
    details = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.now, nullable=False)
