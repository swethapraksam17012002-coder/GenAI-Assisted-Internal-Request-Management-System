"""
NEXUS SDLC - Rate Limiting Middleware
Token-bucket algorithm per IP; stricter limits on auth endpoints.
Headers: X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset
"""

import logging
import time
import asyncio
from collections import defaultdict
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.config import settings

logger = logging.getLogger("nexus.rate_limiter")

class _Bucket:
    """Simple sliding-window token bucket."""
    def __init__(self, capacity: int, refill_rate: float):
        self.capacity = capacity
        self.tokens = float(capacity)
        self.refill_rate = refill_rate   # tokens / second
        self.last_refill = time.monotonic()

    def consume(self) -> bool:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False

    @property
    def reset_after(self) -> int:
        """Seconds until at least 1 token is available."""
        if self.tokens >= 1:
            return 0
        return int((1 - self.tokens) / self.refill_rate) + 1


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Per-IP rate limiter.
    Auth endpoints: 10 req/min  (configurable via settings.RATE_LIMIT_AUTH_PER_MINUTE)
    All other endpoints: 100 req/min (configurable via settings.RATE_LIMIT_PER_MINUTE)
    """

    AUTH_PATHS = {"/api/auth/token", "/api/auth/register", "/api/auth/refresh"}

    def __init__(self, app):
        super().__init__(app)
        self._buckets: dict[str, _Bucket] = defaultdict()
        self._lock = asyncio.Lock()

    def _get_client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _bucket_key(self, ip: str, path: str) -> str:
        prefix = "auth" if path in self.AUTH_PATHS else "api"
        return f"{prefix}:{ip}"

    def _get_or_create_bucket(self, key: str, is_auth: bool) -> _Bucket:
        if key not in self._buckets:
            if is_auth:
                cap = settings.RATE_LIMIT_AUTH_PER_MINUTE
            else:
                cap = settings.RATE_LIMIT_PER_MINUTE
            # refill rate = tokens per second
            self._buckets[key] = _Bucket(capacity=cap, refill_rate=cap / 60.0)
        return self._buckets[key]

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health check and docs
        if request.url.path in {"/", "/health", "/docs", "/redoc", "/openapi.json"}:
            return await call_next(request)

        ip = self._get_client_ip(request)
        path = request.url.path
        is_auth = path in self.AUTH_PATHS
        key = self._bucket_key(ip, path)

        async with self._lock:
            bucket = self._get_or_create_bucket(key, is_auth)
            allowed = bucket.consume()
            remaining = int(bucket.tokens)
            reset_after = bucket.reset_after
            limit = bucket.capacity

        if not allowed:
            logger.warning("Rate limit exceeded ip=%s path=%s limit=%s", ip, path, limit)
            return JSONResponse(
                status_code=429,
                content={
                    "success": False,
                    "data": None,
                    "error": {
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": f"Too many requests. Retry after {reset_after} seconds.",
                        "retry_after": reset_after,
                    },
                },
                headers={
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time()) + reset_after),
                    "Retry-After": str(reset_after),
                },
            )

        response: Response = await call_next(request)
        logger.debug("Rate limit check passed ip=%s path=%s remaining=%s", ip, path, remaining)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int(time.time()) + reset_after)
        return response
