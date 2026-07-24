"""Face Recognition Pipeline Orchestrator (Simplified).

Registration:  detect → minimal quality (blur, face size) → align → embed → store
Login:         detect → align → embed → match → authenticate

No liveness checks, no head pose validation, no blink detection,
no brightness/contrast/eye-visibility checks.

This is an academic demonstration project.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from app.core.config import settings
from app.core.logging import logger
from app.face_ai.detector import FaceDetector
from app.face_ai.alignment import FaceAligner
from app.face_ai.quality_check import QualityChecker
from app.face_ai.liveness import LivenessChecker
from app.face_ai.embedding import FaceEmbedder
from app.face_ai.matcher import FaceMatcher


class FaceRecognizer:
    """Orchestrates the end-to-end face recognition pipeline.

    Singleton pattern — one instance per application lifetime.

    Attributes:
        detector: SCRFD face detector.
        aligner: Facial landmark aligner.
        quality_checker: Minimal quality validator (blur + face size only).
        embedder: ArcFace embedding generator.
        matcher: Cosine similarity matcher.
    """

    _instance: FaceRecognizer | None = None

    def __new__(cls) -> FaceRecognizer:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        self._initialized = True

        logger.info("initializing_face_recognizer_pipeline")

        self.detector = FaceDetector(
            model_name=settings.insightface_model_name,
            min_face_size=80,
            det_threshold=0.5,
        )

        self.aligner = FaceAligner(desired_size=112)
        self.quality_checker = QualityChecker(
            min_blur_threshold=80.0,
            min_face_size=80,
        )
        # Liveness checker is a no-op — always reports live
        self.liveness_checker = LivenessChecker()
        self.embedder = FaceEmbedder(model_name=settings.insightface_model_name)
        self.matcher = FaceMatcher(threshold=settings.face_similarity_threshold)

        # Ensure upload directory exists
        self.upload_dir = settings.upload_dir
        self.upload_dir.mkdir(parents=True, exist_ok=True)

        logger.info("face_recognizer_initialized")

    # ------------------------------------------------------------------
    # Registration Pipeline
    # ------------------------------------------------------------------

    def register_face(
        self,
        image: np.ndarray,
        user_id: int,
        pose: str = "front",
        staff_number: str | None = None,
    ) -> dict[str, Any]:
        """Process a face image for registration.

        Simplified pipeline:
          1. Detect exactly one face (reject 0 or >1 faces)
          2. Validate quality (blur + face size only)
          3. Align face to canonical position
          4. Generate ArcFace embedding (512-d, L2-normalized)
          5. Save JPEG image to disk
          6. Return embedding for Oracle storage

        Args:
            image: BGR image from camera/file.
            user_id: Database user ID.
            pose: Pose label ('front', 'left', 'right', 'up').
            staff_number: Employee staff number for audit.

        Returns:
            Dict with:
                - success: bool
                - embedding: 512-dim numpy array (or None)
                - embedding_bytes: pickled bytes for Oracle BLOB
                - image_path: saved file path
                - quality_score: float (1.0 or 0.0)
                - face: detected face dict
                - checks: quality check results
                - error: error message if failed
        """
        result: dict[str, Any] = {
            "success": False,
            "embedding": None,
            "embedding_bytes": None,
            "image_path": None,
            "quality_score": 0.0,
            "face": None,
            "checks": {},
            "error": None,
        }

        # Step 1: Detect exactly one face
        face = self.detector.get_max_face(image)
        if face is None:
            result["error"] = "No face detected"
            logger.debug("register_no_face", extra={"user_id": user_id})
            return result

        result["face"] = face

        # Step 2: Validate quality (blur + face size only)
        quality = self.quality_checker.evaluate(image, face)
        result["checks"] = quality.get("checks", {})
        result["quality_score"] = quality["score"]

        if not quality["passed"]:
            reasons = "; ".join(quality.get("reasons", []))
            result["error"] = f"Quality check failed: {reasons}"
            logger.debug("register_quality_failed", extra={"user_id": user_id, "reasons": reasons})
            return result

        # Step 3: Align face
        aligned = self.aligner.align(image, face)

        # Step 4: Generate embedding
        embedding = self.embedder.generate(aligned)
        if np.all(embedding == 0):
            result["error"] = "Failed to generate face embedding"
            logger.debug("register_embedding_failed", extra={"user_id": user_id})
            return result

        result["embedding"] = embedding
        result["embedding_bytes"] = self.embedder.embedding_to_bytes(embedding)

        # Step 5: Save JPEG image
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"user_{user_id}_{pose}_{timestamp}.jpg"
        relative_path = f"uploads/{filename}"
        absolute_path = self.upload_dir / filename

        cv2.imwrite(str(absolute_path), image, [cv2.IMWRITE_JPEG_QUALITY, 92])
        result["image_path"] = str(relative_path)

        result["success"] = True
        logger.info(
            "face_registered",
            extra={
                "user_id": user_id,
                "pose": pose,
                "image_path": relative_path,
            },
        )

        return result

    def register_multi_pose(
        self,
        images: dict[str, np.ndarray],
        user_id: int,
        staff_number: str | None = None,
    ) -> dict[str, Any]:
        """Register multiple pose images for a user.

        Args:
            images: Dict of pose_name -> BGR image.
            user_id: Database user ID.
            staff_number: Employee staff number.

        Returns:
            Dict with per-pose results and aggregate status.
        """
        pose_results: dict[str, dict[str, Any]] = {}
        all_embeddings: list[np.ndarray] = []
        all_successful = True

        for pose, img in images.items():
            pose_result = self.register_face(
                image=img,
                user_id=user_id,
                pose=pose,
                staff_number=staff_number,
            )
            pose_results[pose] = pose_result
            if pose_result["success"] and pose_result["embedding"] is not None:
                all_embeddings.append(pose_result["embedding"])
            else:
                all_successful = False

        # Compute mean embedding from all successful captures
        mean_embedding = None
        if all_embeddings:
            mean_embedding = np.mean(all_embeddings, axis=0).astype(np.float32)
            norm = np.linalg.norm(mean_embedding)
            if norm > 0:
                mean_embedding = mean_embedding / norm

        return {
            "success": all_successful,
            "pose_results": pose_results,
            "mean_embedding": mean_embedding,
            "mean_embedding_bytes": self.embedder.embedding_to_bytes(mean_embedding) if mean_embedding is not None else None,
            "registered_poses": list(images.keys()),
            "error": None if all_successful else "One or more poses failed quality checks",
        }

    # ------------------------------------------------------------------
    # Login Pipeline
    # ------------------------------------------------------------------

    def login_face(
        self,
        image: np.ndarray,
        gallery: list[tuple[int, np.ndarray]],
    ) -> dict[str, Any]:
        """Authenticate a user by face.

        Simplified pipeline:
          1. Detect face (reject if none found)
          2. Minimal quality check (blur only)
          3. Align face
          4. Generate ArcFace embedding
          5. Match against gallery by cosine similarity
          6. Authenticate if similarity >= configurable threshold (default 0.70)

        No liveness check, no blink, no head movement, no spoof detection.

        Args:
            image: BGR image from camera.
            gallery: List of (user_id, embedding) tuples from Oracle.

        Returns:
            Dict with:
                - authenticated: bool
                - user_id: matched user ID (or None)
                - similarity: best similarity score
                - threshold: matching threshold used
                - face: detected face info
                - error: error message if failed
        """
        result: dict[str, Any] = {
            "authenticated": False,
            "user_id": None,
            "similarity": 0.0,
            "threshold": self.matcher.threshold,
            "face": None,
            "error": None,
        }

        # Step 1: Detect face
        face = self.detector.get_max_face(image)
        if face is None:
            result["error"] = "No face detected"
            return result

        result["face"] = face

        # Step 2: Minimal quality check (blur only)
        quality = self.quality_checker.evaluate(image, face)
        if not quality["passed"]:
            reasons = "; ".join(quality.get("reasons", []))
            result["error"] = f"Quality check failed: {reasons}"
            return result

        # Step 3: Align face
        aligned = self.aligner.align(image, face)

        # Step 4: Generate embedding
        embedding = self.embedder.generate(aligned)
        if np.all(embedding == 0):
            result["error"] = "Failed to generate face embedding"
            return result

        # Step 5: Match against gallery
        similarity, matched_id = self.matcher.match(embedding, gallery)
        result["similarity"] = round(similarity, 4)

        if matched_id is not None:
            result["authenticated"] = True
            result["user_id"] = matched_id
            logger.info(
                "face_login_success",
                extra={"user_id": matched_id, "similarity": round(similarity, 4)},
            )
        else:
            logger.debug(
                "face_login_no_match",
                extra={"best_similarity": round(similarity, 4), "threshold": self.matcher.threshold},
            )

        return result

    # ------------------------------------------------------------------
    # Utility methods
    # ------------------------------------------------------------------

    def load_face_image(self, image_path: str | Path) -> np.ndarray | None:
        """Load a face image from disk.

        Args:
            image_path: Path to JPEG image.

        Returns:
            BGR image or None on failure.
        """
        path = Path(image_path)
        if not path.is_absolute():
            path = settings.upload_dir.parent / image_path

        if not path.exists():
            logger.error("face_image_not_found", extra={"path": str(path)})
            return None

        image = cv2.imread(str(path))
        return image

    def build_gallery(
        self,
        face_samples: list[Any],
        embedder_util: Any = None,
    ) -> list[tuple[int, np.ndarray]]:
        """Build a matching gallery from database FaceSample records.

        Args:
            face_samples: List of FaceSample ORM objects with embedding_blob.
            embedder_util: FaceEmbedder instance (for bytes_to_embedding).

        Returns:
            List of (user_id, embedding) tuples.
        """
        embedder = embedder_util or self.embedder
        gallery: list[tuple[int, np.ndarray]] = []

        for sample in face_samples:
            if sample.embedding_blob:
                try:
                    embedding = embedder.bytes_to_embedding(sample.embedding_blob)
                    gallery.append((sample.user_id, embedding))
                except Exception as exc:
                    logger.warning(
                        "gallery_embedding_failed",
                        extra={"sample_id": sample.face_sample_id, "error": str(exc)},
                    )

        return gallery
