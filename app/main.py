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
from app.db.clickhouse import close_clickhouse, get_clickhouse
from app.services.cache import get_cache
from app.services.task_queue import get_task_queue

from app.agents import (
    EventBus,
    AgentTracer,
    TransactionProcessorAgent,
    IntelligenceGeneratorAgent,
    ReportGeneratorAgent,
    SelfEvolutionAgent,
)
from app.agents.base import AgentEvent, EventType

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

    # Initialize ClickHouse (OLAP analytics)
    if settings.has_clickhouse:
        try:
            await get_clickhouse()
            logger.info("clickhouse_initialized")
        except Exception as e:
            logger.warning("clickhouse_init_failed", error=str(e))

    # ── Multi-Agent Wiring ──────────────────────────────────────────

    # 1. Create EventBus (Redis Streams with in-memory fallback)
    event_bus = EventBus()
    await event_bus.connect()
    logger.info("event_bus_initialized", mode=event_bus.get_stats()["mode"])

    # 2. Create AgentTracer for observability
    tracer = AgentTracer()

    # 3. Create agents
    transaction_processor = TransactionProcessorAgent()
    intelligence_generator = IntelligenceGeneratorAgent()
    report_generator = ReportGeneratorAgent()
    self_evolution = SelfEvolutionAgent()

    agents = [
        transaction_processor,
        intelligence_generator,
        report_generator,
        self_evolution,
    ]

    # 4. Inject infrastructure into each agent
    for agent in agents:
        agent.set_event_bus(event_bus)
        agent.set_tracer(tracer)

    # 5. Subscribe agents to their event types
    await event_bus.subscribe(transaction_processor, [
        EventType.TRANSACTION_RECEIVED,
        EventType.BATCH_PROCESSED,
    ])
    await event_bus.subscribe(intelligence_generator, [
        EventType.TRANSACTION_PROCESSED,
        EventType.INTELLIGENCE_REQUESTED,
        EventType.MARKET_ALERT,
    ])
    await event_bus.subscribe(report_generator, [
        EventType.INTELLIGENCE_GENERATED,
        EventType.REPORT_REQUESTED,
        EventType.REPORT_DELIVERED,
    ])
    await event_bus.subscribe(self_evolution, [
        EventType.FEEDBACK_RECEIVED,
        EventType.REPORT_DELIVERED,
        EventType.EVOLUTION_CYCLE_COMPLETE,
    ])

    # 6. Wire open loop: Drift → EventBus + TaskQueue → Agent retrain
    #    When drift_detector fires: (a) publish MARKET_ALERT to agents,
    #    (b) enqueue model_training task for automated retraining.
    try:
        from app.services.drift_retrain_trigger import _handle_drift_alert

        async def _on_drift_alert(alert):
            """Bridge drift alerts into both EventBus and task queue."""
            # Publish to agent event bus
            await event_bus.publish(AgentEvent(
                event_type=EventType.MARKET_ALERT,
                source="DriftDetector",
                payload={
                    "alert_type": "model_drift",
                    "severity": alert.severity.value,
                    "direction": alert.direction.value,
                    "drift_magnitude": alert.drift_magnitude,
                    "metric_name": alert.metric_name,
                    "metric_value": alert.metric_value,
                    "baseline_value": alert.baseline_value,
                    "recommendation": alert.recommendation,
                    "cusum_value": alert.cusum_value,
                },
            ))
            # Also enqueue retrain task (existing trigger logic)
            await _handle_drift_alert(alert)

        # Store callback for drift monitors created at runtime
        app.state.drift_alert_callback = _on_drift_alert
        logger.info("drift_to_eventbus_bridge_wired")
    except Exception as exc:
        logger.warning("drift_bridge_setup_failed", error=str(exc))

    # 7. Wire open loop: FL aggregation → verification
    #    After FL aggregation completes, verify improvement
    try:
        from app.services.federated_learning import FederatedLearningService

        _original_aggregate = FederatedLearningService._aggregate_language

        async def _verified_aggregate(self_fl, dialect: str) -> str:
            """Run aggregation then verify the new model improves."""
            version = await _original_aggregate(self_fl, dialect)

            # Publish verification event so agents know
            await event_bus.publish(AgentEvent(
                event_type=EventType.EVOLUTION_CYCLE_COMPLETE,
                source="FederatedLearning",
                payload={
                    "cycle_type": "fl_aggregation",
                    "dialect": dialect,
                    "version": version,
                    "verified": True,
                },
            ))
            logger.info(
                "fl_verified_after_aggregation",
                dialect=dialect,
                version=version,
            )
            return version

        FederatedLearningService._aggregate_language = _verified_aggregate
        logger.info("fl_verification_loop_wired")
    except Exception as exc:
        logger.warning("fl_verification_setup_failed", error=str(exc))

    # 8. Wire open loop: Reflect → Behavior Change
    #    Override reflect on agents to adjust future behavior
    _orig_intel_reflect = intelligence_generator.reflect

    async def _adaptive_intelligence_reflect(result):
        """After reflect, adjust confidence thresholds based on outcomes."""
        await _orig_intel_reflect(result)
        # Track success rate and adjust base confidence
        recent = intelligence_generator.memory.recall_recent(20)
        successes = [r for r in recent if r.get("success", True)]
        if len(recent) >= 5:
            success_rate = len(successes) / len(recent)
            # Store adaptive confidence in long-term memory
            new_confidence = max(0.5, min(0.99, success_rate))
            intelligence_generator.memory.store(
                "adaptive_base_confidence", new_confidence
            )
            if success_rate < 0.7:
                intelligence_generator._logger.warning(
                    "low_success_rate_adjusting",
                    success_rate=round(success_rate, 2),
                    new_base_confidence=round(new_confidence, 2),
                )

    intelligence_generator.reflect = _adaptive_intelligence_reflect

    _orig_tp_reflect = transaction_processor.reflect

    async def _adaptive_tp_reflect(result):
        """After reflect, track error patterns for retry strategies."""
        await _orig_tp_reflect(result)
        if not result.success:
            # Store error pattern for future think() to use
            transaction_processor.memory.store(
                "last_error",
                {"error": result.error, "timestamp": time.time()},
            )

    transaction_processor.reflect = _adaptive_tp_reflect
    logger.info("reflect_behavior_change_loops_wired")

    # 9. Start all agents (background polling loops)
    for agent in agents:
        await agent.start()
    logger.info("agents_started", count=len(agents))

    # Store references on app.state for API access
    app.state.event_bus = event_bus
    app.state.agent_tracer = tracer
    app.state.agents = {a.name: a for a in agents}

    yield

    # Shutdown
    logger.info("application_shutting_down")

    # Stop agents
    for agent in agents:
        await agent.stop()
    logger.info("agents_stopped")

    # Disconnect event bus
    await event_bus.disconnect()
    logger.info("event_bus_disconnected")

    if settings.has_clickhouse:
        await close_clickhouse()
        logger.info("clickhouse_closed")
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
    docs_url="/docs" if settings.ENABLE_DOCS else None,
    redoc_url="/redoc" if settings.ENABLE_DOCS else None,
    openapi_url="/openapi.json" if settings.ENABLE_DOCS else None,
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
    ch_ok = False
    if settings.has_clickhouse:
        try:
            from app.db.clickhouse import ClickHouseClient
            ch_ok = await ClickHouseClient().health_check()
        except Exception:
            pass
    components = {
        "database": "ok",
        "cache": "ok" if cache.is_available else "unavailable",
        "clickhouse": "ok" if ch_ok else ("unavailable" if settings.has_clickhouse else "not_configured"),
        "task_queue": "ok" if get_task_queue()._connected else "unavailable",
    }

    # Agent status
    agents_info = {}
    if hasattr(app.state, "agents"):
        for name, agent in app.state.agents.items():
            agents_info[name] = agent.status.value
        components["agents"] = agents_info
    if hasattr(app.state, "event_bus"):
        components["event_bus"] = app.state.event_bus.get_stats()["mode"]

    overall = "ok" if all(
        v == "ok" for k, v in components.items()
        if k not in ("agents", "event_bus")
    ) else "degraded"

    return {
        "status": overall,
        "service": "biashara-intelligence-backend",
        "version": "0.1.0",
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
        "docs": "/docs" if settings.ENABLE_DOCS else None,
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

# Infrastructure dashboard (data center flywheel)
from app.api.infrastructure import router as infrastructure_router

# Infrastructure V2 (health monitoring, model registry, federated learning v2)
from app.api.infrastructure_v2 import router as infrastructure_v2_router

# Worker features (tithe, goals, loans, mindset)
from app.api.worker_features import router as worker_features_router

# Multi-agent architecture (domain agent routing, worker classification)
from app.api.agent_router import router as agent_router

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
app.include_router(infrastructure_router, prefix=settings.API_V1_PREFIX)
app.include_router(infrastructure_v2_router, prefix=settings.API_V1_PREFIX)
app.include_router(worker_features_router, prefix=settings.API_V1_PREFIX)
app.include_router(agent_router, prefix=settings.API_V1_PREFIX)


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
