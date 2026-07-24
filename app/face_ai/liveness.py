"""Liveness detection — simplified for academic demo.

All checks always pass. No blink detection, no texture analysis,
no motion detection, no anti-spoof heuristics.

This project is an academic demonstration, not a banking production system.
"""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np


class LivenessChecker:
    """No-op liveness checker — always reports face as live.

    All anti-spoof / blink / texture / motion checks are removed.
    The face recognition pipeline relies on InsightFace ArcFace similarity
    for authentication, not on behavioral challenge-response.
    """

    def __init__(self) -> None:
        pass

    def reset(self) -> None:
        """No-op — no state to reset."""
        pass

    def evaluate(self, image: np.ndarray, face: dict[str, Any] | None = None) -> dict[str, Any]:
        """Always pass — no liveness challenge.

        Args:
            image: BGR image frame (unused).
            face: Detected face dict (unused).

        Returns:
            Dict with passed=True, score=1.0.
        """
        return {
            "passed": True,
            "score": 1.0,
            "checks": {"liveness": {"passed": True, "reason": "liveness_bypassed_academic_demo"}},
            "reasons": [],
        }
