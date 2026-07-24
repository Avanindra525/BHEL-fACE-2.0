"""ArcFace embedding generation via InsightFace.

Generates 512-dimensional face embeddings using InsightFace's ArcFace model.
Supports both GPU (CUDA) and CPU inference.
"""

from __future__ import annotations

import pickle
from typing import Any

import cv2
import numpy as np

try:
    import insightface
    from insightface.model_zoo import model_zoo

    _HAS_INSIGHTFACE = True
except ImportError:
    _HAS_INSIGHTFACE = False

from app.core.config import settings
from app.core.logging import logger
from app.face_ai.thresholds import EMBEDDING_DIMENSION


class FaceEmbedder:
    """ArcFace embedding generator.

    Attributes:
        model_name: InsightFace model pack name.
        model: InsightFace ArcFace model instance.
        input_size: Model input image size.
    """

    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name or settings.insightface_model_name
        self.input_size = (112, 112)
        self.model = self._init_model()

    def _init_model(self) -> Any:
        """Initialize the InsightFace ArcFace model."""
        if not _HAS_INSIGHTFACE:
            logger.warning(
                "insightface_not_installed",
                extra={"detail": "Using OpenCV fallback for embeddings. Install insightface for ArcFace."},
            )
            return None

        try:
            # Load the ArcFace model from the InsightFace model zoo
            model_path = f"models/{self.model_name}/w600k_r50.onnx"
            model = model_zoo.get_model(model_path, download=True, download_zip=True)
            logger.info(
                "arcface_model_loaded",
                extra={"model": self.model_name, "embedding_dim": EMBEDDING_DIMENSION},
            )
            return model
        except Exception as exc:
            logger.error(
                "arcface_model_load_failed",
                extra={"model": self.model_name, "error": str(exc)},
            )
            return None

    def generate(self, image: np.ndarray) -> np.ndarray:
        """Generate a 512-dimensional face embedding from an aligned face image.

        Args:
            image: Aligned face image (112x112 RGB or BGR).

        Returns:
            512-dimensional float32 numpy array normalized to unit length.
        """
        if image is None or image.size == 0:
            return np.zeros(EMBEDDING_DIMENSION, dtype=np.float32)

        if self.model is not None:
            return self._generate_insightface(image)
        else:
            return self._generate_fallback(image)

    def _generate_insightface(self, image: np.ndarray) -> np.ndarray:
        """Generate embedding using InsightFace ArcFace model."""
        # Ensure correct size
        if image.shape[:2] != self.input_size:
            image = cv2.resize(image, self.input_size, interpolation=cv2.INTER_LINEAR)

        # Ensure RGB
        if image.shape[2] == 3:
            img_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        else:
            img_rgb = image

        # Normalize to [0, 1]
        img_rgb = img_rgb.astype(np.float32) / 255.0

        # Run inference
        embedding = self.model.get_embedding(img_rgb)
        if embedding is None or len(embedding) == 0:
            return np.zeros(EMBEDDING_DIMENSION, dtype=np.float32)

        embedding = np.array(embedding, dtype=np.float32).flatten()

        # L2-normalize
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm

        return embedding

    def _generate_fallback(self, image: np.ndarray) -> np.ndarray:
        """Fallback: generate a deterministic pseudo-embedding from image features.

        This uses HOG + color histogram features as a placeholder when
        InsightFace is not available.
        """
        # Resize to standard size
        img = cv2.resize(image, self.input_size, interpolation=cv2.INTER_LINEAR)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Compute HOG-like features
        gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
        mag, ang = cv2.cartToPolar(gx, gy)

        # Binned orientation histogram
        bins = 64
        hist_bins = np.linspace(0, 360, bins + 1)
        hog_features = []
        for y in range(0, 112, 14):
            for x in range(0, 112, 14):
                cell_mag = mag[y : y + 14, x : x + 14].flatten()
                cell_ang = ang[y : y + 14, x : x + 14].flatten()
                hist, _ = np.histogram(cell_ang, bins=hist_bins, weights=cell_mag)
                hog_features.extend(hist)

        # Color histogram features
        color_feats = []
        for channel in range(3):
            hist = cv2.calcHist([img], [channel], None, [32], [0, 256])
            color_feats.extend(hist.flatten())

        all_features = np.array(hog_features[:400] + color_feats[:112], dtype=np.float32)
        embedding = np.zeros(EMBEDDING_DIMENSION, dtype=np.float32)
        embedding[: min(len(all_features), EMBEDDING_DIMENSION)] = all_features[:EMBEDDING_DIMENSION]

        # Normalize
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm

        return embedding

    def embedding_to_bytes(self, embedding: np.ndarray) -> bytes:
        """Serialize embedding to bytes for Oracle BLOB storage."""
        return pickle.dumps(embedding)

    def bytes_to_embedding(self, data: bytes) -> np.ndarray:
        """Deserialize embedding from Oracle BLOB bytes."""
        return pickle.loads(data)

