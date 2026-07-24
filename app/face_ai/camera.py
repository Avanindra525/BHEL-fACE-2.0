"""Webcam capture module for face registration and login.

Provides automatic face capture with:
  - Camera device discovery
  - 3-2-1 countdown capture
  - Multi-pose capture (Front, Left, Right, Up)
  - Frame streaming utility
  - Automatic single-face framing
"""

from __future__ import annotations

import time
from typing import Any, Generator

import cv2
import numpy as np

from app.core.logging import logger


class CameraCapture:
    """Webcam capture manager with automatic face detection triggers.

    Attributes:
        camera_id: OpenCV camera device index.
        width: Capture frame width.
        height: Capture frame height.
        cap: OpenCV VideoCapture instance.
    """

    def __init__(
        self,
        camera_id: int = 0,
        width: int = 640,
        height: int = 480,
    ) -> None:
        self.camera_id = camera_id
        self.width = width
        self.height = height
        self.cap: cv2.VideoCapture | None = None

    def open(self) -> bool:
        """Open the camera device.

        Returns:
            True if camera opened successfully.
        """
        try:
            self.cap = cv2.VideoCapture(self.camera_id, cv2.CAP_DSHOW)
            if not self.cap.isOpened():
                self.cap = cv2.VideoCapture(self.camera_id)
            if not self.cap.isOpened():
                logger.error("camera_open_failed", extra={"camera_id": self.camera_id})
                return False

            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            self.cap.set(cv2.CAP_PROP_FPS, 30)

            logger.info("camera_opened", extra={"camera_id": self.camera_id})
            return True
        except Exception as exc:
            logger.error("camera_error", extra={"error": str(exc)})
            return False

    def close(self) -> None:
        """Release the camera device."""
        if self.cap is not None:
            self.cap.release()
            self.cap = None
            logger.debug("camera_closed")

    def read_frame(self) -> np.ndarray | None:
        """Read a single frame from the camera.

        Returns:
            BGR frame as numpy array, or None if failed.
        """
        if self.cap is None or not self.cap.isOpened():
            return None
        success, frame = self.cap.read()
        return frame if success else None

    def stream_frames(self) -> Generator[np.ndarray, None, None]:
        """Yield frames from the camera indefinitely.

        Yields:
            BGR frame as numpy array.
        """
        if not self.open():
            return

        try:
            while True:
                frame = self.read_frame()
                if frame is None:
                    break
                yield frame
        finally:
            self.close()

    def capture_with_countdown(self, seconds: int = 3) -> np.ndarray | None:
        """Capture a single frame after a countdown.

        Args:
            seconds: Countdown duration in seconds.

        Returns:
            Captured frame or None if failed.
        """
        if not self.open():
            return None

        try:
            # Wait for countdown, reading frames to keep camera active
            start = time.time()
            last_frame = None
            while time.time() - start < seconds:
                frame = self.read_frame()
                if frame is not None:
                    last_frame = frame.copy()
                time.sleep(0.03)  # ~30fps read rate

            return last_frame
        finally:
            self.close()

    def capture_pose_sequence(
        self,
        poses: list[str] | None = None,
        countdown_per_pose: int = 3,
    ) -> dict[str, np.ndarray]:
        """Capture a sequence of pose images.

        Args:
            poses: List of pose names (e.g. ['front', 'left', 'right', 'up']).
            countdown_per_pose: Seconds to wait before each capture.

        Returns:
            Dict mapping pose name -> captured frame.
        """
        if poses is None:
            poses = ["front", "left", "right", "up"]

        results: dict[str, np.ndarray] = {}
        if not self.open():
            return results

        try:
            for pose in poses:
                logger.info("capturing_pose", extra={"pose": pose})
                frame = self.capture_with_countdown(countdown_per_pose)
                if frame is not None:
                    results[pose] = frame
                time.sleep(0.5)  # Brief pause between poses
            return results
        finally:
            self.close()

    def detect_and_crop_face(
        self,
        frame: np.ndarray,
        detector: Any,
    ) -> tuple[np.ndarray | None, dict[str, Any] | None]:
        """Detect the largest face in frame and return cropped region.

        Args:
            frame: BGR frame.
            detector: FaceDetector instance.

        Returns:
            Tuple of (cropped_face_image, face_dict) or (None, None).
        """
        face = detector.get_max_face(frame)
        if face is None:
            return None, None

        bbox = face["bbox"]
        x1, y1, x2, y2 = bbox
        # Add margin
        margin = int((x2 - x1) * 0.3)
        h_img, w_img = frame.shape[:2]
        x1 = max(0, x1 - margin)
        y1 = max(0, y1 - margin)
        x2 = min(w_img, x2 + margin)
        y2 = min(h_img, y2 + margin)

        cropped = frame[y1:y2, x1:x2]
        return cropped, face

    @staticmethod
    def list_cameras() -> list[int]:
        """Detect available camera devices.

        Returns:
            List of available camera indices.
        """
        available = []
        for i in range(5):  # Check first 5 indices
            try:
                cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
                if cap.isOpened():
                    available.append(i)
                    cap.release()
            except Exception:
                pass
        return available

    def __enter__(self) -> CameraCapture:
        self.open()
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

