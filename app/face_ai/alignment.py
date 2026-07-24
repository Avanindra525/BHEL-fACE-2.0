"""Facial alignment using similarity transform on 5-point landmarks.

Aligns the face to a canonical position (eyes horizontal, face centered)
using affine transformation based on the 5 facial landmarks:
  - Left eye center
  - Right eye center  
  - Nose tip
  - Left mouth corner
  - Right mouth corner
"""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np

from app.core.logging import logger


class FaceAligner:
    """Align faces to a canonical position using landmark-based similarity transform.

    Attributes:
        desired_size: Output image size in pixels.
        desired_distance: Desired inter-eye distance in output image.
    """

    # Canonical landmark positions for a 112x112 aligned face
    CANONICAL_LANDMARKS = np.array([
        [38.2946, 51.6963],   # Left eye
        [73.5318, 51.5014],   # Right eye
        [56.0252, 71.7366],   # Nose
        [41.5493, 92.3655],   # Left mouth
        [70.7299, 92.2041],   # Right mouth
    ], dtype=np.float64)

    def __init__(self, desired_size: int = 112) -> None:
        self.desired_size = desired_size
        # Scale canonical landmarks to desired size
        scale = desired_size / 112.0
        self.canonical = self.CANONICAL_LANDMARKS * scale

    def align(self, image: np.ndarray, face: dict[str, Any]) -> np.ndarray:
        """Align a face in the image using 5-point landmarks.

        Args:
            image: BGR image as numpy array.
            face: Face dict from detector containing 'kps' (5x2 landmarks).

        Returns:
            Aligned face image as numpy array of shape (desired_size, desired_size, 3).

        Raises:
            ValueError: If landmarks are missing or invalid.
        """
        kps = face.get("kps")
        if kps is None:
            # Fall back to cropping from bounding box
            return self._crop_from_bbox(image, face)

        src_pts = np.array(kps, dtype=np.float64)
        if src_pts.shape != (5, 2):
            logger.debug("invalid_landmarks_shape", extra={"shape": src_pts.shape})
            return self._crop_from_bbox(image, face)

        # Compute similarity transform and warp
        tform = cv2.estimateAffinePartial2D(src_pts, self.canonical, method=cv2.LMEDS)

        if tform[0] is None:
            logger.debug("alignment_transform_failed")
            return self._crop_from_bbox(image, face)

        aligned = cv2.warpAffine(
            image,
            tform[0],
            (self.desired_size, self.desired_size),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REFLECT,
        )

        return aligned

    def _crop_from_bbox(self, image: np.ndarray, face: dict[str, Any]) -> np.ndarray:
        """Fallback: center-crop the face from bounding box."""
        bbox = face.get("bbox", [0, 0, image.shape[1], image.shape[0]])
        x1, y1, x2, y2 = bbox

        # Expand box slightly
        margin = int((x2 - x1) * 0.2)
        x1 = max(0, x1 - margin)
        y1 = max(0, y1 - margin)
        x2 = min(image.shape[1], x2 + margin)
        y2 = min(image.shape[0], y2 + margin)

        cropped = image[y1:y2, x1:x2]
        if cropped.size == 0:
            return np.zeros((self.desired_size, self.desired_size, 3), dtype=np.uint8)

        # Resize to desired size
        aligned = cv2.resize(cropped, (self.desired_size, self.desired_size), interpolation=cv2.INTER_CUBIC)
        return aligned

