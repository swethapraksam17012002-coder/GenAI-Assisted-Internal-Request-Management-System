"""
NEXUS SDLC - Security Headers Middleware
Adds OWASP-recommended HTTP security headers to every response.
"""

import logging
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request

logger = logging.getLogger("nexus.security_headers")

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Inject strict HTTP security headers on every response."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # Prevent MIME-type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Clickjacking protection
        response.headers["X-Frame-Options"] = "DENY"

        # XSS protection (legacy browsers)
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Force HTTPS (enable in production behind TLS terminator)
        # response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"

        # Content Security Policy
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none';"
        )

        # Referrer policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Permissions policy (disable dangerous browser features)
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=()"
        )

        # Remove server fingerprinting
        if "Server" in response.headers:
            del response.headers["Server"]
        if "X-Powered-By" in response.headers:
            del response.headers["X-Powered-By"]

        # Cache control — never cache auth or sensitive endpoints
        if request.url.path.startswith("/api/auth") or request.url.path.startswith("/api/requests"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
            response.headers["Pragma"] = "no-cache"

        logger.debug("Security headers applied path=%s", request.url.path)
        return response
