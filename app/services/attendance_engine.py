from datetime import datetime, date, time, timedelta
from typing import Optional, Tuple, Dict
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.config import PUNCH_COOLDOWN_SECONDS, DEFAULT_SHIFT_START, DEFAULT_GRACE_PERIOD_MINS
from app.models import AttendanceLog, User, Department


class AttendanceEngine:
    # In-memory debounce cache: user_id -> datetime of last punch
    _cooldown_cache: Dict[int, datetime] = {}

    @classmethod
    def check_cooldown(cls, user_id: int) -> Tuple[bool, int]:
        """
        Check if user is within the debounce cooldown window.
        Returns (is_in_cooldown, remaining_seconds).
        """
        now = datetime.now()
        last_punch = cls._cooldown_cache.get(user_id)

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

        # 1. Check Debounce Cooldown
        in_cooldown, remaining = cls.check_cooldown(user.id)
        if in_cooldown:
            # Fetch latest punch for today to return info
            latest = (
                db.query(AttendanceLog)
                .filter(
                    AttendanceLog.user_id == user.id,
                    AttendanceLog.timestamp >= today_start,
                )
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

        # 3. Determine Attendance Status (ON_TIME vs LATE)
        shift_start_str = DEFAULT_SHIFT_START
        grace_mins = DEFAULT_GRACE_PERIOD_MINS

        if user.department:
            shift_start_str = user.department.shift_start or DEFAULT_SHIFT_START
            grace_mins = user.department.grace_period_mins or DEFAULT_GRACE_PERIOD_MINS

        status = "ON_TIME"
        if punch_type == "IN":
            try:
                sh_h, sh_m, sh_s = map(int, shift_start_str.split(":"))
                shift_deadline = datetime.combine(
                    date.today(), time(sh_h, sh_m, sh_s)
                ) + timedelta(minutes=grace_mins)
                if now > shift_deadline:
                    status = "LATE"
            except Exception as e:
                print(f"Shift calculation error: {e}")
                status = "ON_TIME"

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

        # Update cooldown cache
        cls._cooldown_cache[user.id] = now

        return "SUCCESS", log
