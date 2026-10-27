import unittest
from datetime import datetime, date, time, timedelta


class TestBugFixes(unittest.TestCase):
    def test_shift_time_parsing(self):
        """Test shift start time parsing with both HH:MM and HH:MM:SS."""
        test_cases = [
            ("09:00:00", 9, 0, 0),
            ("09:30", 9, 30, 0),
            ("08:15:30", 8, 15, 30),
            ("10", 10, 0, 0),
        ]
        for s_str, exp_h, exp_m, exp_s in test_cases:
            parts = [int(p) for p in s_str.strip().split(":")]
            sh_h = parts[0]
            sh_m = parts[1] if len(parts) > 1 else 0
            sh_s = parts[2] if len(parts) > 2 else 0
            self.assertEqual((sh_h, sh_m, sh_s), (exp_h, exp_m, exp_s))

    def test_cooldown_string_parsing(self):
        """Test safe cooldown string parsing."""
        cases = [
            ("COOLDOWN_340s", "340s"),
            ("COOLDOWN_12s", "12s"),
            ("COOLDOWN", ""),
        ]
        for raw, expected in cases:
            parts = raw.split("_")
            rem = parts[1] if len(parts) > 1 else ""
            self.assertEqual(rem, expected)

    def test_datetime_parser_logic(self):
        def parse_custom_datetime(dt_str: str) -> datetime:
            dt_str = dt_str.strip()
            for fmt in (
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%dT%H:%M",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M",
                "%Y-%m-%d",
            ):
                try:
                    return datetime.strptime(dt_str, fmt)
                except ValueError:
                    continue
            return datetime.now()

        dt1 = parse_custom_datetime("2026-10-27T14:30")
        self.assertEqual(dt1.hour, 14)
        self.assertEqual(dt1.minute, 30)

        dt2 = parse_custom_datetime("2026-10-27 15:45:00")
        self.assertEqual(dt2.hour, 15)
        self.assertEqual(dt2.minute, 45)

    def test_shift_evaluation_logic(self):
        """Test shift evaluation with standard day shift and night shift."""
        def evaluate_punch(start_str: str, grace_mins: int, punch_time: datetime, is_night: bool = False) -> str:
            parts = [int(p) for p in start_str.strip().split(":")]
            sh_h = parts[0]
            sh_m = parts[1] if len(parts) > 1 else 0
            sh_s = parts[2] if len(parts) > 2 else 0
            punch_date = punch_time.date()
            deadline = datetime.combine(punch_date, time(sh_h, sh_m, sh_s)) + timedelta(minutes=grace_mins)

            if is_night:
                if punch_time.hour < 12 and sh_h >= 12:
                    deadline_prev = datetime.combine(punch_date - timedelta(days=1), time(sh_h, sh_m, sh_s)) + timedelta(minutes=grace_mins)
                    if punch_time > deadline_prev:
                        return "LATE"
                elif punch_time > deadline:
                    return "LATE"
            else:
                if punch_time > deadline:
                    return "LATE"
            return "ON_TIME"

        today = date(2026, 10, 28)
        # Day Shift: 09:00, 15m grace -> deadline 09:15
        self.assertEqual(evaluate_punch("09:00:00", 15, datetime.combine(today, time(9, 10))), "ON_TIME")
        self.assertEqual(evaluate_punch("09:00:00", 15, datetime.combine(today, time(9, 16))), "LATE")

        # Night Shift: 22:00, 15m grace -> deadline 22:15
        self.assertEqual(evaluate_punch("22:00:00", 15, datetime.combine(today, time(22, 10)), is_night=True), "ON_TIME")
        self.assertEqual(evaluate_punch("22:00:00", 15, datetime.combine(today, time(22, 20)), is_night=True), "LATE")

    def test_leave_balance_and_overlap_logic(self):
        """Test leave quota tracking and date range overlap collision detection."""
        alloc = 12.0
        used = 3.5
        remaining = max(0.0, round(alloc - used, 1))
        self.assertEqual(remaining, 8.5)

        # Overlap detection logic:
        # Existing leave: [2026-06-05 to 2026-06-10]
        ex_start = date(2026, 6, 5)
        ex_end = date(2026, 6, 10)

        def is_overlapping(s: date, e: date) -> bool:
            return not (e < ex_start or s > ex_end)

        self.assertTrue(is_overlapping(date(2026, 6, 4), date(2026, 6, 6)))   # partial overlap
        self.assertTrue(is_overlapping(date(2026, 6, 6), date(2026, 6, 8)))   # inside
        self.assertTrue(is_overlapping(date(2026, 6, 10), date(2026, 6, 12))) # touches end
        self.assertFalse(is_overlapping(date(2026, 6, 1), date(2026, 6, 4)))  # before
        self.assertFalse(is_overlapping(date(2026, 6, 11), date(2026, 6, 15))) # after


if __name__ == "__main__":
    unittest.main()
