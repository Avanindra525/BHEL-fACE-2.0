"""Similarity-based face matching using cosine similarity.

Matches an input embedding against a gallery of known embeddings
using cosine similarity with configurable threshold.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from app.core.logging import logger
from app.face_ai.thresholds import SIMILARITY_THRESHOLD


class FaceMatcher:
    """Match input embeddings against a gallery of known embeddings.

    Attributes:
        threshold: Minimum cosine similarity for a match.
    """

    def __init__(self, threshold: float | None = None) -> None:
        self.threshold = threshold if threshold is not None else SIMILARITY_THRESHOLD

    def match(
        self,
        embedding: np.ndarray,
        candidates: list[tuple[int, np.ndarray]],
    ) -> tuple[float, int | None]:
        """Find the best matching candidate for the input embedding.

        Args:
            embedding: Query embedding vector (should be L2-normalized).
            candidates: List of (candidate_id, candidate_embedding) tuples.

        Returns:
            Tuple of (best_similarity, best_candidate_id).
            candidate_id is None if no match exceeds threshold.
        """
        if not candidates:
            logger.debug("face_matcher_no_candidates")
            return 0.0, None

        if np.linalg.norm(embedding) == 0:
            logger.debug("face_matcher_zero_embedding")
            return 0.0, None

        # Normalize query
        query_norm = embedding / np.linalg.norm(embedding)

        best_score = -1.0
        best_id = None

        for candidate_id, candidate_emb in candidates:
            if np.linalg.norm(candidate_emb) == 0:
                continue

            # Normalize candidate
            candidate_norm = candidate_emb / np.linalg.norm(candidate_emb)

            # Cosine similarity = dot product of normalized vectors
            similarity = float(np.dot(query_norm, candidate_norm))

            if similarity > best_score:
                best_score = similarity
                best_id = candidate_id if similarity >= self.threshold else None

        logger.debug(
            "face_matching_result",
            extra={
                "best_score": round(best_score, 4),
                "threshold": self.threshold,
                "matched": best_id is not None,
                "candidates_count": len(candidates),
            },
        )

        return best_score, best_id

    def match_all(
        self,
        embedding: np.ndarray,
        candidates: list[tuple[int, np.ndarray]],
    ) -> list[tuple[int, float]]:
        """Return similarity scores for all candidates, sorted by score descending.

        Args:
            embedding: Query embedding vector.
            candidates: List of (candidate_id, candidate_embedding) tuples.

        Returns:
            List of (candidate_id, similarity) sorted by similarity descending.
        """
        if not candidates:
            return []

        query_norm = embedding / np.linalg.norm(embedding) if np.linalg.norm(embedding) > 0 else embedding

        scores = []
        for candidate_id, candidate_emb in candidates:
            if np.linalg.norm(candidate_emb) > 0:
                candidate_norm = candidate_emb / np.linalg.norm(candidate_emb)
                sim = float(np.dot(query_norm, candidate_norm))
            else:
                sim = 0.0
            scores.append((candidate_id, sim))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores

    def verify_pair(self, embedding1: np.ndarray, embedding2: np.ndarray) -> dict[str, Any]:
        """Verify if two embeddings belong to the same person.

        Args:
            embedding1: First embedding vector.
            embedding2: Second embedding vector.

        Returns:
            Dict with similarity score and match decision.
        """
        norm1 = embedding1 / np.linalg.norm(embedding1) if np.linalg.norm(embedding1) > 0 else embedding1
        norm2 = embedding2 / np.linalg.norm(embedding2) if np.linalg.norm(embedding2) > 0 else embedding2

        similarity = float(np.dot(norm1, norm2))
        is_match = similarity >= self.threshold

        return {
            "similarity": round(similarity, 4),
            "threshold": self.threshold,
            "is_match": is_match,
        }

