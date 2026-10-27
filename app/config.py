import os
import logging
from pathlib import Path

# Try to load environment variables from .env
try:
    from dotenv import load_dotenv
    _ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
    if _ENV_PATH.exists():
        load_dotenv(_ENV_PATH)
except ImportError:
    pass

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

# Environment & Server Config
ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Configure Application-wide Logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("fras")

# Database Configuration
_raw_db = os.getenv("DATABASE_URL", "").strip()
if not _raw_db or _raw_db in ("sqlite:///data/attendance.db", "sqlite:///attendance.db"):
    DATABASE_URL = f"sqlite:///{(DATA_DIR / 'attendance.db').resolve().as_posix()}"
else:
    DATABASE_URL = _raw_db

# Security & JWT Configuration
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not JWT_SECRET_KEY:
    if ENVIRONMENT == "production":
        raise RuntimeError("CRITICAL: JWT_SECRET_KEY environment variable MUST be set in production!")
    else:
        logger.warning(
            "JWT_SECRET_KEY not set. Using auto-generated fallback secret for this session."
        )
        import secrets
        JWT_SECRET_KEY = secrets.token_urlsafe(64)

JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", str(60 * 24)))

# Default SuperAdmin Credentials (used only once for seeding if database has no admin)
DEFAULT_ADMIN_USER = os.getenv("DEFAULT_ADMIN_USER", "admin")
DEFAULT_ADMIN_PASS = os.getenv("DEFAULT_ADMIN_PASS", "admin123")
DEFAULT_ADMIN_EMAIL = os.getenv("DEFAULT_ADMIN_EMAIL", "admin@fras.local")

# CORS Configuration
_raw_cors = os.getenv("CORS_ORIGINS", "*")
if _raw_cors.strip() == "*":
    CORS_ORIGINS = ["*"]
else:
    CORS_ORIGINS = [origin.strip() for origin in _raw_cors.split(",") if origin.strip()]

# Kiosk API Protection (optional)
KIOSK_API_KEY = os.getenv("KIOSK_API_KEY", "").strip()

# Multi-Stage CNN Vision Pipeline Configuration
# Stage 1: Face Detection & Alignment ("yunet", "retinaface", "yolo")
VISION_DETECTOR = os.getenv("VISION_DETECTOR", "yunet").lower()
# Stage 2: Anti-Spoofing & Liveness ("passive", "minifasnet", "hybrid")
VISION_LIVENESS = os.getenv("VISION_LIVENESS", "passive").lower()
# Stage 3: Feature Embedding ("sface", "arcface", "facenet")
VISION_EMBEDDER = os.getenv("VISION_EMBEDDER", "sface").lower()

# Deep Learning Model Paths & URLs
YUNET_MODEL_NAME = "face_detection_yunet_2023mar.onnx"
SFACE_MODEL_NAME = "face_recognition_sface_2021dec.onnx"
RETINAFACE_MODEL_NAME = "face_detection_retinaface_2023mar.onnx"
ARCFACE_MODEL_NAME = "face_recognition_arcface_2021dec.onnx"
FACENET_MODEL_NAME = "facenet_128d.onnx"
MINIFASNET_MODEL_NAME = "minifasnet_2.7_80x80.onnx"

YUNET_MODEL_PATH = MODELS_DIR / YUNET_MODEL_NAME
SFACE_MODEL_PATH = MODELS_DIR / SFACE_MODEL_NAME
RETINAFACE_MODEL_PATH = MODELS_DIR / RETINAFACE_MODEL_NAME
ARCFACE_MODEL_PATH = MODELS_DIR / ARCFACE_MODEL_NAME
FACENET_MODEL_PATH = MODELS_DIR / FACENET_MODEL_NAME
MINIFASNET_MODEL_PATH = MODELS_DIR / MINIFASNET_MODEL_NAME

YUNET_DOWNLOAD_URL = (
    "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
)
SFACE_DOWNLOAD_URL = (
    "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx"
)
RETINAFACE_DOWNLOAD_URL = (
    "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_retinaface/face_detection_retinaface_2023mar.onnx"
)
ARCFACE_DOWNLOAD_URL = (
    "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_arcface/face_recognition_arcface_2021dec.onnx"
)
FACENET_DOWNLOAD_URL = (
    "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx"
)
MINIFASNET_DOWNLOAD_URL = (
    "https://github.com/opencv/opencv_zoo/raw/main/models/silent_face_anti_spoofing/minifasnet.onnx"
)

# AI Recognition Thresholds
FACE_DETECTION_CONFIDENCE = float(os.getenv("FACE_DETECTION_CONFIDENCE", "0.70"))
FACE_SIMILARITY_THRESHOLD = float(os.getenv("FACE_SIMILARITY_THRESHOLD", "0.65"))
LIVENESS_LAPLACIAN_THRESHOLD = float(os.getenv("LIVENESS_LAPLACIAN_THRESHOLD", "30.0"))

# Attendance Engine Settings
PUNCH_COOLDOWN_SECONDS = int(os.getenv("PUNCH_COOLDOWN_SECONDS", "600"))
DEFAULT_SHIFT_START = "09:00:00"
DEFAULT_SHIFT_END = "17:00:00"
DEFAULT_GRACE_PERIOD_MINS = 15
