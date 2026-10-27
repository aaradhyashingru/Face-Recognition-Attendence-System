"""
Base abstractions and standard data structures for the Multi-Stage Vision Pipeline.
Stage 1: Face Detection & 5-Point Alignment
Stage 2: Anti-Spoofing & Liveness Verification
Stage 3: Deep Feature Embedding & Metric Classification
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Tuple, List, Dict, Any
import numpy as np


@dataclass
class FaceDetectionResult:
    """Standardized representation of a detected face with 5 facial landmarks."""
    bbox: List[int]  # [x, y, w, h]
    confidence: float
    landmarks: Optional[List[Tuple[float, float]]] = None  # [(re_x, re_y), (le_x, le_y), (nt_x, nt_y), (rm_x, rm_y), (lm_x, lm_y)]
    raw_array: Optional[np.ndarray] = None


@dataclass
class LivenessResult:
    """Anti-spoofing verification result with telemetry breakdown."""
    is_live: bool
    score: float
    method: str = "passive"
    telemetry: Dict[str, Any] = field(default_factory=dict)
    message: str = "Live face verified"


class BaseDetector(ABC):
    """Abstract Base Class for Stage 1: Face Detection & Alignment."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the detector (e.g., 'YuNet', 'RetinaFace', 'YOLOv8-Face')."""
        pass

    @abstractmethod
    def detect(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """
        Detect faces in image frame.
        Returns numpy array of detected faces with bounding boxes & 5 landmarks:
        [x, y, w, h, x_re, y_re, x_le, y_le, x_nt, y_nt, x_rm, y_rm, x_lm, y_lm, score]
        """
        pass

    @abstractmethod
    def align(self, frame: np.ndarray, face_info: np.ndarray, target_size: Tuple[int, int] = (112, 112)) -> np.ndarray:
        """
        Affine-warp and align face using 5 facial landmarks (eyes, nose, mouth).
        Standardized input for feature embedders.
        """
        pass


class BaseLivenessDetector(ABC):
    """Abstract Base Class for Stage 2: Anti-Spoofing & Liveness Detection."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of liveness module (e.g. 'PassiveMultiCue', 'MiniFASNet', 'Hybrid')."""
        pass

    @abstractmethod
    def check_liveness(self, frame: np.ndarray, face_info: np.ndarray) -> Tuple[bool, float]:
        """
        Analyze face for physical presence vs printed photo/screen/replay attacks.
        Returns (is_live: bool, confidence_score: float).
        """
        pass


class BaseEmbedder(ABC):
    """Abstract Base Class for Stage 3: Deep Feature Embedding & Metric Representation."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the embedder (e.g., 'SFace', 'ArcFace', 'FaceNet')."""
        pass

    @property
    @abstractmethod
    def vector_dim(self) -> int:
        """Dimensionality of embedding vector (e.g. 128 or 512)."""
        pass

    @abstractmethod
    def extract(self, frame: np.ndarray, face_info: np.ndarray) -> Optional[np.ndarray]:
        """
        Extract normalized L2 unit feature vector (||v|| = 1.0) from aligned face crop.
        """
        pass
