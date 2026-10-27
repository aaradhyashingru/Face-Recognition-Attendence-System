"""
Stage 2: Face Liveness & Anti-Spoofing Modules.
Defends against Presentation Attacks (photos, screen replays, 3D masks).
Supports:
1. PassiveMultiCueLiveness (Laplacian micro-texture + HSV chromatic diversity + specular glare)
2. MiniFASNetLiveness (Silent-Face-Anti-Spoofing deep CNN)
3. HybridLivenessDetector (Fusion of physical texture cues + deep neural verification)
"""

from typing import Tuple, Dict, Any
import cv2
import numpy as np

from app.config import (
    MINIFASNET_MODEL_PATH,
    MINIFASNET_DOWNLOAD_URL,
    LIVENESS_LAPLACIAN_THRESHOLD,
    logger,
)
from app.services.vision.base import BaseLivenessDetector, LivenessResult


class PassiveMultiCueLiveness(BaseLivenessDetector):
    """
    Physical-cue passive anti-spoofing detector.
    Analyzes:
    1. High-frequency skin micro-texture via discrete 2D Laplacian operator.
    2. Chromatic richness & HSV saturation standard deviation.
    3. Specular glare / screen backlight reflection hot-spots.
    4. 3D morphological aspect ratio sanity.
    """

    def __init__(self, laplacian_threshold: float = LIVENESS_LAPLACIAN_THRESHOLD):
        self.laplacian_threshold = laplacian_threshold

    @property
    def name(self) -> str:
        return "Passive Multi-Cue (Texture + Chromatic + Glare)"

    def check_liveness(self, frame: np.ndarray, face_info: np.ndarray) -> Tuple[bool, float]:
        res = self.evaluate(frame, face_info)
        return res.is_live, res.score

    def evaluate(self, frame: np.ndarray, face_info: np.ndarray) -> LivenessResult:
        try:
            x, y, w, h = map(int, face_info[0:4])
            h_img, w_img = frame.shape[:2]

            # Bounding box bounds check
            x = max(0, x)
            y = max(0, y)
            w = min(w, w_img - x)
            h = min(h, h_img - y)

            if w < 40 or h < 40:
                return LivenessResult(
                    is_live=False,
                    score=0.0,
                    method="passive_multicue",
                    telemetry={"error": "Face crop too small"},
                    message="Face resolution insufficient for anti-spoofing",
                )

            face_crop = frame[y : y + h, x : x + w]
            gray_face = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)

            # 1. High-frequency micro-texture via Laplacian variance
            lap_var = float(cv2.Laplacian(gray_face, cv2.CV_64F).var())

            # 2. Chromatic diversity check (detects flat B&W prints or color-cast displays)
            hsv_face = cv2.cvtColor(face_crop, cv2.COLOR_BGR2HSV)
            sat_std = float(np.std(hsv_face[:, :, 1]))
            val_mean = float(np.mean(hsv_face[:, :, 2]))

            # 3. Specular screen reflection test (hotspot pixel ratio)
            bright_pixels = np.count_nonzero(gray_face > 248)
            hotspot_ratio = float(bright_pixels) / float(w * h)
            is_screen_glare = hotspot_ratio > 0.12

            # 4. Aspect ratio check
            aspect = float(w) / float(h)
            is_valid_aspect = 0.55 <= aspect <= 1.45

            # Compute normalized confidence scores
            lap_score = min(1.0, lap_var / (self.laplacian_threshold * 2.5))
            sat_score = min(1.0, sat_std / 30.0)
            glare_penalty = 0.4 if is_screen_glare else 0.0

            combined_score = max(0.0, min(1.0, (0.65 * lap_score + 0.35 * sat_score) - glare_penalty))

            # Evaluation thresholds
            is_live = (
                lap_var >= self.laplacian_threshold
                and sat_std >= 10.0
                and not is_screen_glare
                and is_valid_aspect
            )

            telemetry = {
                "laplacian_variance": round(lap_var, 2),
                "saturation_std": round(sat_std, 2),
                "val_mean": round(val_mean, 2),
                "hotspot_glare_ratio": round(hotspot_ratio, 4),
                "aspect_ratio": round(aspect, 2),
                "is_screen_glare": is_screen_glare,
            }

            msg = "Live human face verified" if is_live else "Anti-spoofing alert: Screen reflection or photo print detected"

            return LivenessResult(
                is_live=bool(is_live),
                score=round(float(combined_score), 3),
                method="passive_multicue",
                telemetry=telemetry,
                message=msg,
            )
        except Exception as e:
            logger.warning("Passive liveness evaluation error: %s", e)
            return LivenessResult(is_live=False, score=0.0, message=f"Liveness error: {e}")


class MiniFASNetLiveness(BaseLivenessDetector):
    """
    Silent-Face-Anti-Spoofing Deep Neural Network (MiniFASNet).
    Evaluates multi-scale cropped patches to verify live 3D depth and material reflectance.
    """

    def __init__(self):
        self._fallback = PassiveMultiCueLiveness()
        self.net = None
        if MINIFASNET_MODEL_PATH.exists() and MINIFASNET_MODEL_PATH.stat().st_size >= 1000000:
            try:
                self.net = cv2.dnn.readNetFromONNX(str(MINIFASNET_MODEL_PATH.resolve()))
                logger.info("MiniFASNet Deep Anti-Spoofing engine initialized.")
            except Exception as e:
                logger.warning("Could not initialize MiniFASNet ONNX (%s). Using MultiCue fallback.", e)

    @property
    def name(self) -> str:
        return "MiniFASNet (Silent-Face Anti-Spoofing)" if self.net is not None else "MiniFASNet (MultiCue Fallback)"

    def check_liveness(self, frame: np.ndarray, face_info: np.ndarray) -> Tuple[bool, float]:
        if self.net is None:
            return self._fallback.check_liveness(frame, face_info)

        try:
            # Crop 80x80 scaled region for MiniFASNet inference
            x, y, w, h = map(int, face_info[0:4])
            h_img, w_img = frame.shape[:2]
            cx, cy = x + w // 2, y + h // 2
            scale = 2.7
            box_size = int(max(w, h) * scale)
            x1 = max(0, cx - box_size // 2)
            y1 = max(0, cy - box_size // 2)
            x2 = min(w_img, cx + box_size // 2)
            y2 = min(h_img, cy + box_size // 2)

            crop = frame[y1:y2, x1:x2]
            if crop.size == 0:
                return self._fallback.check_liveness(frame, face_info)

            blob = cv2.dnn.blobFromImage(crop, 1.0, (80, 80), (0, 0, 0), swapRB=True)
            self.net.setInput(blob)
            preds = self.net.forward()
            # Softmax
            exp_preds = np.exp(preds - np.max(preds))
            probs = exp_preds / np.sum(exp_preds)
            real_prob = float(probs[0][1]) if probs.shape[-1] >= 2 else float(probs[0][0])
            is_live = real_prob >= 0.70
            return is_live, round(real_prob, 3)
        except Exception as e:
            logger.warning("MiniFASNet inference error (%s). Falling back to MultiCue.", e)
            return self._fallback.check_liveness(frame, face_info)


class HybridLivenessDetector(BaseLivenessDetector):
    """
    Defense-in-depth: Fuses physical micro-texture analysis with deep learning anti-spoofing.
    Prevents single-point-of-failure vulnerabilities in biometric verification.
    """

    def __init__(self):
        self.passive_engine = PassiveMultiCueLiveness()
        self.deep_engine = MiniFASNetLiveness()

    @property
    def name(self) -> str:
        return "Hybrid Anti-Spoofing (Physical Texture + Deep Multi-Scale)"

    def check_liveness(self, frame: np.ndarray, face_info: np.ndarray) -> Tuple[bool, float]:
        p_live, p_score = self.passive_engine.check_liveness(frame, face_info)
        d_live, d_score = self.deep_engine.check_liveness(frame, face_info)

        # Fused decision: Both physical texture and deep model must agree for highest security
        if self.deep_engine.net is not None:
            fused_score = round(0.5 * p_score + 0.5 * d_score, 3)
            fused_live = p_live and d_live
        else:
            fused_score = p_score
            fused_live = p_live

        return fused_live, fused_score


class LivenessFactory:
    """Factory resolver for Stage 2 Anti-Spoofing."""

    @staticmethod
    def create(liveness_type: str = "passive") -> BaseLivenessDetector:
        liveness_type = (liveness_type or "passive").lower().strip()
        if liveness_type == "minifasnet":
            return MiniFASNetLiveness()
        elif liveness_type == "hybrid":
            return HybridLivenessDetector()
        else:
            return PassiveMultiCueLiveness()
