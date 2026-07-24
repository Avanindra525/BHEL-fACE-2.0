"""Rate limiting middleware using in-memory store.

Tracks request counts per IP per endpoint and enforces limits.
Uses Oracle-style clean architecture — pluggable store.
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Callable

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.config import settings


class RateLimitStore:
    """In-memory rate limit store with sliding window."""

    def __init__(self) -> None:
        self._windows: dict[str, list[float]] = defaultdict(list)

    def _key(self, ip: str, path: str) -> str:
        return f"{ip}:{path}"

    def check(self, ip: str, path: str, max_requests: int, window_seconds: int = 60) -> bool:
        """Check if request is within rate limit. Returns True if allowed."""
        key = self._key(ip, path)
        now = time.time()
        cutoff = now - window_seconds

        # Prune expired entries
        self._windows[key] = [t for t in self._windows[key] if t > cutoff]

        if len(self._windows[key]) >= max_requests:
            return False

        self._windows[key].append(now)
        return True

    def get_remaining(self, ip: str, path: str, max_requests: int, window_seconds: int = 60) -> int:
        """Get remaining requests in current window."""
        key = self._key(ip, path)
        now = time.time()
        cutoff = now - window_seconds
        current = len([t for t in self._windows[key] if t > cutoff])
        return max(0, max_requests - current)


# Global store
_store = RateLimitStore()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware that enforces per-IP rate limits."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not settings.rate_limit_enabled:
            return await call_next(request)

        ip = request.client.host if request.client else "unknown"
        path = request.url.path

        # Determine limits based on path
        if path.startswith("/api/auth/login") or path.startswith("/api/face/login"):
            max_r = settings.rate_limit_login_requests_per_minute
        elif path.startswith("/api/face/"):
            max_r = settings.rate_limit_face_requests_per_minute
        else:
            max_r = settings.rate_limit_requests_per_minute

        allowed = _store.check(ip, path, max_r)
        remaining = _store.get_remaining(ip, path, max_r)

        if not allowed:
            return Response(
                content='{"detail": "Rate limit exceeded. Please try again later."}',
                status_code=429,
                media_type="application/json",
                headers={
                    "X-RateLimit-Limit": str(max_r),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time() + 60)),
                    "Retry-After": "60",
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(max_r)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response

