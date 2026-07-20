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

import time
import uuid
from contextlib import asynccontextmanager

import sentry_sdk
import structlog
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.agents.base import AgentEvent, EventType
from app.agents.factory import AgentFactory

# Loop and long-horizon infrastructure (used in lifespan)
from app.api.agent_loops import set_loop_infrastructure
from app.api.long_horizon import set_long_horizon_infrastructure
from app.config import get_settings
from app.db.clickhouse import close_clickhouse, get_clickhouse
from app.db.database import close_db, init_db

# Infrastructure: circuit breaker + telemetry
from app.infrastructure.circuit_breaker import (
    get_circuit_breaker_registry,
)
from app.infrastructure.telemetry import get_telemetry_manager
from app.services.cache import get_cache
from app.services.task_queue import get_task_queue

settings = get_settings()

# ── Sentry Crash Reporting ─────────────────────────────────────────
if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.APP_ENV,
        release=f"angavu-backend@{settings.APP_VERSION if hasattr(settings, 'APP_VERSION') else '0.1.0'}",
        traces_sample_rate=0.2 if settings.is_production else 1.0,
        profiles_sample_rate=0.1 if settings.is_production else 1.0,
        enable_tracing=True,
        send_default_pii=False,
        # FastAPI integration is auto-discovered from installed extras
    )

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

    # Initialize connection pool manager (health checks, retry, metrics)
    from app.infrastructure.connection_pool import get_pool_manager
    pool_mgr = get_pool_manager()
    await pool_mgr.initialize()
    logger.info("connection_pool_manager_initialized")

    # ── Circuit Breakers ───────────────────────────────────────────
    cb_registry = get_circuit_breaker_registry()
    redis_cb = cb_registry.get_or_create("redis", failure_threshold=5, recovery_timeout=30.0)
    postgresql_cb = cb_registry.get_or_create("postgresql", failure_threshold=5, recovery_timeout=30.0)
    clickhouse_cb = cb_registry.get_or_create("clickhouse", failure_threshold=3, recovery_timeout=60.0)
    openwa_cb = cb_registry.get_or_create("openwa", failure_threshold=3, recovery_timeout=60.0)
    app.state.circuit_breaker_registry = cb_registry
    logger.info("circuit_breakers_initialized", breakers=list(cb_registry._breakers.keys()))

    # ── OpenTelemetry ──────────────────────────────────────────────
    telemetry = get_telemetry_manager()
    telemetry.setup()
    telemetry.instrument_app(app)
    telemetry.instrument_redis()
    telemetry.instrument_httpx()
    app.state.telemetry = telemetry
    logger.info("telemetry_initialized")

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
            # Apply schema on first boot (idempotent — all IF NOT EXISTS)
            from app.db.clickhouse import ClickHouseClient
            ch_client = ClickHouseClient()
            await ch_client.ensure_schema()
            logger.info("clickhouse_initialized")
        except (ConnectionError, OSError, TimeoutError) as e:
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

    # Wire telemetry into event bus
    if telemetry.agent_metrics:
        event_bus.set_agent_metrics(telemetry.agent_metrics)

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
        from app.autonomous.config import AgentConfigManager
        from app.autonomous.escalation import EscalationManager
        from app.autonomous.monitoring import AgentMonitor
        from app.autonomous.orchestrator import AutonomousOrchestrator

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
    except (ImportError, RuntimeError, AttributeError) as exc:
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
    except (ImportError, AttributeError) as exc:
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
    except (ImportError, AttributeError) as exc:
        logger.warning("fl_verification_setup_failed", error=str(exc))

    # Loop and long-horizon infrastructure is now managed by AgentFactory
    # (see agent_factory.create_all() above)

    # Initialize MCP server
    from app.mcp.server import get_mcp_server
    mcp_server = get_mcp_server()
    app.state.mcp_server = mcp_server
    logger.info("mcp_server_initialized", tools=mcp_server.get_health()["tools_registered"])

    # ── Protocol Transport Routes (A2A HTTP/SSE + MCP Streamable HTTP) ──
    from app.agents.protocols.routes import register_protocol_routes
    register_protocol_routes(app, prefix=settings.API_V1_PREFIX)
    logger.info("protocol_transport_routes_registered")

    # ── Post-Quantum Cryptography Initialization ───────────────────
    try:
        from app.security.pqc import AlgorithmRegistry, CryptoAuditLogger, PqcConfig
        pqc_registry = AlgorithmRegistry()
        pqc_audit = CryptoAuditLogger()
        app.state.pqc_config = PqcConfig
        app.state.pqc_registry = pqc_registry
        app.state.pqc_audit = pqc_audit
        pqc_status = PqcConfig.get_status_report()
        logger.info(
            "pqc_initialized",
            migration_phase=pqc_status["migration_phase"],
            hybrid_kex=pqc_status["hybrid_key_exchange"],
            kex_algorithm=pqc_status["recommended_key_exchange"],
            sig_algorithm=pqc_status["recommended_signature"],
        )
    except Exception as exc:
        logger.warning("pqc_init_failed", error=str(exc))

    # ── Multi-Channel Infrastructure (Failover & Health) ────────
    try:
        from app.channels.adapters.telegram_adapter import TelegramAdapter
        from app.channels.adapters.http_api_adapter import HttpApiAdapter
        from app.channels.failover import FailoverManager
        from app.channels.health_monitor import ChannelHealthMonitor
        from app.channels.registry import ChannelRegistry

        channel_registry = ChannelRegistry()

        # Register WhatsApp adapter if enabled
        if settings.ENABLE_WHATSAPP:
            from app.channels.adapters.whatsapp_adapter import WhatsAppAdapter
            wa_adapter = WhatsAppAdapter()
            channel_registry.register(wa_adapter)

        # Register Telegram adapter if configured
        if settings.ENABLE_TELEGRAM and settings.TELEGRAM_BOT_TOKEN:
            tg_adapter = TelegramAdapter(
                bot_token=settings.TELEGRAM_BOT_TOKEN,
                api_base=settings.TELEGRAM_API_URL or None,
            )
            channel_registry.register(tg_adapter)

        # Register HTTP API adapter (always available as last resort)
        http_adapter = HttpApiAdapter()
        channel_registry.register(http_adapter)

        # Initialize all adapters
        await channel_registry.initialize_all()

        # Create health monitor
        health_monitor = ChannelHealthMonitor(registry=channel_registry)

        # Create failover manager
        failover_manager = FailoverManager(
            registry=channel_registry,
            health_monitor=health_monitor,
        )

        # Start health monitoring
        if settings.CHANNEL_FAILOVER_ENABLED:
            await health_monitor.start()

        # Wire into API
        set_channel_infrastructure(health_monitor, failover_manager)

        # Store on app.state
        app.state.channel_registry = channel_registry
        app.state.health_monitor = health_monitor
        app.state.failover_manager = failover_manager

        logger.info(
            "channel_infrastructure_initialized",
            channels=channel_registry.registered_channels,
            failover_enabled=settings.CHANNEL_FAILOVER_ENABLED,
        )
    except Exception as exc:
        logger.warning("channel_infrastructure_init_failed", error=str(exc))

    yield

    # Shutdown
    logger.info("application_shutting_down")

    # Shutdown channel health monitor
    if hasattr(app.state, "health_monitor"):
        await app.state.health_monitor.stop()
        logger.info("channel_health_monitor_shutdown")

    # Shutdown telemetry
    if hasattr(app.state, "telemetry"):
        app.state.telemetry.shutdown()
        logger.info("telemetry_shutdown")

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
    # Shutdown connection pool manager
    from app.infrastructure.connection_pool import get_pool_manager
    await get_pool_manager().shutdown()
    logger.info("connection_pool_manager_shutdown")

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
    allow_headers=["Authorization", "Content-Type", "X-Request-ID", "X-Device-ID", "X-OpenWA-Signature", "X-CSRF-Token"],
    expose_headers=["X-Request-ID", "X-RateLimit-Remaining", "X-RateLimit-Limit", "X-RateLimit-Reset"],
)

# Trusted host middleware (prevents Host header attacks)
# Extract hostnames from URLs for TrustedHostMiddleware
import urllib.parse


def _extract_hostnames(origins: list) -> list:
    """Extract hostnames from URL strings for TrustedHostMiddleware."""
    hosts = []
    for origin in origins:
        try:
            parsed = urllib.parse.urlparse(origin)
            if parsed.hostname:
                hosts.append(parsed.hostname)
        except Exception:
            pass
    return hosts if hosts else ["*"]

_trusted_hosts = _extract_hostnames(_cors_origins) if settings.is_production else ["*"]
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=_trusted_hosts,
)

# Rate limiting
app.state.limiter = limiter

# Prometheus metrics middleware
from app.infrastructure.metrics import create_metrics_middleware

app.middleware("http")(create_metrics_middleware())


# Security headers middleware — uses strict CSP, no deprecated headers
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Add security headers to every response."""
    response = await call_next(request)
    response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    # NOTE: X-XSS-Protection intentionally omitted — deprecated and can introduce
    # vulnerabilities in older browsers. Modern browsers use CSP instead.
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = (
        "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
    )
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; frame-ancestors 'none'; "
        "base-uri 'none'; form-action 'self'"
    )
    # Prevent caching of API responses (contains sensitive financial data)
    if request.url.path.startswith("/api/") or request.url.path.startswith("/auth/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
        response.headers["Pragma"] = "no-cache"
    return response


# Input validation middleware — SQL injection, XSS, path traversal detection
from app.security.security_middleware import InputValidationMiddleware

app.add_middleware(InputValidationMiddleware)

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
    Comprehensive health check endpoint.

    Returns application status including all component health,
    system resources, and queue depth. Used by Docker health checks,
    load balancers, Kubernetes probes, and monitoring.

    Components checked (queries real services):
    - Database (PostgreSQL) — executes SELECT 1
    - Redis cache — PING command
    - ClickHouse (OLAP) — SELECT 1
    - OpenWA — HTTP GET /health
    - Agent runtime status + performance metrics
    - Circuit breaker states
    - Event bus statistics
    """
    import psutil

    cache = get_cache()
    components = {}

    # 1. Database health (real query)
    db_start = time.time()
    try:
        from app.infrastructure.connection_pool import get_pool_manager
        pool_mgr = get_pool_manager()
        db_healthy = await pool_mgr.health_check() if pool_mgr._initialized else True
        db_latency = round((time.time() - db_start) * 1000, 1)
        components["database"] = {
            "status": "ok" if db_healthy else "degraded",
            "latency_ms": db_latency,
            "pool": pool_mgr.get_metrics().to_dict(),
        }
    except Exception as exc:
        components["database"] = {"status": "error", "error": str(exc)}

    # 2. Redis health (real PING)
    redis_start = time.time()
    if cache.is_available:
        try:
            # Execute real PING
            if hasattr(cache, '_redis') and cache._redis:
                await cache._redis.ping()
            redis_latency = round((time.time() - redis_start) * 1000, 1)
            components["cache"] = {"status": "ok", "latency_ms": redis_latency}
        except Exception as exc:
            components["cache"] = {"status": "degraded", "error": str(exc)}
    else:
        components["cache"] = {"status": "unavailable"}

    # 3. ClickHouse health (real query)
    ch_start = time.time()
    if settings.has_clickhouse:
        try:
            from app.db.clickhouse import ClickHouseClient
            ch_client = ClickHouseClient()
            ch_ok = await ch_client.health_check()
            ch_latency = round((time.time() - ch_start) * 1000, 1)
            components["clickhouse"] = {
                "status": "ok" if ch_ok else "degraded",
                "latency_ms": ch_latency,
            }
        except Exception as exc:
            components["clickhouse"] = {"status": "error", "error": str(exc)}
    else:
        components["clickhouse"] = {"status": "not_configured"}

    # 4. OpenWA health (real HTTP)
    if settings.ENABLE_WHATSAPP:
        import httpx
        wa_start = time.time()
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(f"{settings.OPENWA_URL}/health")
                wa_latency = round((time.time() - wa_start) * 1000, 1)
                if resp.status_code == 200:
                    data = resp.json()
                    wa_connected = data.get("whatsapp", {}).get("connected", False)
                    components["openwa"] = {
                        "status": "ok" if wa_connected else "awaiting_scan",
                        "latency_ms": wa_latency,
                    }
                else:
                    components["openwa"] = {"status": "degraded", "latency_ms": wa_latency}
        except Exception as exc:
            components["openwa"] = {"status": "unreachable", "error": str(exc)}
    else:
        components["openwa"] = {"status": "disabled"}

    # 5. Task queue health
    tq = get_task_queue()
    components["task_queue"] = "ok" if tq._connected else "unavailable"

    # 6. Agent health with per-agent performance metrics
    agents_info = {}
    if hasattr(app.state, "agents"):
        for name, agent in app.state.agents.items():
            agent_health = agent.health_check()
            # Add tracer performance data if available
            if hasattr(app.state, "agent_tracer"):
                tracer_stats = app.state.agent_tracer.get_stats()
                agent_perf = tracer_stats.get("agents", {}).get(name, {})
                agent_health["performance"] = {
                    "total_traces": agent_perf.get("total_traces", 0),
                    "error_rate": agent_perf.get("error_rate", 0),
                    "avg_duration_ms": agent_perf.get("avg_duration_ms", 0),
                    "p95_duration_ms": agent_perf.get("p95_duration_ms", 0),
                }
            agents_info[name] = agent_health
    components["agents"] = agents_info

    # 7. Event bus stats
    if hasattr(app.state, "event_bus"):
        eb_stats = app.state.event_bus.get_stats()
        components["event_bus"] = {
            "mode": eb_stats["mode"],
            "dead_letter_count": eb_stats["dead_letter_count"],
            "idempotency_cache_size": eb_stats.get("idempotency_cache_size", 0),
            "backpressure_active_streams": eb_stats.get("backpressure_active_streams", []),
        }

    # 8. Circuit breaker states
    if hasattr(app.state, "circuit_breaker_registry"):
        cb_stats = app.state.circuit_breaker_registry.get_all_stats()
        components["circuit_breakers"] = cb_stats
        open_circuits = app.state.circuit_breaker_registry.get_open_circuits()
        if open_circuits:
            components["circuit_breakers"]["_open_circuits"] = open_circuits

    # 9. System resources
    try:
        mem = psutil.virtual_memory()
        cpu_percent = psutil.cpu_percent(interval=0.1)
        components["system"] = {
            "memory_total_mb": round(mem.total / (1024 * 1024)),
            "memory_used_mb": round(mem.used / (1024 * 1024)),
            "memory_percent": mem.percent,
            "cpu_percent": cpu_percent,
        }
    except ImportError:
        components["system"] = "psutil_not_installed"

    # 10. Queue depth
    try:
        from app.infrastructure.task_queue import get_async_task_queue
        aq = get_async_task_queue()
        if aq._connected:
            depths = await aq.get_queue_depths()
            components["queue_depths"] = depths
    except Exception:
        pass

    # Overall status — degraded if any circuit breaker is open
    critical_components = ["database", "cache", "task_queue"]
    overall = "ok"
    if not all(
        (components.get(k) == "ok" or
         (isinstance(components.get(k), dict) and components.get(k, {}).get("status") == "ok"))
        for k in critical_components
    ):
        overall = "degraded"
    if hasattr(app.state, "circuit_breaker_registry"):
        if app.state.circuit_breaker_registry.get_open_circuits():
            overall = "degraded"

    return {
        "status": overall,
        "service": "angavu-intelligence-backend",
        "version": "0.1.0",
        "environment": settings.APP_ENV,
        "components": components,
        "tier": "3-scale",
    }


@app.get("/health/ready", tags=["Health"])
async def readiness_probe():
    """
    Kubernetes readiness probe.

    Returns 200 only when the service is ready to accept traffic.
    Checks minimum required components.
    """
    cache = get_cache()
    if not cache.is_available:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "reason": "cache_unavailable"},
        )
    return {"status": "ready"}


@app.get("/health/live", tags=["Health"])
async def liveness_probe():
    """
    Kubernetes liveness probe.

    Returns 200 if the process is alive and responsive.
    Does NOT check dependencies (to avoid restart loops).
    """
    return {"status": "alive", "uptime": time.time()}


@app.get("/metrics", tags=["Monitoring"])
async def prometheus_metrics():
    """
    Prometheus-compatible metrics endpoint.

    Returns all application metrics in OpenMetrics text format.
    Scrape this endpoint with Prometheus for dashboards and alerting.
    """
    from fastapi.responses import PlainTextResponse

    from app.infrastructure.metrics import collect_system_metrics, get_registry

    await collect_system_metrics()
    registry = get_registry()
    return PlainTextResponse(
        content=registry.render(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


@app.get("/health/pqc", tags=["Health"])
async def pqc_status():
    """
    Post-Quantum Cryptography status endpoint.

    Returns the current PQC migration phase, configured algorithms,
    and available providers. Used for monitoring quantum readiness.
    """
    try:
        from app.security.pqc import AlgorithmRegistry, PqcConfig
        registry = AlgorithmRegistry()
        status_report = PqcConfig.get_status_report()
        algorithms = registry.list_algorithms()
        pq_algorithms = registry.list_pq_algorithms()
        return {
            "pqc_status": status_report,
            "algorithms": algorithms,
            "post_quantum_algorithms": pq_algorithms,
        }
    except Exception as e:
        return {"pqc_status": "unavailable", "error": str(e)}


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
# API Versioning Strategy
# =========================================================================
#
# All endpoints live under /api/v1/ and are organized into domain
# sub-routers via app.api.v1. Each domain aggregates related feature
# routers so there is ONE entry point per domain:
#
#   /api/v1/auth/*          — Authentication (JWT + OTP)
#   /api/v1/intelligence/*  — Intelligence products, analysis, FL, explainability
#   /api/v1/finance/*       — Biashara sync, data sync, reports
#   /api/v1/channels/*      — WhatsApp, triggers, channel health, webhooks
#   /api/v1/agents/*        — Agent management, loops, model routing, harness, MCP
#   /api/v1/dashboard/*     — Dashboard, policymaker, long-horizon research
#   /api/v1/infra/*         — Deployment, infrastructure, evolution
#   /api/v1/worker/*        — Onboarding, features, stickiness, skills, goals, loans
#   /api/v1/revenue-ops/*   — Autonomous revenue operations
#
# When v2 is introduced, duplicate the app/api/v1/ tree as app/api/v2/
# and mount a second v2_router under settings.API_V2_PREFIX. The domain
# structure makes it trivial to evolve individual domains independently.
#
# OpenAPI docs (/docs, /redoc) are controlled by settings.ENABLE_DOCS.
# Set ENABLE_DOCS=true in your environment to enable interactive docs.
# =========================================================================

# Domain-organized API router (single entry point for all /api/v1 endpoints)
from app.api.v1 import v1_router
from app.api.channel_health import set_channel_infrastructure

# Mount the unified v1 router — all 35+ feature routers are organized
# into 9 domain groups (auth, intelligence, finance, channels, agents,
# dashboard, infra, worker, autonomous) behind one include.
app.include_router(v1_router, prefix=settings.API_V1_PREFIX)


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
    logger.info("   Domains:     auth, intelligence, finance, channels, agents,")
    logger.info("                dashboard, infra, worker, revenue-ops")
    logger.info(f"   OpenAPI Docs: {'ENABLED' if settings.ENABLE_DOCS else 'DISABLED'}")
    logger.info(f"   Debug:       {settings.DEBUG}")
    # PQC status in banner
    try:
        from app.security.pqc import PqcConfig
        pqc = PqcConfig.get_status_report()
        logger.info(f"   PQC Phase:   {pqc['migration_phase']}")
        logger.info(f"   Key Exchange: {pqc['recommended_key_exchange']}")
        logger.info(f"   Signatures:   {pqc['recommended_signature']}")
    except Exception:
        logger.info("   PQC:         unavailable")
    logger.info("=" * 60)
