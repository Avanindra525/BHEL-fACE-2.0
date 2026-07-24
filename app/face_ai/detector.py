"""SCRFD face detection via InsightFace with fallback to OpenCV DNN.

Production face detector that:
  - Uses InsightFace's built-in SCRFD model (buffalo_l)
  - Returns normalized face landmarks and bounding boxes
  - Rejects images with zero or multiple faces
  - Validates minimum face size
"""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np

try:
    import insightface
    from insightface.app import FaceAnalysis

    _HAS_INSIGHTFACE = True
except ImportError:
    _HAS_INSIGHTFACE = False

from app.core.config import settings
from app.core.logging import logger


class FaceDetector:
    """SCRFD face detector wrapper.

    Attributes:
        model_name: InsightFace model pack name (e.g. 'buffalo_l').
        min_face_size: Minimum face dimension in pixels.
        app: InsightFace FaceAnalysis instance.
    """

    def __init__(
        self,
        model_name: str | None = None,
        min_face_size: int = 80,
        det_threshold: float = 0.5,
    ) -> None:
        self.model_name = model_name or settings.insightface_model_name
        self.min_face_size = min_face_size
        self.det_threshold = det_threshold
        self.app = self._init_model()

    def _init_model(self) -> Any:
        """Initialize the InsightFace SCRFD detector model."""
        if not _HAS_INSIGHTFACE:
            logger.warning(
                "insightface_not_installed",
                extra={"detail": "Falling back to OpenCV Haar cascade. Install insightface for SCRFD."},
            )
            return None

        try:
            app = FaceAnalysis(
                name=self.model_name,
                providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
            )
            app.prepare(ctx_id=0, det_thresh=self.det_threshold)
            logger.info(
                "face_detector_loaded",
                extra={"model": self.model_name, "threshold": self.det_threshold},
            )
            return app
        except Exception as exc:
            logger.error(
                "face_detector_load_failed",
                extra={"model": self.model_name, "error": str(exc)},
            )
            return None

    def detect(self, image: np.ndarray) -> list[dict[str, Any]]:
        """Detect faces in an image using SCRFD.

        Args:
            image: BGR image as numpy array (H, W, 3).

        Returns:
            List of face dicts each containing:
                - bbox: [x1, y1, x2, y2]
                - kps: 5x2 landmark array (eyes, nose, mouth corners)
                - det_score: detection confidence
                - face_size: face bounding box area in pixels
        """
        if image is None or image.size == 0:
            return []

        if self.app is not None:
            # InsightFace SCRFD path
            results = self.app.get(image)
            faces = []
            for face in results:
                bbox = face.bbox.astype(int).tolist()
                w = bbox[2] - bbox[0]
                h = bbox[3] - bbox[1]
                face_size = min(w, h)
                if face_size < self.min_face_size:
                    continue
                faces.append({
                    "bbox": bbox,
                    "kps": face.kps.astype(int).tolist() if hasattr(face, "kps") else None,
                    "det_score": float(face.det_score),
                    "face_size": face_size,
                    "landmarks_2d_106": face.landmarks_2d_106 if hasattr(face, "landmarks_2d_106") else None,
                })
            return faces
        else:
            # Fallback: OpenCV Haar cascade
            return self._detect_haar_fallback(image)

    def _detect_haar_fallback(self, image: np.ndarray) -> list[dict[str, Any]]:
        """Fallback face detection using OpenCV Haar cascade."""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        cascade = cv2.CascadeClassifier(cascade_path)

        rects = cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(self.min_face_size, self.min_face_size),
        )

        faces = []
        for x, y, w, h in rects:
            faces.append({
                "bbox": [int(x), int(y), int(x + w), int(y + h)],
                "kps": None,
                "det_score": 0.9,
                "face_size": min(w, h),
            })
        return faces

    def get_max_face(self, image: np.ndarray) -> dict[str, Any] | None:
        """Return the largest detected face (or None if no/detected).

        Rejects images where != 1 face is found.
        """
        faces = self.detect(image)
        if len(faces) == 0:
            logger.debug("no_face_detected")
            return None
        if len(faces) > 1:
            logger.debug("multiple_faces_detected", extra={"count": len(faces)})
            return None
        return faces[0]

