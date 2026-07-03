"""
Angavu Intelligence — FastAPI Application

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
from app.agents.factory import AgentFactory

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

    # ── Multi-Agent Wiring (via AgentFactory) ─────────────────────
    agent_factory = AgentFactory()
    agent_infra = await agent_factory.create_all(
        enable_loops=True,
        enable_long_horizon=True,
    )

    # Unpack for local use and API access
    event_bus = agent_infra.event_bus
    tracer = agent_infra.tracer
    agents = agent_infra.agents

    # Store references on app.state for API access
    app.state.event_bus = event_bus
    app.state.agent_tracer = tracer
    app.state.agents = agent_infra.agent_map
    app.state.agent_factory = agent_factory
    app.state.agent_infra = agent_infra

    # V2: MetaAgent, domain agents, utility agents
    if agent_infra.meta_agent:
        app.state.meta_agent = agent_infra.meta_agent
    if agent_infra.domain_agents:
        app.state.domain_agents = {a.name: a for a in agent_infra.domain_agents}
    if agent_infra.utility_agents:
        app.state.utility_agents = {a.name: a for a in agent_infra.utility_agents}
    if agent_infra.broadcast_protocol:
        app.state.broadcast_protocol = agent_infra.broadcast_protocol
    if agent_infra.p2p_protocol:
        app.state.p2p_protocol = agent_infra.p2p_protocol
    if agent_infra.delegation_protocol:
        app.state.delegation_protocol = agent_infra.delegation_protocol

    # Store DeerFlow integration on app.state if available
    if agent_infra.deerflow_factory:
        app.state.deerflow_factory = agent_infra.deerflow_factory
        app.state.deerflow_lead_agent = agent_infra.deerflow_lead_agent
        logger.info(
            "deerflow_agents_ready",
            domain_agents=agent_infra.deerflow_factory.list_agents(),
            has_lead=agent_infra.deerflow_lead_agent is not None,
        )

    # Store loop infrastructure on app.state if available
    if agent_infra.loop_supervisor:
        app.state.loop_event_store = agent_infra.loop_event_store
        app.state.loop_supervisor = agent_infra.loop_supervisor
        app.state.loop_agents = {a.name: a for a in agent_infra.loop_agents}

        # Wire loop infrastructure into the API
        set_loop_infrastructure(
            supervisor=agent_infra.loop_supervisor,
            event_store=agent_infra.loop_event_store,
            agents=agent_infra.loop_agents,
        )

    # Store long-horizon infrastructure if available
    if agent_infra.intelligence_flows:
        app.state.intelligence_flows = agent_infra.intelligence_flows
        app.state.research_orchestrator = agent_infra.research_orchestrator

        set_long_horizon_infrastructure(
            intelligence_flows=agent_infra.intelligence_flows,
            research_orchestrator=agent_infra.research_orchestrator,
        )

    # Initialize Autonomous Orchestrator
    try:
        from app.autonomous.orchestrator import AutonomousOrchestrator
        from app.autonomous.escalation import EscalationManager
        from app.autonomous.monitoring import AgentMonitor
        from app.autonomous.config import AgentConfigManager

        auto_orchestrator = AutonomousOrchestrator(
            event_bus=event_bus,
            tracer=tracer,
            escalation_manager=EscalationManager(),
            monitor=AgentMonitor(),
            config_manager=AgentConfigManager(),
        )
        await auto_orchestrator.start()
        app.state.autonomous_orchestrator = auto_orchestrator
        logger.info("autonomous_orchestrator_started")
    except Exception as exc:
        logger.warning("autonomous_orchestrator_setup_failed", error=str(exc))

    # Wire open loop: Drift → EventBus + TaskQueue → Agent retrain
    try:
        from app.services.drift_retrain_trigger import _handle_drift_alert

        async def _on_drift_alert(alert):
            """Bridge drift alerts into both EventBus and task queue."""
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
            await _handle_drift_alert(alert)

        app.state.drift_alert_callback = _on_drift_alert
        logger.info("drift_to_eventbus_bridge_wired")
    except Exception as exc:
        logger.warning("drift_bridge_setup_failed", error=str(exc))

    # Wire open loop: FL aggregation → verification
    try:
        from app.services.federated_learning import FederatedLearningService

        _original_aggregate = FederatedLearningService._aggregate_language

        async def _verified_aggregate(self_fl, dialect: str) -> str:
            """Run aggregation then verify the new model improves."""
            version = await _original_aggregate(self_fl, dialect)
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

    # Loop and long-horizon infrastructure is now managed by AgentFactory
    # (see agent_factory.create_all() above)

    # Initialize MCP server
    from app.mcp.server import get_mcp_server
    mcp_server = get_mcp_server()
    app.state.mcp_server = mcp_server
    logger.info("mcp_server_initialized", tools=mcp_server.get_health()["tools_registered"])

    yield

    # Shutdown
    logger.info("application_shutting_down")

    # Graceful agent shutdown via factory (reverse order)
    await agent_factory.shutdown()
    logger.info("agents_shutdown_complete")

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
    title="Angavu Intelligence",
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


# Security headers middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Add security headers to every response."""
    response = await call_next(request)
    response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; frame-ancestors 'none'; "
        "script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; connect-src 'self'"
    )
    return response


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
        "service": "Angavu Intelligence Backend",
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

# OmniRoute-inspired model router (multi-provider inference gateway)
from app.api.model_router import router as model_router_api

# Skills API (degree-to-skill mappings)
from app.api.skills import router as skills_router

# Agentic loop patterns (ReAct, Reflexion, Plan-Execute, Event Sourcing, Supervisor)
from app.api.agent_loops import router as agent_loops_router
from app.api.agent_loops import set_loop_infrastructure

# Long-horizon research (DeerFlow-inspired orchestration)
from app.api.long_horizon import router as long_horizon_router
from app.api.long_horizon import set_long_horizon_infrastructure

# MCP (Model Context Protocol) server
from app.mcp.router import router as mcp_router

# Goal Planner (accountability-driven goal tracking)
from app.api.v1.goals import router as goals_router

# 12-Factor: Multi-channel triggers (WhatsApp, USSD, SMS, Voice)
from app.api.trigger_router import router as trigger_router

# Loan Manager (dedicated loan management with purpose verification)
from app.api.v1.loans import router as loans_router

# Stickiness / Engagement (gamification, badges, streaks, social proof)
from app.api.stickiness import router as stickiness_router

# Tithe Tracker — dedicated giving tracking API
from app.api.v1.tithe import router as tithe_router

# Wealth Mindset (56 lessons, rich habits, affirmations, mastermind)
from app.api.v1.mindset import router as mindset_router

# Autonomous Revenue Operations (leads, invoicing, content, onboarding)
from app.autonomous.api.router import router as autonomous_router

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
app.include_router(model_router_api, prefix=settings.API_V1_PREFIX)
app.include_router(skills_router, prefix=settings.API_V1_PREFIX)
app.include_router(agent_loops_router, prefix=settings.API_V1_PREFIX)
app.include_router(long_horizon_router, prefix=settings.API_V1_PREFIX)
app.include_router(mcp_router, prefix=settings.API_V1_PREFIX)
app.include_router(goals_router, prefix=settings.API_V1_PREFIX)
app.include_router(trigger_router, prefix=settings.API_V1_PREFIX)
app.include_router(loans_router, prefix=settings.API_V1_PREFIX)
app.include_router(stickiness_router, prefix=settings.API_V1_PREFIX)
app.include_router(tithe_router, prefix=settings.API_V1_PREFIX)
app.include_router(mindset_router, prefix=settings.API_V1_PREFIX)
app.include_router(autonomous_router)

# Mount autonomous router (prefix is built into the router)


# =========================================================================
# Startup Banner
# =========================================================================


@app.on_event("startup")
async def startup_banner():
    """Print startup banner for visibility."""
    logger.info("=" * 60)
    logger.info("🇰🇪 Angavu Intelligence — Backend Starting")
    logger.info(f"   Environment: {settings.APP_ENV}")
    logger.info(f"   API Prefix:  {settings.API_V1_PREFIX}")
    logger.info(f"   Debug:       {settings.DEBUG}")
    logger.info("=" * 60)
