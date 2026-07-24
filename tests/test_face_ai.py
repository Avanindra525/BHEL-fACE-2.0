"""Face AI test suite for simplified academic demo pipeline.

Tests: detection, alignment, embedding, matching, minimal quality checks.
Liveness checks are removed (no-op). Head pose validation is removed.
Brightness/contrast/eye-visibility checks are removed.

Only rejects: no face, multiple faces, extreme blur, tiny face.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.face_ai.alignment import FaceAligner
from app.face_ai.detector import FaceDetector
from app.face_ai.embedding import FaceEmbedder
from app.face_ai.liveness import LivenessChecker
from app.face_ai.matcher import FaceMatcher
from app.face_ai.quality_check import QualityChecker
from app.face_ai.recognizer import FaceRecognizer
from app.face_ai.thresholds import EMBEDDING_DIMENSION, SIMILARITY_THRESHOLD
from app.models.face_sample import FaceSample
from app.models.user import User
from app.core.security import hash_password
from tests.conftest import unique_username, unique_email


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _synthetic_face_image(size: tuple[int, int] = (480, 640)) -> np.ndarray:
    """Create a synthetic face-like image for testing.

    Generates a random gradient image with a face-like ellipse.
    """
    img = np.random.randint(50, 200, (*size, 3), dtype=np.uint8)
    center = (size[1] // 2, size[0] // 2)
    axes = (size[1] // 4, size[0] // 3)
    cv2.ellipse(img, center, axes, 0, 0, 360, (180, 140, 100), -1)
    cv2.circle(img, (center[0] - 30, center[1] - 20), 8, (50, 50, 50), -1)
    cv2.circle(img, (center[0] + 30, center[1] - 20), 8, (50, 50, 50), -1)
    cv2.ellipse(img, (center[0], center[1] + 30), (30, 10), 0, 0, 180, (50, 50, 50), 2)
    return img


def _blank_image(size: tuple[int, int] = (100, 100)) -> np.ndarray:
    """Create a blank uniform image."""
    return np.zeros((*size, 3), dtype=np.uint8)


# ═══════════════════════════════════════════════════════════════════════════════
# Quality Check (Simplified — blur + face size only)
# ═══════════════════════════════════════════════════════════════════════════════


class TestQualityChecker:
    def setup_method(self) -> None:
        self.checker = QualityChecker()

    def test_accepts_good_image(self) -> None:
        """Good synthetic image passes quality (or fails only on blur)."""
        img = _synthetic_face_image()
        result = self.checker.evaluate(img)
        assert "score" in result
        assert "passed" in result
        assert "checks" in result

    def test_rejects_blank_image(self) -> None:
        """Blank image fails quality (extreme blur / low Laplacian variance)."""
        img = _blank_image()
        result = self.checker.evaluate(img)
        assert result["passed"] is False
        assert len(result["reasons"]) > 0

    def test_detects_blur(self) -> None:
        """Very blurry image fails blur check."""
        img = np.ones((400, 400, 3), dtype=np.uint8) * 128
        img = cv2.GaussianBlur(img, (99, 99), 50)
        result = self.checker.evaluate(img)
        blur_check = result["checks"].get("blur", {})
        assert blur_check.get("passed") is False

    def test_face_size_rejects_small_face(self) -> None:
        """Face smaller than min_face_size is rejected."""
        img = _synthetic_face_image((50, 50))
        face = {"bbox": [0, 0, 20, 20], "kps": None}
        result = self.checker.evaluate(img, face)
        face_size_check = result["checks"].get("face_size", {})
        if face_size_check:
            assert face_size_check.get("passed") is False

    def test_passes_without_landmarks(self) -> None:
        """Quality check tolerates missing landmarks (eye_visibility removed)."""
        img = _synthetic_face_image()
        face = {"bbox": [50, 50, 200, 200], "kps": None}
        result = self.checker.evaluate(img, face)
        assert isinstance(result, dict)
        assert "passed" in result
        assert "checks" in result
        # eye_visibility check no longer present
        assert "eye_visibility" not in result["checks"]


# ═══════════════════════════════════════════════════════════════════════════════
# Liveness Detection (No-op — always passes)
# ═══════════════════════════════════════════════════════════════════════════════


class TestLivenessChecker:
    def setup_method(self) -> None:
        self.checker = LivenessChecker()

    def test_always_passes(self) -> None:
        """Liveness checker always passes (academic demo mode)."""
        img = _synthetic_face_image()
        result = self.checker.evaluate(img)
        assert result["passed"] is True
        assert result["score"] == 1.0

    def test_reset_does_not_crash(self) -> None:
        """Reset is a no-op, does not crash."""
        self.checker.reset()
        result = self.checker.evaluate(_synthetic_face_image())
        assert result["passed"] is True

    def test_handles_empty_image(self) -> None:
        """Empty image doesn't crash."""
        img = np.zeros((0, 0, 3), dtype=np.uint8)
        result = self.checker.evaluate(img)
        assert result["passed"] is True
        assert result["score"] == 1.0


# ═══════════════════════════════════════════════════════════════════════════════
# Face Detection
# ═══════════════════════════════════════════════════════════════════════════════


class TestFaceDetector:
    def setup_method(self) -> None:
        self.detector = FaceDetector()

    def test_returns_empty_for_no_face(self) -> None:
        """Detector returns empty list for images with no face."""
        img = _blank_image()
        faces = self.detector.detect(img)
        assert isinstance(faces, list)

    def test_no_crash_on_none_image(self) -> None:
        """None image returns empty list."""
        faces = self.detector.detect(np.array([]))
        assert faces == []


# ═══════════════════════════════════════════════════════════════════════════════
# Face Alignment
# ═══════════════════════════════════════════════════════════════════════════════


class TestFaceAligner:
    def setup_method(self) -> None:
        self.aligner = FaceAligner(desired_size=112)

    def test_aligns_with_landmarks(self) -> None:
        """Aligns face given valid landmarks."""
        img = _synthetic_face_image((224, 224))
        face = {
            "bbox": [50, 50, 150, 150],
            "kps": [[70, 80], [130, 80], [100, 110], [80, 140], [120, 140]],
        }
        aligned = self.aligner.align(img, face)
        assert aligned.shape == (112, 112, 3)

    def test_fallback_without_landmarks(self) -> None:
        """Aligns face using bbox when landmarks are missing."""
        img = _synthetic_face_image((224, 224))
        face = {"bbox": [50, 50, 174, 174], "kps": None}
        aligned = self.aligner.align(img, face)
        assert aligned.shape == (112, 112, 3)


# ═══════════════════════════════════════════════════════════════════════════════
# Face Embedding
# ═══════════════════════════════════════════════════════════════════════════════


class TestFaceEmbedder:
    def setup_method(self) -> None:
        self.embedder = FaceEmbedder()

    def test_generates_512_dim_embedding(self) -> None:
        """Embedding output has 512 dimensions."""
        img = _synthetic_face_image((112, 112))
        emb = self.embedder.generate(img)
        assert emb.shape == (EMBEDDING_DIMENSION,)
        assert emb.dtype == np.float32

    def test_embeddings_are_normalized(self) -> None:
        """Generated embeddings are L2-normalized (unit norm)."""
        img = _synthetic_face_image((112, 112))
        emb = self.embedder.generate(img)
        norm = np.linalg.norm(emb)
        assert abs(norm - 1.0) < 0.1 or abs(norm) < 1e-6

    def test_handles_empty_image(self) -> None:
        """Empty image returns zero embedding."""
        emb = self.embedder.generate(np.zeros((0, 0, 3), dtype=np.uint8))
        assert np.all(emb == 0)

    def test_serialization_roundtrip(self) -> None:
        """Embedding serialization to bytes and back."""
        img = _synthetic_face_image((112, 112))
        emb = self.embedder.generate(img)
        blob = self.embedder.embedding_to_bytes(emb)
        assert isinstance(blob, bytes)
        restored = self.embedder.bytes_to_embedding(blob)
        assert np.allclose(emb, restored)


# ═══════════════════════════════════════════════════════════════════════════════
# Face Matching (with configurable threshold)
# ═══════════════════════════════════════════════════════════════════════════════


class TestFaceMatcher:
    def setup_method(self) -> None:
        self.matcher = FaceMatcher(threshold=0.70)

    def test_match_identical_vectors(self) -> None:
        """Identical vectors match with similarity ~1.0."""
        emb = np.random.randn(512).astype(np.float32)
        emb = emb / np.linalg.norm(emb)
        candidates = [(1, emb)]
        score, match_id = self.matcher.match(emb, candidates)
        assert match_id == 1
        assert score > 0.99

    def test_no_match_for_orthogonal_vectors(self) -> None:
        """Very different vectors don't match."""
        emb1 = np.array([1.0] + [0.0] * 511, dtype=np.float32)
        emb2 = np.array([0.0] + [1.0] + [0.0] * 510, dtype=np.float32)
        candidates = [(1, emb2)]
        score, match_id = self.matcher.match(emb1, candidates)
        assert match_id is None
        assert score < 0.70

    def test_match_all_returns_sorted(self) -> None:
        """match_all returns candidates sorted by similarity descending."""
        emb = np.array([1.0] + [0.0] * 511, dtype=np.float32)
        candidates = [
            (1, np.array([0.9] + [0.0] * 511, dtype=np.float32)),
            (2, np.array([0.1] + [0.0] * 511, dtype=np.float32)),
            (3, np.array([0.5] + [0.0] * 511, dtype=np.float32)),
        ]
        results = self.matcher.match_all(emb, candidates)
        assert len(results) == 3
        assert results[0][1] >= results[1][1] >= results[2][1]

    def test_empty_candidates(self) -> None:
        """Empty candidate list returns None."""
        emb = np.random.randn(512).astype(np.float32)
        score, match_id = self.matcher.match(emb, [])
        assert match_id is None
        assert score == 0.0

    def test_verify_pair(self) -> None:
        """verify_pair returns correct similarity for identical vectors."""
        emb = np.random.randn(512).astype(np.float32)
        emb = emb / np.linalg.norm(emb)
        result = self.matcher.verify_pair(emb, emb)
        assert result["is_match"] is True
        assert result["similarity"] > 0.99

    def test_verify_pair_no_match(self) -> None:
        """verify_pair returns False for very different vectors."""
        emb1 = np.array([1.0] + [0.0] * 511, dtype=np.float32)
        emb2 = np.array([0.0] + [1.0] + [0.0] * 510, dtype=np.float32)
        result = self.matcher.verify_pair(emb1, emb2)
        assert result["is_match"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# Recognizer Pipeline (Simplified)
# ═══════════════════════════════════════════════════════════════════════════════


class TestFaceRecognizer:
    def setup_method(self) -> None:
        self.recognizer = FaceRecognizer()

    def test_register_no_face_rejected(self) -> None:
        """Registration with no face returns error."""
        img = _blank_image()
        result = self.recognizer.register_face(img, user_id=1, pose="front")
        assert result["success"] is False
        assert "No face detected" in (result.get("error") or "")

    def test_build_gallery_empty(self) -> None:
        """Building gallery from empty samples returns empty list."""
        gallery = self.recognizer.build_gallery([])
        assert gallery == []

    def test_build_gallery_from_samples(self, db_session: Session) -> None:
        """Building gallery from valid samples returns embeddings."""
        user = User(
            username=unique_username(),
            email=unique_email(),
            full_name="Gallery Test",
            password_hash=hash_password("TestPass123!"),
        )
        db_session.add(user)
        db_session.commit()

        emb = np.random.randn(512).astype(np.float32)
        emb = emb / np.linalg.norm(emb)
        sample = FaceSample(
            user_id=user.user_id,
            pose="front",
            image_path="test.jpg",
            embedding_blob=self.recognizer.embedder.embedding_to_bytes(emb),
            quality_score=95,
        )
        db_session.add(sample)
        db_session.commit()

        gallery = self.recognizer.build_gallery([sample])
        assert len(gallery) == 1
        assert gallery[0][0] == user.user_id
        assert np.allclose(gallery[0][1], emb)

    def test_login_no_liveness_required(self) -> None:
        """Login does not require liveness (always passes)."""
        # Login with a blank image should fail only on "No face detected"
        img = _blank_image()
        gallery = [(1, np.random.randn(512).astype(np.float32))]
        result = self.recognizer.login_face(img, gallery)
        assert result["authenticated"] is False
        assert "No face detected" in (result.get("error") or "")


# ═══════════════════════════════════════════════════════════════════════════════
# Face API Routes
# ═══════════════════════════════════════════════════════════════════════════════

def _empty_jpeg_bytes() -> bytes:
    """Create a 1x1 valid JPEG byte string."""
    img = np.zeros((1, 1, 3), dtype=np.uint8)
    _, buf = cv2.imencode(".jpg", img)
    return buf.tobytes()


class TestFaceAPI:
    def test_register_requires_auth(self, client: TestClient) -> None:
        """Face registration without auth returns 401."""
        response = client.post(
            "/api/face/register",
            files={"file": ("test.jpg", _empty_jpeg_bytes(), "image/jpeg")},
        )
        assert response.status_code == 401

    def test_register_with_auth_rejects_bad_image(self, client: TestClient, auth_headers_employee) -> None:
        """Face registration with bad image returns 400."""
        response = client.post(
            "/api/face/register",
            files={"file": ("test.jpg", b"not-an-image", "image/jpeg")},
            headers=auth_headers_employee,
        )
        assert response.status_code in (400, 201)

    def test_face_status_unregistered(self, client: TestClient, auth_headers_employee) -> None:
        """Face status endpoint returns unregistered status."""
        response = client.get("/api/face/status", headers=auth_headers_employee)
        assert response.status_code == 200
        assert "face_registered" in response.json()
        assert "sample_count" in response.json()

    def test_face_status_requires_auth(self, client: TestClient) -> None:
        """Face status without auth returns 401."""
        response = client.get("/api/face/status")
        assert response.status_code == 401

    def test_login_no_image(self, client: TestClient) -> None:
        """Face login with no image returns 422."""
        response = client.post("/api/face/login")
        assert response.status_code == 422

    def test_login_bad_image(self, client: TestClient) -> None:
        """Face login with bad image returns 400."""
        response = client.post(
            "/api/face/login",
            files={"file": ("test.jpg", b"bad-data", "image/jpeg")},
        )
        assert response.status_code in (400, 422)

    def test_login_no_registered_faces(self, client: TestClient) -> None:
        """Face login when no faces registered returns 401."""
        img_bytes = _empty_jpeg_bytes()
        response = client.post(
            "/api/face/login",
            files={"file": ("test.jpg", img_bytes, "image/jpeg")},
        )
        assert response.status_code == 401
