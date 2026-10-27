"""
FRAS Enterprise Vision Engine Entry Point.
Delegates to modular Multi-Stage Vision Pipeline in `app.services.vision`:
  - Stage 1: Face Detection & 5-Point Alignment (YuNet / RetinaFace / YOLOv8)
  - Stage 2: Anti-Spoofing & Liveness (Passive Multi-Cue / MiniFASNet / Hybrid)
  - Stage 3: Deep Feature Embedding (SFace / ArcFace / FaceNet)
  - Stage 4: Cosine Similarity Matching & Vector Cache
"""

from app.services.vision import (
    VisionEngine,
    EmbeddingCache,
    get_vision_engine,
    BaseDetector,
    BaseLivenessDetector,
    BaseEmbedder,
    DetectorFactory,
    LivenessFactory,
    EmbedderFactory,
    YuNetDetector,
    RetinaFaceDetector,
    YoloFaceDetector,
    PassiveMultiCueLiveness,
    MiniFASNetLiveness,
    HybridLivenessDetector,
    SFaceEmbedder,
    ArcFaceEmbedder,
    FaceNetEmbedder,
)

__all__ = [
    "VisionEngine",
    "EmbeddingCache",
    "get_vision_engine",
    "BaseDetector",
    "BaseLivenessDetector",
    "BaseEmbedder",
    "DetectorFactory",
    "LivenessFactory",
    "EmbedderFactory",
    "YuNetDetector",
    "RetinaFaceDetector",
    "YoloFaceDetector",
    "PassiveMultiCueLiveness",
    "MiniFASNetLiveness",
    "HybridLivenessDetector",
    "SFaceEmbedder",
    "ArcFaceEmbedder",
    "FaceNetEmbedder",
]
