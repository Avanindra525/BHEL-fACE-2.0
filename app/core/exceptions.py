"""Domain specific exceptions."""

from __future__ import annotations


class FaceAuthError(Exception):
    """Base class for FaceAuth Enterprise exceptions."""


class AuthenticationError(FaceAuthError):
    """Raised when authentication fails."""


class AuthorizationError(FaceAuthError):
    """Raised when the current user lacks permissions."""


class NotFoundError(FaceAuthError):
    """Raised when a requested resource is missing."""


class ConflictError(FaceAuthError):
    """Raised when a uniqueness or state conflict occurs."""


class ValidationError(FaceAuthError):
    """Raised when business validation fails."""
