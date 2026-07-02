"""
Biashara Intelligence — FastAPI Application

Main entry point for the cloud backend. Sets up:
- CORS middleware
- Rate limiting
- Exception handlers
- API router with versioning (/api/v1/)
- Health check endpoint
- Database lifecycle events
"""

import logging
import time
import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import get_settings
from app.db.database import close_db, init_db
from app.services.cache import get_cache
from app.services.task_queue import get_task_queue

settings = get_settings()

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.dev.ConsoleRenderer() if settings.DEBUG else structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)

# Rate limiter — use Redis if available, else in-memory
_rate_storage = settings.REDIS_URL if settings.REDIS_URL else "memory://"
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[f"{settings.RATE_LIMIT_PER_MINUTE}/minute"],
    storage_uri=_rate_storage,
)


# =========================================================================
# Lifespan Events
# =========================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifecycle management.

    Startup: Initialize database, Redis cache, and task queue
    Shutdown: Close all connections gracefully
    """
    # Startup
    logger.info(
        "application_starting",
        app_name=settings.APP_NAME,
        env=settings.APP_ENV,
        debug=settings.DEBUG,
    )
    await init_db()
    logger.info("database_initialized")

    # Initialize Redis cache (Tier 2)
    cache = get_cache()
    await cache.connect()
    logger.info("cache_initialized", available=cache.is_available)

    # Initialize task queue (Tier 2)
    task_queue = get_task_queue()
    await task_queue.connect()
    logger.info("task_queue_initialized")

    yield

    # Shutdown
    logger.info("application_shutting_down")
    await task_queue.close()
    logger.info("task_queue_closed")
    await cache.close()
    logger.info("cache_closed")
    await close_db()
    logger.info("database_connections_closed")


# =========================================================================
# Application Instance
# =========================================================================


app = FastAPI(
    title="Biashara Intelligence",
    description=(
        "Intelligence platform for Kenya's informal economy. "
        "Transforms raw transaction data from dukawallahs and mama mbogas "
        "into actionable economic intelligence."
    ),
    version="0.1.0",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
    lifespan=lifespan,
)


# =========================================================================
# Middleware
# =========================================================================

# CORS — default to localhost origins if none configured
_cors_origins = settings.CORS_ORIGINS if settings.CORS_ORIGINS else ["http://localhost:3000", "http://localhost:8080"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID", "X-Device-ID", "X-OpenWA-Signature"],
    expose_headers=["X-Request-ID", "X-RateLimit-Remaining"],
)

# Trusted host middleware (prevents Host header attacks)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=_cors_origins if settings.is_production else ["*"],
)

# Rate limiting
app.state.limiter = limiter


# Request ID middleware
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """Add unique request ID to every request for tracing."""
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id

    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time

    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time"] = f"{process_time:.4f}"

    logger.info(
        "request_completed",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        process_time=round(process_time, 4),
        request_id=request_id,
    )

    return response


# =========================================================================
# Exception Handlers
# =========================================================================


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    """Handle rate limit exceeded errors."""
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={
            "error": "rate_limit_exceeded",
            "message": "Too many requests. Please try again later.",
            "retry_after": 60,
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions with consistent format."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "http_error",
            "status_code": exc.status_code,
            "message": exc.detail,
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions — log and return 500."""
    logger.error(
        "unhandled_exception",
        error=str(exc),
        path=request.url.path,
        method=request.method,
        exc_info=True,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "internal_server_error",
            "message": "An unexpected error occurred. Please try again later.",
            "request_id": getattr(request.state, "request_id", None),
        },
    )


# =========================================================================
# Health Check
# =========================================================================


@app.get("/health", tags=["Health"])
async def health_check():
    """
    Health check endpoint.

    Returns application status including cache and task queue health.
    Used by Docker health checks, load balancers, and monitoring.
    """
    cache = get_cache()
    components = {
        "database": "ok",
        "cache": "ok" if cache.is_available else "unavailable",
        "task_queue": "ok" if get_task_queue()._connected else "unavailable",
    }
    overall = "ok" if all(v == "ok" for v in components.values()) else "degraded"

    return {
        "status": overall,
        "service": "biashara-intelligence-backend",
        "version": "0.2.0",
        "environment": settings.APP_ENV,
        "components": components,
        "tier": "2-growth",
    }


@app.get("/", tags=["Root"])
async def root():
    """Root endpoint — redirects to docs in development."""
    return {
        "service": "Biashara Intelligence Backend",
        "version": "0.1.0",
        "docs": "/docs" if settings.DEBUG else None,
        "health": "/health",
    }


# =========================================================================
# API Routers
# =========================================================================

from app.api.auth import router as auth_router
from app.api.sync import router as sync_router
from app.api.reports import router as reports_router
from app.api.intelligence import router as intelligence_router
from app.api.intelligence_products import router as intelligence_products_router
from app.api.whatsapp import router as whatsapp_router
from app.api.federated_learning import router as fl_router
from app.api.analysis import router as analysis_router

# Phase 1 routers
from app.api.onboarding import router as onboarding_router
from app.api.dashboard import router as dashboard_router
from app.api.phase1_intelligence import router as phase1_router

# Formal reports (bank, government, insurance)
from app.api.formal_reports import router as formal_reports_router

# FMCG intelligence (Pwani Oil, Unilever, Bidco)
from app.api.fmcg import router as fmcg_router

# Mount all API routers under versioned prefix
app.include_router(auth_router, prefix=settings.API_V1_PREFIX)
app.include_router(sync_router, prefix=settings.API_V1_PREFIX)
app.include_router(reports_router, prefix=settings.API_V1_PREFIX)
app.include_router(intelligence_router, prefix=settings.API_V1_PREFIX)
app.include_router(intelligence_products_router, prefix=settings.API_V1_PREFIX)
app.include_router(whatsapp_router, prefix=settings.API_V1_PREFIX)
app.include_router(fl_router, prefix=settings.API_V1_PREFIX)
app.include_router(analysis_router, prefix=settings.API_V1_PREFIX)
app.include_router(onboarding_router, prefix=settings.API_V1_PREFIX)
app.include_router(dashboard_router, prefix=settings.API_V1_PREFIX)
app.include_router(phase1_router, prefix=settings.API_V1_PREFIX)
app.include_router(formal_reports_router, prefix=settings.API_V1_PREFIX)
app.include_router(fmcg_router, prefix=settings.API_V1_PREFIX)


# =========================================================================
# Startup Banner
# =========================================================================


@app.on_event("startup")
async def startup_banner():
    """Print startup banner for visibility."""
    logger.info("=" * 60)
    logger.info("🇰🇪 Biashara Intelligence — Backend Starting")
    logger.info(f"   Environment: {settings.APP_ENV}")
    logger.info(f"   API Prefix:  {settings.API_V1_PREFIX}")
    logger.info(f"   Debug:       {settings.DEBUG}")
    logger.info("=" * 60)
