from datetime import datetime, date, time, timedelta
from typing import Optional, Tuple, Dict
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.config import (
    PUNCH_COOLDOWN_SECONDS,
    DEFAULT_SHIFT_START,
    DEFAULT_GRACE_PERIOD_MINS,
    logger,
)
from app.models import AttendanceLog, User, Department
from app.services.shift_service import ShiftService


class AttendanceEngine:
    # In-memory debounce cache: user_id -> datetime of last punch
    _cooldown_cache: Dict[int, datetime] = {}

    @classmethod
    def check_cooldown(cls, user_id: int, db: Optional[Session] = None) -> Tuple[bool, int]:
        """
        Check if user is within the debounce cooldown window.
        Uses in-memory cache with automatic database fallback so restarts
        do not reset the cooldown.
        Returns (is_in_cooldown, remaining_seconds).
        """
        now = datetime.now()
        last_punch = cls._cooldown_cache.get(user_id)

        # Fallback to DB if not present in in-memory cache
        if last_punch is None and db is not None:
            latest_record = (
                db.query(AttendanceLog.timestamp)
                .filter(AttendanceLog.user_id == user_id)
                .order_by(AttendanceLog.timestamp.desc())
                .first()
            )
            if latest_record:
                last_punch = latest_record[0]
                cls._cooldown_cache[user_id] = last_punch

        if last_punch:
            elapsed = (now - last_punch).total_seconds()
            if elapsed < PUNCH_COOLDOWN_SECONDS:
                remaining = int(PUNCH_COOLDOWN_SECONDS - elapsed)
                return True, remaining

        return False, 0

    @classmethod
    def record_punch(
        cls,
        db: Session,
        user: User,
        confidence: float,
        device_id: str = "KIOSK-01",
    ) -> Tuple[str, AttendanceLog]:
        """
        Process and commit a punch record adhering to business rules.
        Returns ("SUCCESS" or "COOLDOWN", AttendanceLog).
        """
        now = datetime.now()
        today_start = datetime.combine(date.today(), time.min)
        today_end = datetime.combine(date.today(), time.max)

        # 1. Check Debounce Cooldown (with DB fallback)
        in_cooldown, remaining = cls.check_cooldown(user.id, db=db)
        if in_cooldown:
            latest = (
                db.query(AttendanceLog)
                .filter(
                    AttendanceLog.user_id == user.id,
                    AttendanceLog.timestamp >= today_start,
                )
                .order_by(AttendanceLog.timestamp.desc())
                .first()
            )
            # Cross-midnight fallback: if debounced punch happened before 00:00
            if not latest:
                latest = (
                    db.query(AttendanceLog)
                    .filter(AttendanceLog.user_id == user.id)
                    .order_by(AttendanceLog.timestamp.desc())
                    .first()
                )
            return f"COOLDOWN_{remaining}s", latest

        # 2. Determine Punch Type (IN vs OUT)
        today_punches = (
            db.query(AttendanceLog)
            .filter(
                AttendanceLog.user_id == user.id,
                AttendanceLog.timestamp >= today_start,
                AttendanceLog.timestamp <= today_end,
            )
            .order_by(AttendanceLog.timestamp.asc())
            .all()
        )

        if not today_punches:
            punch_type = "IN"
        else:
            # Alternate between IN and OUT
            last_punch_type = today_punches[-1].punch_type
            punch_type = "OUT" if last_punch_type == "IN" else "IN"

        # 3. Determine Attendance Status (ON_TIME vs LATE) via ShiftService
        status = "ON_TIME"
        if punch_type == "IN":
            status = ShiftService.evaluate_punch_status(user, now)

        # 4. Save Record
        log = AttendanceLog(
            user_id=user.id,
            timestamp=now,
            punch_type=punch_type,
            status=status,
            confidence_score=confidence,
            device_id=device_id,
        )
        db.add(log)
        db.commit()
        db.refresh(log)

        # Update in-memory cooldown cache
        cls._cooldown_cache[user.id] = now

        logger.info(
            "Recorded punch: user_code=%s punch_type=%s status=%s device=%s",
            user.user_code,
            punch_type,
            status,
            device_id,
        )

        return "SUCCESS", log
