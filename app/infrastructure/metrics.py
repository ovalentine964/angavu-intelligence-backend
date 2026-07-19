"""
Prometheus Metrics — Observability for Angavu Intelligence backend.

Exports application metrics in Prometheus exposition format for scraping.
Covers all critical dimensions:
- HTTP request count, latency (p50/p95/p99), error rate
- Agent execution time per agent type
- Database query time per query type
- Redis operation time
- Queue depth and processing rate
- Cache hit rate

Design:
    Uses prometheus_client (standard Python client) for metric collection.
    Exposes /metrics endpoint for Prometheus scraping.
    Labels are used for dimensional slicing (method, path, agent_type, etc.)

Metric Naming Convention (OpenTelemetry-compatible):
    angavu_<category>_<name>_<unit>
    - angavu_http_requests_total (Counter)
    - angavu_http_request_duration_seconds (Histogram)
    - angavu_agent_execution_duration_seconds (Histogram)
    - angavu_db_query_duration_seconds (Histogram)
    - angavu_redis_operation_duration_seconds (Histogram)
    - angavu_queue_depth (Gauge)
    - angavu_cache_operations_total (Counter)

References:
- Prometheus Best Practices: https://prometheus.io/docs/practices/naming/
- RED Method (Rate, Errors, Duration) for HTTP services
- USE Method (Utilization, Saturation, Errors) for infrastructure
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Dict, Generator, Optional

import structlog

logger = structlog.get_logger(__name__)

# ── Prometheus Client ──────────────────────────────────────────────

try:
    from prometheus_client import (
        CollectorRegistry,
        Counter,
        Gauge,
        Histogram,
        Info,
        generate_latest,
        CONTENT_TYPE_LATEST,
    )
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    logger.warning("prometheus_client_not_installed_metrics_disabled")

# ── Registry ───────────────────────────────────────────────────────

# Custom registry to avoid conflicts with default prometheus_client registry
_registry = CollectorRegistry(auto_describe=True) if PROMETHEUS_AVAILABLE else None

# ── HTTP Metrics (RED Method) ──────────────────────────────────────

if PROMETHEUS_AVAILABLE:
    HTTP_REQUESTS_TOTAL = Counter(
        "angavu_http_requests_total",
        "Total HTTP requests",
        ["method", "path", "status_code"],
        registry=_registry,
    )

    HTTP_REQUEST_DURATION_SECONDS = Histogram(
        "angavu_http_request_duration_seconds",
        "HTTP request duration in seconds",
        ["method", "path"],
        buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
        registry=_registry,
    )

    HTTP_REQUESTS_IN_PROGRESS = Gauge(
        "angavu_http_requests_in_progress",
        "Number of HTTP requests currently in progress",
        ["method", "path"],
        registry=_registry,
    )

    HTTP_REQUEST_SIZE_BYTES = Histogram(
        "angavu_http_request_size_bytes",
        "HTTP request body size in bytes",
        ["method", "path"],
        buckets=[100, 1000, 10000, 100000, 1000000],
        registry=_registry,
    )

    HTTP_RESPONSE_SIZE_BYTES = Histogram(
        "angavu_http_response_size_bytes",
        "HTTP response body size in bytes",
        ["method", "path"],
        buckets=[100, 1000, 10000, 100000, 1000000],
        registry=_registry,
    )

# ── Agent Metrics ──────────────────────────────────────────────────

if PROMETHEUS_AVAILABLE:
    AGENT_EXECUTION_DURATION_SECONDS = Histogram(
        "angavu_agent_execution_duration_seconds",
        "Agent execution time in seconds",
        ["agent_type", "agent_name"],
        buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0],
        registry=_registry,
    )

    AGENT_EXECUTIONS_TOTAL = Counter(
        "angavu_agent_executions_total",
        "Total agent executions",
        ["agent_type", "agent_name", "status"],
        registry=_registry,
    )

    AGENT_EVENTS_PUBLISHED = Counter(
        "angavu_agent_events_published_total",
        "Total events published by agents",
        ["event_type", "source_agent"],
        registry=_registry,
    )

    AGENT_EVENTS_CONSUMED = Counter(
        "angavu_agent_events_consumed_total",
        "Total events consumed by agents",
        ["event_type", "consumer_group"],
        registry=_registry,
    )

# ── Database Metrics (USE Method) ──────────────────────────────────

if PROMETHEUS_AVAILABLE:
    DB_QUERY_DURATION_SECONDS = Histogram(
        "angavu_db_query_duration_seconds",
        "Database query duration in seconds",
        ["query_type", "table"],
        buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5],
        registry=_registry,
    )

    DB_QUERIES_TOTAL = Counter(
        "angavu_db_queries_total",
        "Total database queries",
        ["query_type", "table", "status"],
        registry=_registry,
    )

    DB_CONNECTION_POOL_SIZE = Gauge(
        "angavu_db_connection_pool_size",
        "Database connection pool size",
        registry=_registry,
    )

    DB_CONNECTION_POOL_CHECKED_OUT = Gauge(
        "angavu_db_connection_pool_checked_out",
        "Database connections currently checked out",
        registry=_registry,
    )

    DB_CONNECTION_POOL_OVERFLOW = Gauge(
        "angavu_db_connection_pool_overflow",
        "Database connection pool overflow count",
        registry=_registry,
    )

# ── Redis Metrics ──────────────────────────────────────────────────

if PROMETHEUS_AVAILABLE:
    REDIS_OPERATION_DURATION_SECONDS = Histogram(
        "angavu_redis_operation_duration_seconds",
        "Redis operation duration in seconds",
        ["operation"],
        buckets=[0.0005, 0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5],
        registry=_registry,
    )

    REDIS_OPERATIONS_TOTAL = Counter(
        "angavu_redis_operations_total",
        "Total Redis operations",
        ["operation", "status"],
        registry=_registry,
    )

# ── Queue Metrics ──────────────────────────────────────────────────

if PROMETHEUS_AVAILABLE:
    QUEUE_DEPTH = Gauge(
        "angavu_queue_depth",
        "Current task queue depth",
        ["priority"],
        registry=_registry,
    )

    QUEUE_TASKS_ENQUEUED = Counter(
        "angavu_queue_tasks_enqueued_total",
        "Total tasks enqueued",
        ["priority"],
        registry=_registry,
    )

    QUEUE_TASKS_COMPLETED = Counter(
        "angavu_queue_tasks_completed_total",
        "Total tasks completed",
        ["priority"],
        registry=_registry,
    )

    QUEUE_TASKS_FAILED = Counter(
        "angavu_queue_tasks_failed_total",
        "Total tasks failed",
        ["priority"],
        registry=_registry,
    )

    QUEUE_TASKS_DEAD_LETTERED = Counter(
        "angavu_queue_tasks_dead_lettered_total",
        "Total tasks dead-lettered",
        registry=_registry,
    )

    QUEUE_TASK_DURATION_SECONDS = Histogram(
        "angavu_queue_task_duration_seconds",
        "Task execution duration in seconds",
        ["task_type", "priority"],
        buckets=[0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 300.0],
        registry=_registry,
    )

    QUEUE_WORKERS_ACTIVE = Gauge(
        "angavu_queue_workers_active",
        "Number of active queue workers",
        registry=_registry,
    )

# ── Cache Metrics ──────────────────────────────────────────────────

if PROMETHEUS_AVAILABLE:
    CACHE_OPERATIONS_TOTAL = Counter(
        "angavu_cache_operations_total",
        "Total cache operations",
        ["operation", "namespace", "result"],
        registry=_registry,
    )

    CACHE_OPERATION_DURATION_SECONDS = Histogram(
        "angavu_cache_operation_duration_seconds",
        "Cache operation duration in seconds",
        ["operation"],
        buckets=[0.0005, 0.001, 0.005, 0.01, 0.025, 0.05, 0.1],
        registry=_registry,
    )

# ── Stream Metrics ─────────────────────────────────────────────────

if PROMETHEUS_AVAILABLE:
    STREAM_MESSAGES_PUBLISHED = Counter(
        "angavu_stream_messages_published_total",
        "Total messages published to Redis Streams",
        ["stream"],
        registry=_registry,
    )

    STREAM_MESSAGES_CONSUMED = Counter(
        "angavu_stream_messages_consumed_total",
        "Total messages consumed from Redis Streams",
        ["stream", "consumer_group"],
        registry=_registry,
    )

    STREAM_DEAD_LETTERS = Counter(
        "angavu_stream_dead_letters_total",
        "Total messages sent to dead letter stream",
        ["stream"],
        registry=_registry,
    )

# ── Agent Loop Improvement Metrics (NEW) ───────────────────────────

if PROMETHEUS_AVAILABLE:
    # Agent cost tracking
    AGENT_TOKENS_INPUT_TOTAL = Counter(
        "angavu_agent_tokens_input_total",
        "Total input tokens consumed per agent",
        ["agent_name", "swarm", "model"],
        registry=_registry,
    )

    AGENT_TOKENS_OUTPUT_TOTAL = Counter(
        "angavu_agent_tokens_output_total",
        "Total output tokens consumed per agent",
        ["agent_name", "swarm", "model"],
        registry=_registry,
    )

    AGENT_COST_USD_TOTAL = Counter(
        "angavu_agent_cost_usd_total",
        "Total cost in USD per agent",
        ["agent_name", "swarm", "domain"],
        registry=_registry,
    )

    SWARM_COST_USD_TOTAL = Counter(
        "angavu_swarm_cost_usd_total",
        "Total cost in USD per swarm",
        ["swarm"],
        registry=_registry,
    )

    DOMAIN_COST_USD_TOTAL = Counter(
        "angavu_domain_cost_usd_total",
        "Total cost in USD per business domain",
        ["domain"],
        registry=_registry,
    )

    COST_RATE_USD_PER_HOUR = Gauge(
        "angavu_cost_rate_usd_per_hour",
        "Current cost rate in USD per hour",
        ["agent_name"],
        registry=_registry,
    )

    BUDGET_UTILIZATION_RATIO = Gauge(
        "angavu_budget_utilization_ratio",
        "Budget utilization ratio (0.0-1.0+)",
        ["scope"],
        registry=_registry,
    )

    # Self-evaluation metrics
    EVALUATION_COST_USD_TOTAL = Counter(
        "angavu_evaluation_cost_usd_total",
        "Cost of self-evaluation loops",
        ["agent_name", "verdict"],
        registry=_registry,
    )

    EVALUATION_TOKENS_TOTAL = Counter(
        "angavu_evaluation_tokens_total",
        "Tokens consumed by self-evaluation",
        ["agent_name"],
        registry=_registry,
    )

    EVALUATION_ITERATIONS_HISTOGRAM = Histogram(
        "angavu_evaluation_iterations",
        "Number of evaluation iterations per agent call",
        ["agent_name"],
        buckets=[1, 2, 3, 4, 5],
        registry=_registry,
    )

    EVALUATION_SCORE_HISTOGRAM = Histogram(
        "angavu_evaluation_score",
        "Evaluation quality scores",
        ["agent_name"],
        buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
        registry=_registry,
    )

    # Circuit breaker governance metrics
    CIRCUIT_STATE_CHANGES_TOTAL = Counter(
        "angavu_circuit_state_changes_total",
        "Total circuit breaker state changes",
        ["agent_name", "from_state", "to_state"],
        registry=_registry,
    )

    CIRCUIT_OPEN_DURATION_SECONDS = Gauge(
        "angavu_circuit_open_duration_seconds",
        "How long a circuit has been open",
        ["agent_name"],
        registry=_registry,
    )

    AGENT_PAUSED_GAUGE = Gauge(
        "angavu_agent_paused",
        "Whether an agent is paused (1) or active (0)",
        ["agent_name"],
        registry=_registry,
    )

    GOVERNANCE_ESCALATIONS_TOTAL = Counter(
        "angavu_governance_escalations_total",
        "Total governance escalations",
        ["agent_name", "severity"],
        registry=_registry,
    )

    # Inference tier metrics
    INFERENCE_LATENCY_SECONDS = Histogram(
        "angavu_inference_latency_seconds",
        "Inference latency by model tier",
        ["tier", "agent_name"],
        buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
        registry=_registry,
    )

    MODEL_FALLBACK_TOTAL = Counter(
        "angavu_model_fallback_total",
        "Number of model fallbacks",
        ["from_model", "to_model", "reason"],
        registry=_registry,
    )


# ── Application Info ───────────────────────────────────────────────

if PROMETHEUS_AVAILABLE:
    APP_INFO = Info(
        "angavu_app",
        "Application information",
        registry=_registry,
    )


# ── Helper Classes ─────────────────────────────────────────────────

class MetricsCollector:
    """
    Central metrics collector for Angavu Intelligence.

    Provides a unified interface for recording metrics from all
    components (HTTP, agents, DB, Redis, queues, cache).

    Usage:
        metrics = MetricsCollector()

        # HTTP
        metrics.record_http_request("GET", "/api/v1/health", 200, 0.05)

        # Agent
        with metrics.measure_agent("intelligence_generator", "IntelligenceGeneratorAgent"):
            result = await agent.execute()

        # Database
        with metrics.measure_db_query("SELECT", "transactions"):
            rows = await db.execute(query)

        # Redis
        with metrics.measure_redis("get"):
            value = await redis.get(key)

        # Cache
        metrics.record_cache_hit("users")
        metrics.record_cache_miss("prices")

        # Queue
        metrics.record_task_enqueued("NORMAL")
        metrics.set_queue_depth("NORMAL", 42)

        # Export
        output = metrics.export()
    """

    def __init__(self):
        self._available = PROMETHEUS_AVAILABLE
        self._logger = logger.bind(component="metrics")

    @property
    def is_available(self) -> bool:
        return self._available

    # ── HTTP Metrics ────────────────────────────────────────────────

    def record_http_request(
        self,
        method: str,
        path: str,
        status_code: int,
        duration_seconds: float,
        request_size: int = 0,
        response_size: int = 0,
    ) -> None:
        """Record an HTTP request."""
        if not self._available:
            return

        HTTP_REQUESTS_TOTAL.labels(
            method=method,
            path=path,
            status_code=str(status_code),
        ).inc()

        HTTP_REQUEST_DURATION_SECONDS.labels(
            method=method,
            path=path,
        ).observe(duration_seconds)

        if request_size > 0:
            HTTP_REQUEST_SIZE_BYTES.labels(
                method=method, path=path,
            ).observe(request_size)

        if response_size > 0:
            HTTP_RESPONSE_SIZE_BYTES.labels(
                method=method, path=path,
            ).observe(response_size)

    @contextmanager
    def measure_http_request(
        self,
        method: str,
        path: str,
    ) -> Generator[None, None, None]:
        """Context manager for measuring HTTP request duration."""
        if not self._available:
            yield
            return

        HTTP_REQUESTS_IN_PROGRESS.labels(method=method, path=path).inc()
        start = time.monotonic()
        try:
            yield
        finally:
            duration = time.monotonic() - start
            HTTP_REQUEST_DURATION_SECONDS.labels(
                method=method, path=path,
            ).observe(duration)
            HTTP_REQUESTS_IN_PROGRESS.labels(method=method, path=path).dec()

    # ── Agent Metrics ───────────────────────────────────────────────

    @contextmanager
    def measure_agent(
        self,
        agent_type: str,
        agent_name: str,
    ) -> Generator[None, None, None]:
        """
        Context manager for measuring agent execution time.

        Usage:
            with metrics.measure_agent("domain", "AgricultureAgent"):
                result = await agent.execute(context)
        """
        if not self._available:
            yield
            return

        start = time.monotonic()
        status = "success"
        try:
            yield
        except Exception:
            status = "error"
            raise
        finally:
            duration = time.monotonic() - start
            AGENT_EXECUTION_DURATION_SECONDS.labels(
                agent_type=agent_type,
                agent_name=agent_name,
            ).observe(duration)
            AGENT_EXECUTIONS_TOTAL.labels(
                agent_type=agent_type,
                agent_name=agent_name,
                status=status,
            ).inc()

    def record_agent_event_published(self, event_type: str, source_agent: str) -> None:
        """Record an event published by an agent."""
        if self._available:
            AGENT_EVENTS_PUBLISHED.labels(
                event_type=event_type,
                source_agent=source_agent,
            ).inc()

    def record_agent_event_consumed(self, event_type: str, consumer_group: str) -> None:
        """Record an event consumed by a consumer group."""
        if self._available:
            AGENT_EVENTS_CONSUMED.labels(
                event_type=event_type,
                consumer_group=consumer_group,
            ).inc()

    # ── Database Metrics ────────────────────────────────────────────

    @contextmanager
    def measure_db_query(
        self,
        query_type: str,
        table: str = "unknown",
    ) -> Generator[None, None, None]:
        """
        Context manager for measuring database query duration.

        Usage:
            with metrics.measure_db_query("SELECT", "transactions"):
                rows = await db.execute(query)
        """
        if not self._available:
            yield
            return

        start = time.monotonic()
        status = "success"
        try:
            yield
        except Exception:
            status = "error"
            raise
        finally:
            duration = time.monotonic() - start
            DB_QUERY_DURATION_SECONDS.labels(
                query_type=query_type,
                table=table,
            ).observe(duration)
            DB_QUERIES_TOTAL.labels(
                query_type=query_type,
                table=table,
                status=status,
            ).inc()

    def update_db_pool_metrics(
        self,
        pool_size: int,
        checked_out: int,
        overflow: int,
    ) -> None:
        """Update database connection pool gauges."""
        if not self._available:
            return
        DB_CONNECTION_POOL_SIZE.set(pool_size)
        DB_CONNECTION_POOL_CHECKED_OUT.set(checked_out)
        DB_CONNECTION_POOL_OVERFLOW.set(overflow)

    # ── Redis Metrics ───────────────────────────────────────────────

    @contextmanager
    def measure_redis(
        self,
        operation: str,
    ) -> Generator[None, None, None]:
        """
        Context manager for measuring Redis operation duration.

        Usage:
            with metrics.measure_redis("get"):
                value = await redis.get(key)
        """
        if not self._available:
            yield
            return

        start = time.monotonic()
        status = "success"
        try:
            yield
        except Exception:
            status = "error"
            raise
        finally:
            duration = time.monotonic() - start
            REDIS_OPERATION_DURATION_SECONDS.labels(
                operation=operation,
            ).observe(duration)
            REDIS_OPERATIONS_TOTAL.labels(
                operation=operation,
                status=status,
            ).inc()

    # ── Queue Metrics ───────────────────────────────────────────────

    def record_task_enqueued(self, priority: str) -> None:
        """Record a task being enqueued."""
        if self._available:
            QUEUE_TASKS_ENQUEUED.labels(priority=priority).inc()

    def record_task_completed(self, priority: str) -> None:
        """Record a task completing."""
        if self._available:
            QUEUE_TASKS_COMPLETED.labels(priority=priority).inc()

    def record_task_failed(self, priority: str) -> None:
        """Record a task failure."""
        if self._available:
            QUEUE_TASKS_FAILED.labels(priority=priority).inc()

    def record_task_dead_lettered(self) -> None:
        """Record a task being dead-lettered."""
        if self._available:
            QUEUE_TASKS_DEAD_LETTERED.inc()

    def set_queue_depth(self, priority: str, depth: int) -> None:
        """Set the current queue depth for a priority level."""
        if self._available:
            QUEUE_DEPTH.labels(priority=priority).set(depth)

    def set_workers_active(self, count: int) -> None:
        """Set the number of active workers."""
        if self._available:
            QUEUE_WORKERS_ACTIVE.set(count)

    @contextmanager
    def measure_task(
        self,
        task_type: str,
        priority: str,
    ) -> Generator[None, None, None]:
        """Context manager for measuring task execution time."""
        if not self._available:
            yield
            return

        start = time.monotonic()
        try:
            yield
        finally:
            duration = time.monotonic() - start
            QUEUE_TASK_DURATION_SECONDS.labels(
                task_type=task_type,
                priority=priority,
            ).observe(duration)

    # ── Cache Metrics ───────────────────────────────────────────────

    def record_cache_hit(self, namespace: str = "default") -> None:
        """Record a cache hit."""
        if self._available:
            CACHE_OPERATIONS_TOTAL.labels(
                operation="get", namespace=namespace, result="hit",
            ).inc()

    def record_cache_miss(self, namespace: str = "default") -> None:
        """Record a cache miss."""
        if self._available:
            CACHE_OPERATIONS_TOTAL.labels(
                operation="get", namespace=namespace, result="miss",
            ).inc()

    def record_cache_set(self, namespace: str = "default") -> None:
        """Record a cache set operation."""
        if self._available:
            CACHE_OPERATIONS_TOTAL.labels(
                operation="set", namespace=namespace, result="ok",
            ).inc()

    def record_cache_delete(self, namespace: str = "default") -> None:
        """Record a cache delete operation."""
        if self._available:
            CACHE_OPERATIONS_TOTAL.labels(
                operation="delete", namespace=namespace, result="ok",
            ).inc()

    @contextmanager
    def measure_cache(self, operation: str) -> Generator[None, None, None]:
        """Context manager for measuring cache operation duration."""
        if not self._available:
            yield
            return

        start = time.monotonic()
        try:
            yield
        finally:
            duration = time.monotonic() - start
            CACHE_OPERATION_DURATION_SECONDS.labels(operation=operation).observe(duration)

    # ── Stream Metrics ──────────────────────────────────────────────

    def record_stream_published(self, stream: str) -> None:
        """Record a message published to a stream."""
        if self._available:
            STREAM_MESSAGES_PUBLISHED.labels(stream=stream).inc()

    def record_stream_consumed(self, stream: str, consumer_group: str) -> None:
        """Record a message consumed from a stream."""
        if self._available:
            STREAM_MESSAGES_CONSUMED.labels(
                stream=stream, consumer_group=consumer_group,
            ).inc()

    def record_stream_dead_letter(self, stream: str) -> None:
        """Record a message dead-lettered from a stream."""
        if self._available:
            STREAM_DEAD_LETTERS.labels(stream=stream).inc()

    # ── Export ──────────────────────────────────────────────────────

    def export(self) -> bytes:
        """
        Export all metrics in Prometheus exposition format.

        Returns bytes suitable for an HTTP response with
        Content-Type: text/plain; version=0.0.4; charset=utf-8
        """
        if not self._available:
            return b"# prometheus_client not installed\n"
        return generate_latest(_registry)

    def get_content_type(self) -> str:
        """Get the Prometheus content type header value."""
        if not self._available:
            return "text/plain"
        return CONTENT_TYPE_LATEST

    def get_summary(self) -> Dict[str, Any]:
        """
        Get a human-readable summary of current metrics.

        Useful for health endpoints and debugging.
        """
        if not self._available:
            return {"status": "prometheus_client_not_installed"}

        return {
            "status": "available",
            "metric_count": len(list(_registry.collect())),
            "content_type": CONTENT_TYPE_LATEST,
        }


# ── FastAPI Integration ────────────────────────────────────────────

def create_metrics_endpoint():
    """
    Create a FastAPI route for the /metrics endpoint.

    Usage in main.py:
        from app.infrastructure.metrics import create_metrics_endpoint
        app = FastAPI()
        create_metrics_endpoint()(app)

    Or as a standalone router:
        from fastapi import APIRouter
        router = APIRouter()
        router.add_api_route("/metrics", metrics_endpoint, methods=["GET"])
    """
    from fastapi import Response

    collector = get_metrics_collector()

    async def metrics_endpoint():
        body = collector.export()
        return Response(
            content=body,
            media_type=collector.get_content_type(),
        )

    return metrics_endpoint


def create_metrics_middleware(app):
    """
    Add Prometheus metrics middleware to a FastAPI application.

    Automatically records request count, duration, and error rate
    for all routes.

    Usage:
        from app.infrastructure.metrics import create_metrics_middleware
        app = FastAPI()
        create_metrics_middleware(app)
    """
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import Response

    collector = get_metrics_collector()

    class MetricsMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            # Skip metrics endpoint to avoid recursion
            if request.url.path == "/metrics":
                return await call_next(request)

            method = request.method
            # Normalize path to avoid high cardinality labels
            path = request.url.path
            # Group API paths: /api/v1/businesses/123 → /api/v1/businesses/{id}
            if path.startswith("/api/"):
                parts = path.split("/")
                if len(parts) > 4:
                    parts[4] = "{id}"
                    path = "/".join(parts)

            start = time.monotonic()
            status_code = 500

            with collector.measure_http_request(method, path):
                try:
                    response = await call_next(request)
                    status_code = response.status_code
                    return response
                except Exception:
                    status_code = 500
                    raise
                finally:
                    duration = time.monotonic() - start
                    collector.record_http_request(
                        method=method,
                        path=path,
                        status_code=status_code,
                        duration_seconds=duration,
                    )

    app.add_middleware(MetricsMiddleware)

    # Add /metrics endpoint
    from fastapi import Response

    @app.get("/metrics", include_in_schema=False)
    async def metrics():
        body = collector.export()
        return Response(
            content=body,
            media_type=collector.get_content_type(),
        )

    logger.info("metrics_middleware_attached")


# ── Singleton ──────────────────────────────────────────────────────

_metrics_collector: Optional[MetricsCollector] = None


def get_metrics_collector() -> MetricsCollector:
    """Get the singleton MetricsCollector."""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector
