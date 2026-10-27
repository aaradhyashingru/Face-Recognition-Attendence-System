from datetime import date, datetime, time
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from app.models import RegularizationRequest, AttendanceLog, AuditLog, User
from app.config import logger


class RegularizationService:
    @classmethod
    def create_request(
        cls,
        db: Session,
        user_id: int,
        attendance_date: date,
        requested_punch_in: Optional[str],
        requested_punch_out: Optional[str],
        reason: str,
    ) -> Tuple[bool, str, Optional[RegularizationRequest]]:
        """Submit a regularization request for a missed punch."""
        if not requested_punch_in and not requested_punch_out:
            return False, "Must provide at least a requested punch-in or punch-out time.", None

        if attendance_date > date.today():
            return False, "Cannot regularize attendance for future dates.", None

        # Check existing pending request for this user and date
        existing = (
            db.query(RegularizationRequest)
            .filter(
                RegularizationRequest.user_id == user_id,
                RegularizationRequest.attendance_date == attendance_date,
                RegularizationRequest.status == "PENDING",
            )
            .first()
        )
        if existing:
            return False, f"A pending regularization request already exists for {attendance_date}.", None

        req = RegularizationRequest(
            user_id=user_id,
            attendance_date=attendance_date,
            requested_punch_in=requested_punch_in.strip() if requested_punch_in else None,
            requested_punch_out=requested_punch_out.strip() if requested_punch_out else None,
            reason=reason.strip(),
            status="PENDING",
        )
        db.add(req)
        db.commit()
        db.refresh(req)

        return True, "Regularization request submitted for review.", req

    @classmethod
    def review_request(
        cls,
        db: Session,
        request_id: int,
        reviewer_id: int,
        decision: str,  # "APPROVED" or "REJECTED"
        review_notes: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """Review and apply attendance regularization."""
        req = db.query(RegularizationRequest).filter(RegularizationRequest.id == request_id).first()
        if not req:
            return False, "Regularization request not found."

        decision = decision.upper().strip()
        if decision not in ("APPROVED", "REJECTED"):
            return False, "Invalid review status. Must be APPROVED or REJECTED."

        req.status = decision
        req.reviewed_by = reviewer_id
        req.review_notes = review_notes
        req.reviewed_at = datetime.now()

        if decision == "APPROVED":
            att_date = req.attendance_date

            def parse_time(time_str: str) -> time:
                parts = [int(p) for p in time_str.split(":")]
                h = parts[0]
                m = parts[1] if len(parts) > 1 else 0
                s = parts[2] if len(parts) > 2 else 0
                return time(h, m, s)

            # Apply Punch IN if requested
            if req.requested_punch_in:
                t_in = parse_time(req.requested_punch_in)
                dt_in = datetime.combine(att_date, t_in)
                existing_in = (
                    db.query(AttendanceLog)
                    .filter(
                        AttendanceLog.user_id == req.user_id,
                        AttendanceLog.timestamp >= datetime.combine(att_date, time.min),
                        AttendanceLog.timestamp <= datetime.combine(att_date, time.max),
                        AttendanceLog.punch_type == "IN",
                    )
                    .first()
                )
                if existing_in:
                    existing_in.timestamp = dt_in
                    existing_in.status = "REGULARIZED"
                    existing_in.device_id = "PORTAL-REGULARIZATION"
                else:
                    db.add(AttendanceLog(
                        user_id=req.user_id,
                        timestamp=dt_in,
                        punch_type="IN",
                        status="REGULARIZED",
                        confidence_score=1.0,
                        device_id="PORTAL-REGULARIZATION",
                    ))

            # Apply Punch OUT if requested
            if req.requested_punch_out:
                t_out = parse_time(req.requested_punch_out)
                dt_out = datetime.combine(att_date, t_out)
                existing_out = (
                    db.query(AttendanceLog)
                    .filter(
                        AttendanceLog.user_id == req.user_id,
                        AttendanceLog.timestamp >= datetime.combine(att_date, time.min),
                        AttendanceLog.timestamp <= datetime.combine(att_date, time.max),
                        AttendanceLog.punch_type == "OUT",
                    )
                    .first()
                )
                if existing_out:
                    existing_out.timestamp = dt_out
                    existing_out.status = "REGULARIZED"
                    existing_out.device_id = "PORTAL-REGULARIZATION"
                else:
                    db.add(AttendanceLog(
                        user_id=req.user_id,
                        timestamp=dt_out,
                        punch_type="OUT",
                        status="REGULARIZED",
                        confidence_score=1.0,
                        device_id="PORTAL-REGULARIZATION",
                    ))

            # Audit log
            reviewer = db.query(User).filter(User.id == reviewer_id).first()
            actor_name = reviewer.user_code if reviewer else f"USER_{reviewer_id}"
            db.add(AuditLog(
                actor=actor_name,
                action="REGULARIZE_ATTENDANCE",
                details=f"Approved regularization #{req.id} for user ID {req.user_id} on {att_date}.",
            ))

        try:
            db.commit()
            return True, f"Regularization request #{request_id} {decision} successfully."
        except Exception as e:
            db.rollback()
            return False, f"Failed to apply regularization: {e}"
