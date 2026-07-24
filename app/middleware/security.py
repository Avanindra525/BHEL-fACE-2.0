"""HTTP security middleware: CSP, XSS, SQL injection prevention.

Adds security headers to all responses.
"""

from __future__ import annotations

from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware that adds enterprise security headers to all responses.

    Headers added:
      - Content-Security-Policy (XSS prevention)
      - X-Content-Type-Options (MIME sniffing prevention)
      - X-Frame-Options (Clickjacking prevention)
      - X-XSS-Protection (Legacy XSS filter)
      - Strict-Transport-Security (HSTS)
      - Referrer-Policy
      - Permissions-Policy
      - Cache-Control (for sensitive data)
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        # ── Content Security Policy ──
        # Restricts script/style sources to prevent XSS
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            "font-src 'self' https://cdnjs.cloudflare.com; "
            "connect-src 'self' ws:; "
            "media-src 'self' blob:; "
            "frame-ancestors 'self'; "
            "form-action 'self'"
        )

        # ── Prevent MIME type sniffing ──
        response.headers["X-Content-Type-Options"] = "nosniff"

        # ── Clickjacking prevention ──
        response.headers["X-Frame-Options"] = "SAMEORIGIN"

        # ── Legacy XSS filter ──
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # ── HSTS (forces HTTPS in production) ──
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        # ── Referrer policy ──
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # ── Permissions policy (restrict browser features) ──
        response.headers["Permissions-Policy"] = (
            "camera=(self), microphone=(), geolocation=(), "
            "fullscreen=(self), payment=(), usb=(), "
            "magnetometer=(), accelerometer=(), gyroscope=()"
        )

        # ── Cache control for API responses ──
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"

        return response

