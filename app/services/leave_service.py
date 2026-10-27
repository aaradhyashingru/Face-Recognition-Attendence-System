from datetime import date, datetime, timedelta
from typing import Optional, Tuple, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from app.models import LeaveType, LeaveBalance, LeaveRequest, User, AttendanceLog
from app.config import logger


class LeaveService:
    @classmethod
    def seed_default_leave_types(cls, db: Session):
        """Seed standard corporate leave types if none exist."""
        if db.query(LeaveType).count() > 0:
            return

        defaults = [
            ("Casual Leave", "CL", 12.0, True, "General purpose personal time off"),
            ("Sick Leave", "SL", 10.0, True, "Medical and health-related leave"),
            ("Privilege / Earned Leave", "PL", 15.0, True, "Annual earned paid vacation"),
            ("Loss of Pay (Unpaid)", "UL", 30.0, False, "Unpaid approved absence"),
        ]

        for name, code, days, is_paid, desc in defaults:
            db.add(LeaveType(
                name=name,
                code=code,
                default_days_per_year=days,
                is_paid=is_paid,
                description=desc,
                is_active=True,
            ))

        try:
            db.commit()
            logger.info("Initialized default corporate leave types: CL, SL, PL, UL")
        except Exception as e:
            db.rollback()
            logger.warning("Error seeding leave types: %s", e)

    @classmethod
    def ensure_user_balances(cls, db: Session, user_id: int, year: Optional[int] = None) -> List[LeaveBalance]:
        """
        Verify that a user has leave balances allocated for all active leave types for the year.
        If missing, automatically initializes balances from default_days_per_year.
        """
        y = year or datetime.now().year
        leave_types = db.query(LeaveType).filter(LeaveType.is_active == True).all()
        created_any = False

        for lt in leave_types:
            bal = (
                db.query(LeaveBalance)
                .filter(
                    LeaveBalance.user_id == user_id,
                    LeaveBalance.leave_type_id == lt.id,
                    LeaveBalance.year == y,
                )
                .first()
            )
            if not bal:
                new_bal = LeaveBalance(
                    user_id=user_id,
                    leave_type_id=lt.id,
                    year=y,
                    allocated_days=lt.default_days_per_year,
                    used_days=0.0,
                )
                db.add(new_bal)
                created_any = True

        if created_any:
            try:
                db.commit()
            except Exception as e:
                db.rollback()
                logger.warning("Error ensuring leave balances for user %d: %s", user_id, e)

        return (
            db.query(LeaveBalance)
            .filter(LeaveBalance.user_id == user_id, LeaveBalance.year == y)
            .all()
        )

    @classmethod
    def get_user_balances_summary(cls, db: Session, user_id: int, year: Optional[int] = None) -> List[Dict[str, Any]]:
        """Return human-readable leave balances with remaining days for an employee."""
        balances = cls.ensure_user_balances(db, user_id, year)
        results = []
        for b in balances:
            lt = b.leave_type
            results.append({
                "id": b.id,
                "user_id": b.user_id,
                "leave_type_id": b.leave_type_id,
                "leave_type_name": lt.name if lt else "Unknown",
                "leave_type_code": lt.code if lt else "UNK",
                "is_paid": lt.is_paid if lt else True,
                "year": b.year,
                "allocated_days": b.allocated_days,
                "used_days": b.used_days,
                "remaining_days": b.remaining_days,
            })
        return results

    @classmethod
    def apply_leave(
        cls,
        db: Session,
        user_id: int,
        leave_type_id: int,
        start_date: date,
        end_date: date,
        reason: str,
        total_days: Optional[float] = None,
    ) -> Tuple[bool, str, Optional[LeaveRequest]]:
        """
        Validate and submit a leave application.
        Checks date validity, overlaps, and remaining balance.
        """
        if start_date > end_date:
            return False, "Start date cannot be after end date.", None

        # Calculate total days if not provided
        if total_days is None or total_days <= 0:
            calc_days = (end_date - start_date).days + 1
            total_days = float(calc_days)

        # Check overlapping requests
        overlap = (
            db.query(LeaveRequest)
            .filter(
                LeaveRequest.user_id == user_id,
                LeaveRequest.status.in_(["PENDING", "APPROVED"]),
                or_(
                    and_(LeaveRequest.start_date <= start_date, LeaveRequest.end_date >= start_date),
                    and_(LeaveRequest.start_date <= end_date, LeaveRequest.end_date >= end_date),
                    and_(LeaveRequest.start_date >= start_date, LeaveRequest.end_date <= end_date),
                ),
            )
            .first()
        )
        if overlap:
            return False, f"Leave dates overlap with an existing request (#{overlap.id} - {overlap.status}).", None

        # Check balance for the year of start_date
        y = start_date.year
        cls.ensure_user_balances(db, user_id, y)
        bal = (
            db.query(LeaveBalance)
            .filter(
                LeaveBalance.user_id == user_id,
                LeaveBalance.leave_type_id == leave_type_id,
                LeaveBalance.year == y,
            )
            .first()
        )

        lt = db.query(LeaveType).filter(LeaveType.id == leave_type_id).first()
        if not lt:
            return False, "Selected leave type does not exist.", None

        # If it's a paid leave, enforce balance check
        if lt.is_paid:
            if not bal or bal.remaining_days < total_days:
                avail = bal.remaining_days if bal else 0.0
                return False, f"Insufficient leave balance. Requested: {total_days} days, Available: {avail} days.", None

        req = LeaveRequest(
            user_id=user_id,
            leave_type_id=leave_type_id,
            start_date=start_date,
            end_date=end_date,
            total_days=total_days,
            reason=reason,
            status="PENDING",
        )
        db.add(req)
        db.commit()
        db.refresh(req)

        return True, "Leave application submitted successfully.", req

    @classmethod
    def review_leave(
        cls,
        db: Session,
        request_id: int,
        reviewer_id: int,
        decision: str,  # "APPROVED" or "REJECTED"
        review_notes: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Approve or reject a leave request and update leave balances accordingly.
        """
        req = db.query(LeaveRequest).filter(LeaveRequest.id == request_id).first()
        if not req:
            return False, "Leave request not found."

        decision = decision.upper().strip()
        if decision not in ("APPROVED", "REJECTED"):
            return False, "Invalid review status. Must be APPROVED or REJECTED."

        y = req.start_date.year
        bal = (
            db.query(LeaveBalance)
            .filter(
                LeaveBalance.user_id == req.user_id,
                LeaveBalance.leave_type_id == req.leave_type_id,
                LeaveBalance.year == y,
            )
            .first()
        )

        old_status = req.status
        req.status = decision
        req.reviewed_by = reviewer_id
        req.review_notes = review_notes
        req.reviewed_at = datetime.now()

        # Update balance if paid leave
        lt = req.leave_type
        if lt and lt.is_paid and bal:
            if decision == "APPROVED" and old_status != "APPROVED":
                bal.used_days = round(bal.used_days + req.total_days, 1)
            elif decision == "REJECTED" and old_status == "APPROVED":
                bal.used_days = max(0.0, round(bal.used_days - req.total_days, 1))

        # Auto-record ON_LEAVE logs for dates in range if approved
        if decision == "APPROVED":
            curr = req.start_date
            while curr <= req.end_date:
                curr_dt = datetime.combine(curr, datetime.min.time().replace(hour=9))
                # Check if an attendance log already exists for that day
                existing = (
                    db.query(AttendanceLog)
                    .filter(
                        AttendanceLog.user_id == req.user_id,
                        AttendanceLog.timestamp >= datetime.combine(curr, datetime.min.time()),
                        AttendanceLog.timestamp <= datetime.combine(curr, datetime.max.time()),
                    )
                    .first()
                )
                if not existing:
                    db.add(AttendanceLog(
                        user_id=req.user_id,
                        timestamp=curr_dt,
                        punch_type="IN",
                        status="ON_LEAVE",
                        confidence_score=1.0,
                        device_id="PORTAL-LEAVE",
                    ))
                curr += timedelta(days=1)

        try:
            db.commit()
            return True, f"Leave request #{request_id} has been marked as {decision}."
        except Exception as e:
            db.rollback()
            return False, f"Failed to update leave request: {e}"

    @classmethod
    def is_user_on_approved_leave(cls, db: Session, user_id: int, check_date: date) -> Tuple[bool, Optional[str], bool]:
        """
        Check if employee is on an approved leave on `check_date`.
        Returns (is_on_leave, leave_name, is_paid).
        """
        leave = (
            db.query(LeaveRequest)
            .filter(
                LeaveRequest.user_id == user_id,
                LeaveRequest.status == "APPROVED",
                LeaveRequest.start_date <= check_date,
                LeaveRequest.end_date >= check_date,
            )
            .first()
        )
        if leave and leave.leave_type:
            return True, leave.leave_type.name, leave.leave_type.is_paid
        return False, None, False
