"""Angavu Intelligence Backend — FastAPI Application."""
from __future__ import annotations

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from app.core import settings
from app.core.logging import setup_logging, get_logger
from app.api.v1.router import api_router

logger = get_logger(__name__)

_start_time = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown hooks."""
    setup_logging()
    logger.info("angavu.startup", environment=settings.ENVIRONMENT, version=settings.VERSION)
    yield
    logger.info("angavu.shutdown")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan,
)

# ── CORS ───────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Prometheus metrics ─────────────────────────────────────────
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# ── API Routes ─────────────────────────────────────────────────
app.include_router(api_router, prefix=settings.API_V1_PREFIX)


# ── Health Check ───────────────────────────────────────────────
@app.get("/health", tags=["System"])
async def health_check():
    """Basic health check — always returns 200 if process is alive."""
    return {
        "status": "ok",
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "uptime_seconds": round(time.time() - _start_time, 2),
    }


@app.get("/health/ready", tags=["System"])
async def readiness_check():
    """Readiness check — verifies DB and Redis connectivity."""
    from app.core.database import engine
    from app.core.redis import get_redis

    services = {}
    try:
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        services["postgres"] = "ok"
    except Exception as e:
        services["postgres"] = f"error: {e}"

    try:
        r = get_redis()
        await r.ping()
        services["redis"] = "ok"
    except Exception as e:
        services["redis"] = f"error: {e}"

    all_ok = all(v == "ok" for v in services.values())
    return {
        "status": "ok" if all_ok else "degraded",
        "services": services,
    }
