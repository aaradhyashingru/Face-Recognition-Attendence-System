from datetime import date, datetime
from typing import Optional, Tuple, List
from sqlalchemy.orm import Session
from app.models import Holiday
from app.config import logger


class HolidayService:
    @classmethod
    def is_holiday(cls, db: Session, check_date: date) -> Tuple[bool, Optional[str]]:
        """
        Check if a given date is an official holiday.
        Returns (is_holiday, holiday_name).
        """
        holiday = db.query(Holiday).filter(Holiday.holiday_date == check_date).first()
        if holiday:
            return True, holiday.name
        return False, None

    @classmethod
    def get_upcoming_holidays(cls, db: Session, limit: int = 5) -> List[Holiday]:
        """Fetch next upcoming holidays from today."""
        today = date.today()
        return (
            db.query(Holiday)
            .filter(Holiday.holiday_date >= today)
            .order_by(Holiday.holiday_date.asc())
            .limit(limit)
            .all()
        )

    @classmethod
    def seed_default_holidays(cls, db: Session, year: Optional[int] = None):
        """Seed common global and corporate holidays for the given year if none exist."""
        y = year or datetime.now().year
        count = db.query(Holiday).filter(Holiday.holiday_date >= date(y, 1, 1), Holiday.holiday_date <= date(y, 12, 31)).count()
        if count > 0:
            return

        default_holidays = [
            ("New Year's Day", date(y, 1, 1), "NATIONAL", "Global start of the new calendar year"),
            ("International Workers' Day", date(y, 5, 1), "NATIONAL", "Celebrating workers and laborers"),
            ("Independence Day", date(y, 8, 15), "NATIONAL", "National celebration of sovereignty"),
            ("Thanksgiving / Harvest Day", date(y, 11, 26), "COMPANY", "Annual thanksgiving holiday"),
            ("Christmas Day", date(y, 12, 25), "NATIONAL", "Christmas festival celebration"),
            ("New Year's Eve", date(y, 12, 31), "COMPANY", "End of annual business cycle celebration"),
        ]

        for name, h_date, h_type, desc in default_holidays:
            existing = db.query(Holiday).filter(Holiday.holiday_date == h_date).first()
            if not existing:
                db.add(Holiday(name=name, holiday_date=h_date, holiday_type=h_type, description=desc))

        try:
            db.commit()
            logger.info("Default corporate holidays initialized for year %d", y)
        except Exception as e:
            db.rollback()
            logger.warning("Error seeding holidays: %s", e)
