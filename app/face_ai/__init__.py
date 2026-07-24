"""Face AI package for FaceAuth Enterprise.

Production pipeline:
    detector (SCRFD) → aligner → quality_checker → liveness_checker → embedder (ArcFace) → matcher
"""

