import os
from pathlib import Path

# Base Paths
BASE_DIR = Path(__file__).resolve().parent.parent
APP_DIR = BASE_DIR / "app"
MODELS_DIR = BASE_DIR / "models"
DATA_DIR = BASE_DIR / "data"
STATIC_DIR = APP_DIR / "static"
TEMPLATES_DIR = APP_DIR / "templates"

# Ensure runtime directories exist
MODELS_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Database Configuration
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'attendance.db'}")

# Security & JWT Configuration
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "fras-enterprise-super-secret-key-2026-secure-jwt")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 Hours

# Default SuperAdmin Credentials (seeded if database is empty)
DEFAULT_ADMIN_USER = os.getenv("DEFAULT_ADMIN_USER", "admin")
DEFAULT_ADMIN_PASS = os.getenv("DEFAULT_ADMIN_PASS", "admin123")
DEFAULT_ADMIN_EMAIL = os.getenv("DEFAULT_ADMIN_EMAIL", "admin@fras.local")

# Deep Learning Model Paths & URLs
YUNET_MODEL_NAME = "face_detection_yunet_2023mar.onnx"
SFACE_MODEL_NAME = "face_recognition_sface_2021dec.onnx"

YUNET_MODEL_PATH = MODELS_DIR / YUNET_MODEL_NAME
SFACE_MODEL_PATH = MODELS_DIR / SFACE_MODEL_NAME

YUNET_DOWNLOAD_URL = (
    "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
)
SFACE_DOWNLOAD_URL = (
    "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx"
)

# AI Recognition Thresholds
FACE_DETECTION_CONFIDENCE = 0.70  # YuNet face confidence threshold
# Cosine similarity threshold for SFace 128-d vectors (range: -1.0 to 1.0; standard match is >= 0.65)
FACE_SIMILARITY_THRESHOLD = 0.65
# Passive liveness Laplacian variance threshold (rejects low-frequency screens/paper blurs)
LIVENESS_LAPLACIAN_THRESHOLD = 30.0

# Attendance Engine Settings
PUNCH_COOLDOWN_SECONDS = 600  # 10 minutes debounce per user
DEFAULT_SHIFT_START = "09:00:00"
DEFAULT_SHIFT_END = "17:00:00"
DEFAULT_GRACE_PERIOD_MINS = 15
