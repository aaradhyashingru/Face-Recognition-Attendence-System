"""
Multi-Stage Vision Pipeline Orchestrator.
Coordinates:
  Stage 1: Face Detection & 5-Point Alignment (YuNet / RetinaFace / YOLOv8-Face)
  Stage 2: Anti-Spoofing & Liveness Analysis (Passive Multi-Cue / MiniFASNet / Hybrid)
  Stage 3: Deep Feature Embedding & Metric Representation (SFace / ArcFace / FaceNet)
  Stage 4: In-Memory Metric Classification (Cosine Similarity Matching Engine)
"""

import base64
from typing import Optional, Tuple, List, Dict, Any
import cv2
import numpy as np
from sqlalchemy.orm import Session

from app.config import (
    VISION_DETECTOR,
    VISION_EMBEDDER,
    VISION_LIVENESS,
    FACE_SIMILARITY_THRESHOLD,
    logger,
)
from app.services.vision.base import BaseDetector, BaseLivenessDetector, BaseEmbedder
from app.services.vision.detectors import DetectorFactory
from app.services.vision.liveness import LivenessFactory
from app.services.vision.embedders import EmbedderFactory


class VisionEngine:
    """
    Enterprise Multi-Stage Deep Learning Face Recognition Engine.
    Orchestrates modular detection, anti-spoofing, and embedding stages.
    """
    _instance: Optional["VisionEngine"] = None

    def __init__(
        self,
        detector_type: str = VISION_DETECTOR,
        liveness_type: str = VISION_LIVENESS,
        embedder_type: str = VISION_EMBEDDER,
    ):
        logger.info(
            "Initializing Multi-Stage Vision Pipeline [Detector: %s, Liveness: %s, Embedder: %s]...",
            detector_type,
            liveness_type,
            embedder_type,
        )
        self.detector: BaseDetector = DetectorFactory.create(detector_type)
        self.liveness: BaseLivenessDetector = LivenessFactory.create(liveness_type)
        self.embedder: BaseEmbedder = EmbedderFactory.create(embedder_type)

        logger.info(
            "Multi-Stage Vision Pipeline Ready: %s | %s | %s (%d-D vector)",
            self.detector.name,
            self.liveness.name,
            self.embedder.name,
            self.embedder.vector_dim,
        )

    @classmethod
    def get_instance(cls) -> "VisionEngine":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_pipeline_info(self) -> Dict[str, Any]:
        """Telemetry metadata about currently active pipeline components."""
        return {
            "detector": self.detector.name,
            "liveness": self.liveness.name,
            "embedder": self.embedder.name,
            "vector_dimension": self.embedder.vector_dim,
        }

    def decode_base64_frame(self, base64_str: str) -> Optional[np.ndarray]:
        """Decode base64 data URL from browser canvas to OpenCV BGR numpy array."""
        try:
            if "," in base64_str:
                base64_str = base64_str.split(",", 1)[1]
            image_data = base64.b64decode(base64_str)
            np_arr = np.frombuffer(image_data, np.uint8)
            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            return frame
        except Exception as e:
            logger.warning("Frame decode error: %s", e)
            return None

    def detect_faces(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """
        Stage 1: Detect all frontal and angled faces in frame.
        Returns face array with bounding boxes and 5 landmarks.
        """
        return self.detector.detect(frame)

    def check_liveness(self, frame: np.ndarray, face_info: np.ndarray) -> Tuple[bool, float]:
        """
        Stage 2: Anti-spoofing and human liveness assessment.
        Returns (is_live: bool, confidence_score: float).
        """
        return self.liveness.check_liveness(frame, face_info)

    def extract_embedding(self, frame: np.ndarray, face_info: np.ndarray) -> Optional[np.ndarray]:
        """
        Stage 3: Deep metric feature embedding extraction (unit L2-normalized).
        """
        return self.embedder.extract(frame, face_info)

    def match_embedding(
        self,
        query_vec: np.ndarray,
        registered_records: List[Tuple[int, np.ndarray]],
        threshold: float = FACE_SIMILARITY_THRESHOLD,
    ) -> Tuple[Optional[int], float]:
        """
        Stage 4: In-Memory Metric Classification.
        Computes Cosine Similarity against active registered user embeddings.
        Returns (matched_user_id, confidence) if >= threshold, else (None, confidence).
        """
        if not registered_records:
            return None, 0.0

        best_user_id = None
        best_similarity = -1.0

        q_norm = np.linalg.norm(query_vec)
        if q_norm < 1e-6:
            return None, 0.0

        for user_id, reg_vec in registered_records:
            r_norm = np.linalg.norm(reg_vec)
            if r_norm < 1e-6:
                continue

            # Check vector dimensionality consistency
            if len(query_vec) != len(reg_vec):
                continue

            # Cosine similarity: (A . B) / (||A|| * ||B||)
            similarity = float(np.dot(query_vec, reg_vec) / (q_norm * r_norm))
            if similarity > best_similarity:
                best_similarity = similarity
                best_user_id = user_id

        # Clamp similarity to 0.0..1.0 range for readable UI display
        normalized_conf = max(0.0, min(1.0, (best_similarity + 1.0) / 2.0))

        if best_similarity >= threshold:
            return best_user_id, round(normalized_conf, 3)
        return None, round(normalized_conf, 3)


class EmbeddingCache:
    """High-performance in-memory cache of registered face embeddings."""
    _cached_records: Optional[List[Tuple[int, np.ndarray]]] = None
    _dirty: bool = True

    @classmethod
    def invalidate(cls):
        """Invalidate cache when a user is enrolled, updated, or deleted."""
        cls._dirty = True
        cls._cached_records = None

    @classmethod
    def get_embeddings(cls, db: Session) -> List[Tuple[int, np.ndarray]]:
        """Retrieve pre-parsed vector records from RAM or reload from DB if dirty."""
        if cls._dirty or cls._cached_records is None:
            from app.models import FaceEmbedding, User
            all_embeddings = (
                db.query(FaceEmbedding)
                .join(User)
                .filter(User.is_active == True)
                .all()
            )
            records = []
            for emb in all_embeddings:
                try:
                    records.append((emb.user_id, np.array(emb.get_vector(), dtype=np.float32)))
                except Exception as e:
                    logger.warning("Error parsing embedding for user %s: %s", emb.user_id, e)
            cls._cached_records = records
            cls._dirty = False
        return cls._cached_records


def get_vision_engine() -> VisionEngine:
    """Singleton accessor for the vision pipeline."""
    return VisionEngine.get_instance()
