"""Minimal image quality validation for face capture pipeline.

Only rejects:
  - Extremely blurry images (Laplacian variance too low)
  - Face bounding box too small (< 80px)

All enterprise-grade checks (brightness, contrast, eye visibility,
head pose, etc.) are removed — this is an academic demo.
"""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np

from app.core.logging import logger


class QualityChecker:
    """Minimal quality validator for academic face registration.

    Attributes:
        min_blur_threshold: Minimum Laplacian variance (lower = more blur).
        min_face_size: Minimum face bounding box side in pixels.
    """

    def __init__(
        self,
        min_blur_threshold: float = 80.0,
        min_face_size: int = 80,
    ) -> None:
        self.min_blur_threshold = min_blur_threshold
        self.min_face_size = min_face_size

    def evaluate(self, image: np.ndarray, face: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run minimal quality checks on the image.

        Args:
            image: BGR image as numpy array.
            face: Face dict from detector (optional, for face size check).

        Returns:
            Dict with:
                - passed: bool
                - score: float (1.0 if passed, 0.0 if failed)
                - checks: dict of individual check results
                - reasons: list of failure reasons
        """
        checks = {}
        reasons = []

        # Check blur
        blur_result = self._check_blur(image)
        checks["blur"] = blur_result
        if not blur_result["passed"]:
            reasons.append(blur_result["reason"])

        # Check face size
        if face is not None:
            face_size_result = self._check_face_size(face)
            checks["face_size"] = face_size_result
            if not face_size_result["passed"]:
                reasons.append(face_size_result["reason"])

        passed = len(reasons) == 0
        score = 1.0 if passed else 0.0

        if not passed:
            logger.debug("quality_check_failed", extra={"reasons": reasons})

        return {
            "passed": passed,
            "score": score,
            "checks": checks,
            "reasons": reasons,
        }

    def _check_blur(self, image: np.ndarray) -> dict[str, Any]:
        """Detect extreme blur using Laplacian variance."""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        passed = laplacian_var >= self.min_blur_threshold
        return {
            "passed": passed,
            "value": float(round(laplacian_var, 2)),
            "threshold": self.min_blur_threshold,
            "reason": f"Image too blurry ({laplacian_var:.1f}, min: {self.min_blur_threshold})" if not passed else None,
        }

    def _check_face_size(self, face: dict[str, Any]) -> dict[str, Any]:
        """Validate that face bounding box is above minimum."""
        bbox = face.get("bbox", [0, 0, 0, 0])
        face_w = bbox[2] - bbox[0]
        face_h = bbox[3] - bbox[1]
        min_dim = min(face_w, face_h)
        passed = min_dim >= self.min_face_size
        return {
            "passed": passed,
            "value": min_dim,
            "threshold": self.min_face_size,
            "reason": f"Face too small ({min_dim}px, min: {self.min_face_size}px)" if not passed else None,
        }
