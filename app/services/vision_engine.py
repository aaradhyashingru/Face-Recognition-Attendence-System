import base64
import os
import urllib.request
from typing import Optional, Tuple, List, Dict
import cv2
import numpy as np

from app.config import (
    YUNET_MODEL_PATH,
    SFACE_MODEL_PATH,
    YUNET_DOWNLOAD_URL,
    SFACE_DOWNLOAD_URL,
    FACE_DETECTION_CONFIDENCE,
    FACE_SIMILARITY_THRESHOLD,
    LIVENESS_LAPLACIAN_THRESHOLD,
)


class VisionEngine:
    _instance: Optional["VisionEngine"] = None

    def __init__(self):
        self._ensure_models_downloaded()
        print("Loading OpenCV Deep Learning YuNet and SFace models...")
        # FaceDetectorYN: input size will be dynamically adjusted per frame
        self.detector = cv2.FaceDetectorYN.create(
            str(YUNET_MODEL_PATH),
            "",
            (320, 320),
            score_threshold=FACE_DETECTION_CONFIDENCE,
            nms_threshold=0.3,
            top_k=5000,
        )
        self.recognizer = cv2.FaceRecognizerSF.create(str(SFACE_MODEL_PATH), "")
        print("AI Vision Engine successfully initialized!")

    @classmethod
    def get_instance(cls) -> "VisionEngine":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _ensure_models_downloaded(self):
        """Download YuNet & SFace ONNX models from OpenCV Zoo if not present."""
        if not YUNET_MODEL_PATH.exists():
            print(f"Downloading YuNet Face Detector model to {YUNET_MODEL_PATH}...")
            urllib.request.urlretrieve(YUNET_DOWNLOAD_URL, str(YUNET_MODEL_PATH))
            print("YuNet model download complete.")

        if not SFACE_MODEL_PATH.exists():
            print(f"Downloading SFace Face Recognizer model to {SFACE_MODEL_PATH}...")
            urllib.request.urlretrieve(SFACE_DOWNLOAD_URL, str(SFACE_MODEL_PATH))
            print("SFace model download complete.")

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
            print(f"Frame decode error: {e}")
            return None

    def check_liveness(self, frame: np.ndarray, face_info: np.ndarray) -> Tuple[bool, float]:
        """
        Passive Liveness and Anti-Spoofing assessment.
        Analyzes high-frequency texture micro-variations (Laplacian variance)
        and color distribution to detect photo/screen replay attacks.
        """
        try:
            x, y, w, h = map(int, face_info[0:4])
            h_img, w_img = frame.shape[:2]

            # Bounding box sanity checks
            x = max(0, x)
            y = max(0, y)
            w = min(w, w_img - x)
            h = min(h, h_img - y)

            if w < 40 or h < 40:
                return False, 0.0

            face_crop = frame[y : y + h, x : x + w]
            gray_face = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)

            # 1. Texture analysis via Laplacian variance
            lap_var = cv2.Laplacian(gray_face, cv2.CV_64F).var()

            # 2. Chromatic diversity check (detect flat/monochrome printouts)
            hsv_face = cv2.cvtColor(face_crop, cv2.COLOR_BGR2HSV)
            sat_std = float(np.std(hsv_face[:, :, 1]))

            # Normalized liveness score between 0.0 and 1.0
            lap_score = min(1.0, lap_var / (LIVENESS_LAPLACIAN_THRESHOLD * 2.5))
            sat_score = min(1.0, sat_std / 30.0)
            combined_liveness = 0.7 * lap_score + 0.3 * sat_score

            is_live = lap_var >= LIVENESS_LAPLACIAN_THRESHOLD and sat_std >= 10.0
            return bool(is_live), round(float(combined_liveness), 3)
        except Exception as e:
            print(f"Liveness check error: {e}")
            return False, 0.0

    def detect_faces(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """
        Detect faces in image frame using YuNet.
        Returns array of detected faces with bounding boxes & 5 landmarks.
        """
        h, w = frame.shape[:2]
        self.detector.setInputSize((w, h))
        _, faces = self.detector.detect(frame)
        return faces

    def extract_embedding(self, frame: np.ndarray, face_info: np.ndarray) -> Optional[np.ndarray]:
        """
        Align face using 5 landmarks and extract 128-d normalized embedding with SFace.
        """
        try:
            aligned_face = self.recognizer.alignCrop(frame, face_info)
            feature = self.recognizer.feature(aligned_face)
            # Flatten and normalize
            vec = feature.flatten().astype(np.float32)
            norm = np.linalg.norm(vec)
            if norm > 1e-6:
                vec = vec / norm
            return vec
        except Exception as e:
            print(f"Feature extraction error: {e}")
            return None

    def match_embedding(
        self,
        query_vec: np.ndarray,
        registered_records: List[Tuple[int, np.ndarray]],
        threshold: float = FACE_SIMILARITY_THRESHOLD,
    ) -> Tuple[Optional[int], float]:
        """
        Perform Cosine Similarity comparison against registered user vectors.
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


# Singleton accessor
def get_vision_engine() -> VisionEngine:
    return VisionEngine.get_instance()
