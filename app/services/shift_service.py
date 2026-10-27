from datetime import datetime, date, time, timedelta
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from app.models import Shift, User, Department
from app.config import (
    DEFAULT_SHIFT_START,
    DEFAULT_SHIFT_END,
    DEFAULT_GRACE_PERIOD_MINS,
    logger,
)


class ShiftService:
    @classmethod
    def seed_default_shifts(cls, db: Session):
        """Seed foundational enterprise shifts if none exist."""
        if db.query(Shift).count() > 0:
            return

        default_shifts = [
            {
                "name": "General Day Shift",
                "code": "GEN",
                "start_time": "09:00:00",
                "end_time": "17:00:00",
                "grace_period_mins": 15,
                "is_night_shift": False,
                "break_duration_mins": 60,
            },
            {
                "name": "Morning Shift",
                "code": "MORN",
                "start_time": "06:00:00",
                "end_time": "14:00:00",
                "grace_period_mins": 10,
                "is_night_shift": False,
                "break_duration_mins": 45,
            },
            {
                "name": "Evening Shift",
                "code": "EVE",
                "start_time": "14:00:00",
                "end_time": "22:00:00",
                "grace_period_mins": 10,
                "is_night_shift": False,
                "break_duration_mins": 45,
            },
            {
                "name": "Night Shift (Cross-Midnight)",
                "code": "NIGHT",
                "start_time": "22:00:00",
                "end_time": "06:00:00",
                "grace_period_mins": 15,
                "is_night_shift": True,
                "break_duration_mins": 60,
            },
        ]

        for s in default_shifts:
            db.add(Shift(**s))

        try:
            db.commit()
            logger.info("Initialized default enterprise shifts: GEN, MORN, EVE, NIGHT")
        except Exception as e:
            db.rollback()
            logger.warning("Error seeding shifts: %s", e)

    @classmethod
    def get_effective_shift(cls, user: User) -> Tuple[str, str, int, bool]:
        """
        Determine user's active shift parameters in priority order:
        1. User's explicit shift (if assigned)
        2. Department's assigned shift
        3. Department's legacy shift_start / shift_end
        4. Global system defaults
        Returns (start_time_str, end_time_str, grace_mins, is_night_shift).
        """
        # 1. User specific shift
        if getattr(user, "shift", None) and user.shift.is_active:
            s = user.shift
            grace = user.grace_period_mins if getattr(user, "grace_period_mins", None) is not None else s.grace_period_mins
            return s.start_time, s.end_time, grace, s.is_night_shift

        # 2. Department specific shift
        dept = user.department
        if dept and getattr(dept, "shift", None) and dept.shift.is_active:
            s = dept.shift
            grace = user.grace_period_mins if getattr(user, "grace_period_mins", None) is not None else s.grace_period_mins
            return s.start_time, s.end_time, grace, s.is_night_shift

        # 3. Department legacy fields
        if dept:
            s_start = dept.shift_start or DEFAULT_SHIFT_START
            s_end = dept.shift_end or DEFAULT_SHIFT_END
            dept_grace = dept.grace_period_mins or DEFAULT_GRACE_PERIOD_MINS
            grace = user.grace_period_mins if getattr(user, "grace_period_mins", None) is not None else dept_grace
            return s_start, s_end, grace, False

        # 4. Fallback defaults
        grace = user.grace_period_mins if getattr(user, "grace_period_mins", None) is not None else DEFAULT_GRACE_PERIOD_MINS
        return DEFAULT_SHIFT_START, DEFAULT_SHIFT_END, grace, False

    @classmethod
    def evaluate_punch_status(
        cls,
        user: User,
        punch_time: datetime,
    ) -> str:
        """
        Determine attendance status: "ON_TIME" or "LATE" according to shift start + grace.
        """
        start_str, end_str, grace_mins, is_night = cls.get_effective_shift(user)

        try:
            parts = [int(p) for p in start_str.strip().split(":")]
            sh_h = parts[0]
            sh_m = parts[1] if len(parts) > 1 else 0
            sh_s = parts[2] if len(parts) > 2 else 0

            punch_date = punch_time.date()
            deadline = datetime.combine(punch_date, time(sh_h, sh_m, sh_s)) + timedelta(minutes=grace_mins)

            # Night shift scenario: e.g. start at 22:00. If employee punches between 20:00 and 22:15, on time.
            if is_night:
                # If shift starts at 22:00, punch could be 21:50 or 22:10
                if punch_time.hour < 12 and sh_h >= 12:
                    # Punched after midnight for a night shift starting previous evening
                    # e.g. punch at 00:05, shift began 22:00 yesterday
                    deadline_prev = datetime.combine(punch_date - timedelta(days=1), time(sh_h, sh_m, sh_s)) + timedelta(minutes=grace_mins)
                    if punch_time > deadline_prev:
                        return "LATE"
                elif punch_time > deadline:
                    return "LATE"
            else:
                if punch_time > deadline:
                    return "LATE"

            return "ON_TIME"
        except Exception as e:
            logger.error("Error evaluating punch status for %s: %s", user.user_code, e)
            return "ON_TIME"
