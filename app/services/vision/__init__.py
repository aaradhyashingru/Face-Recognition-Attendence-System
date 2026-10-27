"""
Multi-Stage Vision Pipeline Package.
"""

from app.services.vision.base import (
    BaseDetector,
    BaseLivenessDetector,
    BaseEmbedder,
    FaceDetectionResult,
    LivenessResult,
)
from app.services.vision.detectors import (
    YuNetDetector,
    RetinaFaceDetector,
    YoloFaceDetector,
    DetectorFactory,
    align_face_5point,
)
from app.services.vision.liveness import (
    PassiveMultiCueLiveness,
    MiniFASNetLiveness,
    HybridLivenessDetector,
    LivenessFactory,
)
from app.services.vision.embedders import (
    SFaceEmbedder,
    ArcFaceEmbedder,
    FaceNetEmbedder,
    EmbedderFactory,
)
from app.services.vision.pipeline import (
    VisionEngine,
    EmbeddingCache,
    get_vision_engine,
)

__all__ = [
    "BaseDetector",
    "BaseLivenessDetector",
    "BaseEmbedder",
    "FaceDetectionResult",
    "LivenessResult",
    "YuNetDetector",
    "RetinaFaceDetector",
    "YoloFaceDetector",
    "DetectorFactory",
    "align_face_5point",
    "PassiveMultiCueLiveness",
    "MiniFASNetLiveness",
    "HybridLivenessDetector",
    "LivenessFactory",
    "SFaceEmbedder",
    "ArcFaceEmbedder",
    "FaceNetEmbedder",
    "EmbedderFactory",
    "VisionEngine",
    "EmbeddingCache",
    "get_vision_engine",
]
