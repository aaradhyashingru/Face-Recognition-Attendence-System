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

if __name__ == "__main__":
    unittest.main()
