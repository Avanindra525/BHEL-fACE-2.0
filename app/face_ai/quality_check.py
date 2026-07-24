"""Image quality validation for face capture pipeline.

Validates:
  - Blur detection (Laplacian variance)
  - Brightness check
  - Contrast check
  - Face size validation
  - Eye visibility validation
"""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np

from app.core.logging import logger


class QualityChecker:
    """Validates image quality before accepting a face sample.

    Attributes:
        min_blur_threshold: Minimum Laplacian variance (lower = more blur).
        min_brightness: Minimum mean pixel brightness (0-255).
        max_brightness: Maximum mean pixel brightness (0-255).
        min_contrast: Minimum contrast (std deviation).
        min_face_size: Minimum face bounding box side in pixels.
        min_eye_distance: Minimum distance between eyes in pixels.
    """

    def __init__(
        self,
        min_blur_threshold: float = 80.0,
        min_brightness: float = 60.0,
        max_brightness: float = 230.0,
        min_contrast: float = 30.0,
        min_face_size: int = 120,
        min_eye_distance: float = 30.0,
    ) -> None:
        self.min_blur_threshold = min_blur_threshold
        self.min_brightness = min_brightness
        self.max_brightness = max_brightness
        self.min_contrast = min_contrast
        self.min_face_size = min_face_size
        self.min_eye_distance = min_eye_distance

    def evaluate(self, image: np.ndarray, face: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run all quality checks on the image.

        Args:
            image: BGR image as numpy array.
            face: Face dict from detector (optional, for face-specific checks).

        Returns:
            Dict with:
                - passed: bool
                - score: float (0.0 - 1.0)
                - checks: dict of individual check results
                - reasons: list of failure reasons
        """
        checks = {}
        reasons = []

        # Run all checks
        blur_result = self._check_blur(image)
        checks["blur"] = blur_result
        if not blur_result["passed"]:
            reasons.append(blur_result["reason"])

        brightness_result = self._check_brightness(image)
        checks["brightness"] = brightness_result
        if not brightness_result["passed"]:
            reasons.append(brightness_result["reason"])

        contrast_result = self._check_contrast(image)
        checks["contrast"] = contrast_result
        if not contrast_result["passed"]:
            reasons.append(contrast_result["reason"])

        if face is not None:
            face_size_result = self._check_face_size(face)
            checks["face_size"] = face_size_result
            if not face_size_result["passed"]:
                reasons.append(face_size_result["reason"])

            if face.get("kps"):
                eye_result = self._check_eye_visibility(face)
                checks["eye_visibility"] = eye_result
                if not eye_result["passed"]:
                    reasons.append(eye_result["reason"])

        # Compute overall score
        total_checks = len(checks)
        passed_checks = sum(1 for c in checks.values() if c["passed"])
        score = passed_checks / total_checks if total_checks > 0 else 0.0

        passed = len(reasons) == 0
        if not passed:
            logger.debug("quality_check_failed", extra={"reasons": reasons, "score": score})

        return {
            "passed": passed,
            "score": round(score, 3),
            "checks": checks,
            "reasons": reasons,
        }

    def _check_blur(self, image: np.ndarray) -> dict[str, Any]:
        """Detect blur using Laplacian variance.

        Low variance = blurry image.
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        passed = laplacian_var >= self.min_blur_threshold
        return {
            "passed": passed,
            "value": float(round(laplacian_var, 2)),
            "threshold": self.min_blur_threshold,
            "reason": f"Image is blurry (sharpness: {laplacian_var:.1f}, min: {self.min_blur_threshold})" if not passed else None,
        }

    def _check_brightness(self, image: np.ndarray) -> dict[str, Any]:
        """Check if image brightness is within acceptable range."""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        mean_brightness = float(np.mean(gray))
        passed = self.min_brightness <= mean_brightness <= self.max_brightness
        reason = None
        if mean_brightness < self.min_brightness:
            reason = f"Image too dark (brightness: {mean_brightness:.1f}, min: {self.min_brightness})"
        elif mean_brightness > self.max_brightness:
            reason = f"Image too bright (brightness: {mean_brightness:.1f}, max: {self.max_brightness})"
        return {
            "passed": passed,
            "value": round(mean_brightness, 1),
            "threshold_min": self.min_brightness,
            "threshold_max": self.max_brightness,
            "reason": reason,
        }

    def _check_contrast(self, image: np.ndarray) -> dict[str, Any]:
        """Check if image has sufficient contrast."""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        std = float(np.std(gray))
        passed = std >= self.min_contrast
        return {
            "passed": passed,
            "value": round(std, 2),
            "threshold": self.min_contrast,
            "reason": f"Image lacks contrast (contrast: {std:.1f}, min: {self.min_contrast})" if not passed else None,
        }

    def _check_face_size(self, face: dict[str, Any]) -> dict[str, Any]:
        """Validate that face is large enough in the frame."""
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

    def _check_eye_visibility(self, face: dict[str, Any]) -> dict[str, Any]:
        """Check that eyes are visible and sufficiently separated."""
        kps = np.array(face.get("kps", []), dtype=np.int32)
        if kps.shape != (5, 2):
            return {"passed": True, "reason": "landmarks_unavailable"}

        # kps indices: 0=left_eye, 1=right_eye, 2=nose, 3=mouth_left, 4=mouth_right
        left_eye = kps[0]
        right_eye = kps[1]

        eye_distance = float(np.linalg.norm(left_eye - right_eye))
        passed = eye_distance >= self.min_eye_distance
        return {
            "passed": passed,
            "eye_distance": round(eye_distance, 1),
            "threshold": self.min_eye_distance,
            "reason": f"Eyes too close together ({eye_distance:.0f}px, min: {self.min_eye_distance}px)" if not passed else None,
        }

