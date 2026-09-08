import io
import sys
from pathlib import Path
import unittest

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import cv2

from app.auth import hash_password, verify_password, create_access_token, decode_token
from app.database import Base, SessionLocal, engine
from app.models import User, Department, FaceEmbedding, AttendanceLog
from app.services.attendance_engine import AttendanceEngine
from app.services.export_service import ExportService
from app.services.vision_engine import get_vision_engine


class TestFRASEnterprise(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)
        cls.db = SessionLocal()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_01_auth_service(self):
        pwd = "SecurePassword@2026"
        hashed = hash_password(pwd)
        self.assertTrue(verify_password(pwd, hashed))
        self.assertFalse(verify_password("WrongPassword", hashed))

        token = create_access_token({"sub": "test_user", "role": "ADMIN"})
        payload = decode_token(token)
        self.assertIsNotNone(payload)
        self.assertEqual(payload.get("sub"), "test_user")
        self.assertEqual(payload.get("role"), "ADMIN")
        print("[OK] Auth & JWT service passed.")

    def test_02_vision_engine_models(self):
        vision = get_vision_engine()
        self.assertIsNotNone(vision.detector)
        self.assertIsNotNone(vision.recognizer)

        # Test dummy image (320x320)
        dummy_frame = np.zeros((320, 320, 3), dtype=np.uint8)
        faces = vision.detect_faces(dummy_frame)
        self.assertTrue(faces is None or len(faces) == 0)

        # Test cosine similarity matching
        v1 = np.random.randn(128).astype(np.float32)
        v1 = v1 / np.linalg.norm(v1)
        v2 = v1.copy()  # identical
        v3 = np.random.randn(128).astype(np.float32)
        v3 = v3 / np.linalg.norm(v3)

        user_id, conf = vision.match_embedding(v1, [(101, v2)], threshold=0.65)
        self.assertEqual(user_id, 101)
        self.assertGreater(conf, 0.9)
        print("[OK] Vision Engine initialization & vector matching passed.")

    def test_03_database_and_attendance_engine(self):
        # Create department
        dept = self.db.query(Department).filter(Department.name == "Test CSE").first()
        if not dept:
            dept = Department(name="Test CSE", shift_start="09:00:00", grace_period_mins=15)
            self.db.add(dept)
            self.db.commit()
            self.db.refresh(dept)

        # Create test user
        user = self.db.query(User).filter(User.user_code == "TEST_001").first()
        if not user:
            user = User(
                user_code="TEST_001",
                full_name="Unit Test Student",
                department_id=dept.id,
                role="USER",
                is_active=True,
            )
            self.db.add(user)
            self.db.commit()
            self.db.refresh(user)

        # Clean up existing test logs
        self.db.query(AttendanceLog).filter(AttendanceLog.user_id == user.id).delete()
        self.db.commit()
        AttendanceEngine._cooldown_cache.pop(user.id, None)

        # First punch -> IN
        status1, log1 = AttendanceEngine.record_punch(self.db, user, confidence=0.95)
        self.assertEqual(status1, "SUCCESS")
        self.assertEqual(log1.punch_type, "IN")

        # Second immediate punch -> COOLDOWN
        status2, log2 = AttendanceEngine.record_punch(self.db, user, confidence=0.95)
        self.assertTrue(status2.startswith("COOLDOWN"))
        print("[OK] Attendance engine & debounce cooldown passed.")

    def test_04_exports(self):
        logs = self.db.query(AttendanceLog).limit(5).all()

        excel_buf = ExportService.generate_excel(logs)
        self.assertIsInstance(excel_buf, io.BytesIO)
        self.assertGreater(len(excel_buf.getvalue()), 1000)

        pdf_buf = ExportService.generate_pdf(logs)
        self.assertIsInstance(pdf_buf, io.BytesIO)
        self.assertGreater(len(pdf_buf.getvalue()), 1000)
        print("[OK] Excel and PDF export services passed.")


if __name__ == "__main__":
    unittest.main()
