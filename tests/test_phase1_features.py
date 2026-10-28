import unittest
from datetime import datetime, date, time, timedelta
from pathlib import Path
import sys

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.database import Base
    from app.models import (
        User,
        Department,
        Shift,
        LeaveType,
        LeaveBalance,
        LeaveRequest,
        Holiday,
        RegularizationRequest,
        AttendanceLog,
    )
    from app.services.shift_service import ShiftService
    from app.services.leave_service import LeaveService
    from app.services.holiday_service import HolidayService
    from app.services.regularization_service import RegularizationService
    from app.services.payroll_service import PayrollService
    DEPENDENCIES_AVAILABLE = True
except ImportError:
    DEPENDENCIES_AVAILABLE = False


@unittest.skipUnless(DEPENDENCIES_AVAILABLE, "SQLAlchemy and project dependencies required for Phase 1 feature tests")
class TestPhase1EnterpriseFeatures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # In-memory SQLite for isolated high-speed unit testing
        cls.engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(bind=cls.engine)
        cls.Session = sessionmaker(bind=cls.engine)

    def setUp(self):
        self.db = self.Session()
        # Seed core defaults
        ShiftService.seed_default_shifts(self.db)
        LeaveService.seed_default_leave_types(self.db)
        HolidayService.seed_default_holidays(self.db, 2026)

        # Create test department
        self.dept = Department(
            name="Engineering",
            shift_start="09:00:00",
            shift_end="17:00:00",
            grace_period_mins=15,
        )
        self.db.add(self.dept)
        self.db.commit()

        # Create test user
        self.user = User(
            user_code="EMP_TEST_01",
            full_name="Alice Developer",
            email="alice@company.com",
            department_id=self.dept.id,
            role="USER",
            hourly_rate=30.0,
            is_active=True,
        )
        self.db.add(self.user)
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_01_shift_seeding_and_evaluation(self):
        """Test shifts and punch status resolution (on-time vs late, custom grace)."""
        shifts = self.db.query(Shift).all()
        self.assertGreaterEqual(len(shifts), 4)

        gen_shift = self.db.query(Shift).filter(Shift.code == "GEN").first()
        self.assertIsNotNone(gen_shift)
        self.assertEqual(gen_shift.start_time, "09:00:00")
        self.assertEqual(gen_shift.grace_period_mins, 15)

        # Test on-time punch: 09:10 (within 15m grace)
        t_ontime = datetime.combine(date.today(), time(9, 10))
        status = ShiftService.evaluate_punch_status(self.user, t_ontime)
        self.assertEqual(status, "ON_TIME")

        # Test late punch: 09:20 (outside 15m grace)
        t_late = datetime.combine(date.today(), time(9, 20))
        status_late = ShiftService.evaluate_punch_status(self.user, t_late)
        self.assertEqual(status_late, "LATE")

        # Test manual grace override: give employee 30m grace
        self.user.grace_period_mins = 30
        self.db.commit()
        status_override = ShiftService.evaluate_punch_status(self.user, t_late)
        self.assertEqual(status_override, "ON_TIME")

    def test_02_leave_management_lifecycle(self):
        """Test leave quota allocation, application validation, and approval deduction."""
        LeaveService.ensure_user_balances(self.db, self.user.id, 2026)
        balances = LeaveService.get_user_balances_summary(self.db, self.user.id, 2026)
        self.assertGreaterEqual(len(balances), 3)

        cl = self.db.query(LeaveType).filter(LeaveType.code == "CL").first()
        self.assertIsNotNone(cl)

        # Apply for 2 days of casual leave
        d1 = date(2026, 6, 1)
        d2 = date(2026, 6, 2)
        success, msg, req = LeaveService.apply_leave(
            self.db, self.user.id, cl.id, d1, d2, "Family vacation"
        )
        self.assertTrue(success)
        self.assertIsNotNone(req)
        self.assertEqual(req.status, "PENDING")
        self.assertEqual(req.total_days, 2.0)

        # Test overlap rejection
        succ2, msg2, _ = LeaveService.apply_leave(
            self.db, self.user.id, cl.id, d2, date(2026, 6, 3), "Overlapping"
        )
        self.assertFalse(succ2)
        self.assertIn("overlap", msg2.lower())

        # Review & Approve
        reviewer = self.user.id
        rev_success, rev_msg = LeaveService.review_leave(
            self.db, req.id, reviewer, "APPROVED", "Approved by team lead"
        )
        self.assertTrue(rev_success)

        # Verify balance deduction
        bal = (
            self.db.query(LeaveBalance)
            .filter(
                LeaveBalance.user_id == self.user.id,
                LeaveBalance.leave_type_id == cl.id,
                LeaveBalance.year == 2026,
            )
            .first()
        )
        self.assertEqual(bal.used_days, 2.0)
        self.assertEqual(bal.remaining_days, 10.0)  # 12 - 2 = 10

        # Verify user is marked on leave on 2026-06-01
        on_leave, lt_name, is_paid = LeaveService.is_user_on_approved_leave(
            self.db, self.user.id, d1
        )
        self.assertTrue(on_leave)
        self.assertTrue(is_paid)

    def test_03_holiday_calendar(self):
        """Test official statutory holiday lookup and upcoming queries."""
        is_h, name = HolidayService.is_holiday(self.db, date(2026, 1, 1))
        self.assertTrue(is_h)
        self.assertEqual(name, "New Year's Day")

        is_h2, _ = HolidayService.is_holiday(self.db, date(2026, 2, 10))
        self.assertFalse(is_h2)

        upcoming = HolidayService.get_upcoming_holidays(self.db, limit=5)
        self.assertIsInstance(upcoming, list)

    def test_04_attendance_regularization(self):
        """Test missed punch correction request and automatic AttendanceLog generation."""
        past_date = date.today() - timedelta(days=2)
        success, msg, reg = RegularizationService.create_request(
            self.db,
            user_id=self.user.id,
            attendance_date=past_date,
            requested_punch_in="09:05:00",
            requested_punch_out="17:15:00",
            reason="Card reader was offline during morning entry",
        )
        self.assertTrue(success)
        self.assertEqual(reg.status, "PENDING")

        # Approve regularization
        rev_ok, rev_msg = RegularizationService.review_request(
            self.db, reg.id, reviewer_id=self.user.id, decision="APPROVED"
        )
        self.assertTrue(rev_ok)

        # Check that AttendanceLog records were created
        logs = (
            self.db.query(AttendanceLog)
            .filter(
                AttendanceLog.user_id == self.user.id,
                AttendanceLog.timestamp >= datetime.combine(past_date, time.min),
                AttendanceLog.timestamp <= datetime.combine(past_date, time.max),
            )
            .all()
        )
        self.assertEqual(len(logs), 2)
        punch_types = {l.punch_type for l in logs}
        self.assertEqual(punch_types, {"IN", "OUT"})
        for l in logs:
            self.assertEqual(l.status, "REGULARIZED")
            self.assertEqual(l.device_id, "PORTAL-REGULARIZATION")

    def test_05_payroll_with_leaves_and_regularization(self):
        """Test payroll computation factoring in regularized attendance and paid leaves."""
        # Add punch on day 1
        today = date.today()
        d_in = datetime.combine(today, time(9, 0))
        d_out = datetime.combine(today, time(17, 0))
        self.db.add(AttendanceLog(user_id=self.user.id, timestamp=d_in, punch_type="IN", status="ON_TIME"))
        self.db.add(AttendanceLog(user_id=self.user.id, timestamp=d_out, punch_type="OUT", status="ON_TIME"))

        # Add approved paid leave on yesterday
        yesterday = today - timedelta(days=1)
        self.db.add(AttendanceLog(
            user_id=self.user.id,
            timestamp=datetime.combine(yesterday, time(9, 0)),
            punch_type="IN",
            status="ON_LEAVE",
        ))
        self.db.commit()

        # Compute payroll
        start_str = date(today.year, today.month, 1).strftime("%Y-%m-%d")
        end_str = today.strftime("%Y-%m-%d")
        payroll = PayrollService.compute_payroll(self.db, start_date=start_str, end_date=end_str, user_id=self.user.id)

        self.assertEqual(len(payroll["records"]), 1)
        rec = payroll["records"][0]
        self.assertEqual(rec["user_code"], self.user.user_code)
        # 8 hrs from work + 8 hrs from paid leave = 16 regular hrs
        self.assertGreaterEqual(rec["regular_hours"], 16.0)
        self.assertEqual(rec["hourly_rate"], 30.0)
        self.assertGreaterEqual(rec["net_pay"], 480.0)  # 16 * $30 = $480


if __name__ == "__main__":
    unittest.main()
