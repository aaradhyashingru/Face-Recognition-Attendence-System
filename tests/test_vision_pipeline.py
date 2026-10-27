import unittest

try:
    import numpy as np
    import cv2
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False


class TestMultiStageVisionPipeline(unittest.TestCase):
    @unittest.skipUnless(NUMPY_AVAILABLE, "NumPy and OpenCV required for Vision Pipeline tests")
    def test_01_detector_factory(self):
        from app.services.vision.base import BaseDetector
        from app.services.vision.detectors import (
            DetectorFactory,
            YuNetDetector,
            RetinaFaceDetector,
            YoloFaceDetector,
        )
        d_yunet = DetectorFactory.create("yunet")
        self.assertIsInstance(d_yunet, YuNetDetector)
        self.assertTrue(issubclass(type(d_yunet), BaseDetector))

        d_retina = DetectorFactory.create("retinaface")
        self.assertIsInstance(d_retina, RetinaFaceDetector)

        d_yolo = DetectorFactory.create("yolo")
        self.assertIsInstance(d_yolo, YoloFaceDetector)

    @unittest.skipUnless(NUMPY_AVAILABLE, "NumPy and OpenCV required for Vision Pipeline tests")
    def test_02_liveness_factory(self):
        from app.services.vision.base import BaseLivenessDetector
        from app.services.vision.liveness import (
            LivenessFactory,
            PassiveMultiCueLiveness,
            MiniFASNetLiveness,
            HybridLivenessDetector,
        )
        l_passive = LivenessFactory.create("passive")
        self.assertIsInstance(l_passive, PassiveMultiCueLiveness)
        self.assertTrue(issubclass(type(l_passive), BaseLivenessDetector))

        l_mini = LivenessFactory.create("minifasnet")
        self.assertIsInstance(l_mini, MiniFASNetLiveness)

        l_hybrid = LivenessFactory.create("hybrid")
        self.assertIsInstance(l_hybrid, HybridLivenessDetector)

    @unittest.skipUnless(NUMPY_AVAILABLE, "NumPy and OpenCV required for Vision Pipeline tests")
    def test_03_embedder_factory(self):
        from app.services.vision.base import BaseEmbedder
        from app.services.vision.embedders import (
            EmbedderFactory,
            SFaceEmbedder,
            ArcFaceEmbedder,
            FaceNetEmbedder,
        )
        e_sface = EmbedderFactory.create("sface")
        self.assertIsInstance(e_sface, SFaceEmbedder)
        self.assertEqual(e_sface.vector_dim, 128)
        self.assertTrue(issubclass(type(e_sface), BaseEmbedder))

        e_arc = EmbedderFactory.create("arcface")
        self.assertIsInstance(e_arc, ArcFaceEmbedder)
        self.assertIn(e_arc.vector_dim, (128, 512))

        e_facenet = EmbedderFactory.create("facenet")
        self.assertIsInstance(e_facenet, FaceNetEmbedder)

    @unittest.skipUnless(NUMPY_AVAILABLE, "NumPy and OpenCV required for Vision Pipeline tests")
    def test_04_cosine_similarity_matching(self):
        from app.services.vision.pipeline import VisionEngine
        engine = VisionEngine(detector_type="yunet", liveness_type="passive", embedder_type="sface")
        
        # Test 128-D matching
        v1 = np.random.randn(128).astype(np.float32)
        v1 = v1 / np.linalg.norm(v1)
        v2 = v1.copy()
        v3 = np.random.randn(128).astype(np.float32)
        v3 = v3 / np.linalg.norm(v3)

        matched_id, conf = engine.match_embedding(v1, [(10, v2), (20, v3)], threshold=0.65)
        self.assertEqual(matched_id, 10)
        self.assertGreater(conf, 0.9)

        # Test 512-D matching
        v512_a = np.random.randn(512).astype(np.float32)
        v512_a = v512_a / np.linalg.norm(v512_a)
        v512_b = v512_a.copy()

        matched_512, conf_512 = engine.match_embedding(v512_a, [(42, v512_b)], threshold=0.65)
        self.assertEqual(matched_512, 42)
        self.assertGreater(conf_512, 0.9)

    @unittest.skipUnless(NUMPY_AVAILABLE, "NumPy and OpenCV required for Vision Pipeline tests")
    def test_05_5point_alignment_matrix(self):
        from app.services.vision.detectors import align_face_5point, REFERENCE_LANDMARKS_112x112
        self.assertEqual(REFERENCE_LANDMARKS_112x112.shape, (5, 2))
        dummy_frame = np.zeros((200, 200, 3), dtype=np.uint8)
        landmarks = np.array([
            [60, 70],
            [120, 70],
            [90, 100],
            [70, 130],
            [110, 130],
        ], dtype=np.float32)
        aligned = align_face_5point(dummy_frame, landmarks, (112, 112))
        self.assertEqual(aligned.shape, (112, 112, 3))


if __name__ == "__main__":
    unittest.main()
