"""
Angavu Intelligence Backend — Main Application

FastAPI application serving as the collective intelligence platform
for Msaidizi super agents.

Architecture: arch_backend.md
- No agents, direct service calls
- Pre-computed intelligence products
- Vector clock sync with conflict resolution
- Federated learning aggregation
- Buyer dashboard (B2B API)
"""
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from app.api.v1 import sync, intelligence, buyer, auth, health, fl
from app.config import settings

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown."""
    logger.info("angavu_starting", version=settings.APP_VERSION, env=settings.ENVIRONMENT)

    # Initialize database
    from app.db.database import init_db
    await init_db()

    # Initialize Redis
    from app.db.redis import get_redis
    try:
        await get_redis()
    except Exception as e:
        logger.warning("redis_unavailable", error=str(e))

    logger.info("angavu_ready")
    yield

    # Shutdown
    logger.info("angavu_shutting_down")
    from app.db.redis import close_redis
    from app.db.database import close_db
    from app.db.clickhouse import close_clickhouse

    await close_redis()
    close_clickhouse()
    await close_db()
    logger.info("angavu_stopped")


app = FastAPI(
    title="Angavu Intelligence API",
    description="Africa's operating system for the informal economy — collective intelligence for 600M+ workers",
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Input validation middleware
from app.middleware.input_validation import InputValidationMiddleware
app.add_middleware(InputValidationMiddleware)

# API Routes
app.include_router(health.router, tags=["Health"])
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(sync.router, prefix="/api/v1/sync", tags=["Sync"])
app.include_router(intelligence.router, prefix="/api/v1/intelligence", tags=["Intelligence"])
app.include_router(fl.router, prefix="/api/v1", tags=["Federated Learning"])
app.include_router(buyer.router, prefix="/api/v1/buyer", tags=["Buyer Dashboard"])


@app.get("/")
async def root():
    return {
        "name": "Angavu Intelligence",
        "version": settings.APP_VERSION,
        "description": "Africa's operating system for the informal economy",
        "status": "running",
        "docs": "/docs" if settings.ENVIRONMENT != "production" else None,
        "endpoints": {
            "health": "/health",
            "metrics": "/metrics",
            "auth": "/api/v1/auth",
            "sync": "/api/v1/sync",
            "intelligence": "/api/v1/intelligence",
            "federated_learning": "/api/v1/fl",
            "buyer": "/api/v1/buyer",
        },
    }
