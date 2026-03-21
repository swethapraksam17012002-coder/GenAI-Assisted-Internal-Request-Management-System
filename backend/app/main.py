"""NEXUS SDLC - FastAPI application entrypoint."""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api import agents, analytics, auth, dashboard, health, ingest, requests
from app.core.config import settings
from app.core.database import init_db
from app.core.logging_config import setup_logging
from app.middleware.rate_limiter import RateLimitMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware

setup_logging()
logger = logging.getLogger("nexus.app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    logger.info("Application startup complete")
    yield
    logger.info("Application shutdown complete")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    debug=settings.DEBUG,
    lifespan=lifespan,
)


@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    correlation_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.correlation_id = correlation_id
    start = time.perf_counter()
    logger.info(
        "Request started method=%s path=%s correlation_id=%s",
        request.method,
        request.url.path,
        correlation_id,
    )
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id
    duration_ms = int((time.perf_counter() - start) * 1000)
    logger.info(
        "Request completed method=%s path=%s status=%s duration_ms=%s correlation_id=%s",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
        correlation_id,
    )
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    correlation_id = getattr(request.state, "correlation_id", str(uuid.uuid4()))
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "data": None,
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred.",
                "correlation_id": correlation_id,
            },
        },
        headers={"X-Correlation-ID": correlation_id},
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset", "X-Correlation-ID"],
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.ALLOWED_HOSTS)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)


@app.get("/", tags=["System"])
async def root():
    return {
        "success": True,
        "data": {
            "name": settings.APP_NAME,
            "version": settings.VERSION,
            "docs": "/docs",
            "health": "/health",
        },
        "error": None,
    }


app.include_router(health.router)
app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(requests.router, prefix="/api/requests", tags=["Requests"])
app.include_router(agents.router, prefix="/api/agents", tags=["Agents"])
app.include_router(ingest.router, prefix="/api/ingest", tags=["Ingestion"])
app.include_router(dashboard.dashboard_router, prefix="/api/dashboard", tags=["Dashboard"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["Analytics"])
