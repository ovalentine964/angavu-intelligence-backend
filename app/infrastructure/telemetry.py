"""
OpenTelemetry Integration — Distributed tracing and metrics for Angavu Intelligence.

Instruments:
- FastAPI (HTTP request/response spans)
- SQLAlchemy (database query spans)
- Redis (cache and stream operation spans)
- Agent execution (custom spans with trace context propagation)

Provides:
- Distributed tracing with W3C TraceContext propagation
- Custom metrics for agent performance
- Span attributes for debugging and filtering
- Graceful degradation when OTel is not installed

Architecture:
    Request → FastAPI span → Agent span → DB span → Redis span
                                    ↓
                              Custom metrics (agent_duration, event_lag, etc.)

Configuration (environment variables):
    OTEL_EXPORTER_OTLP_ENDPOINT  — collector URL (e.g. http://otel-collector:4317)
    OTEL_SERVICE_NAME             — service name (default: angavu-backend)
    OTEL_TRACES_SAMPLER           — sampling strategy (parentbased_always_on)
    OTEL_METRICS_EXPORTER         — metrics exporter (otlp or none)

References:
- OpenTelemetry Python SDK docs
- W3C Trace Context specification
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager, contextmanager
from typing import Any, Dict, Generator, Optional

import structlog

logger = structlog.get_logger(__name__)

# ── OpenTelemetry Imports (graceful degradation) ───────────────────

try:
    from opentelemetry import trace, metrics, baggage, context
    from opentelemetry.sdk.trace import TracerProvider, SpanProcessor
    from opentelemetry.sdk.trace.export import (
        BatchSpanProcessor,
        ConsoleSpanExporter,
    )
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import (
        ConsoleMetricExporter,
        PeriodicExportingMetricReader,
    )
    from opentelemetry.sdk.resources import Resource, SERVICE_NAME
    from opentelemetry.trace.propagation.tracecontext import (
        TraceContextTextMapPropagator,
    )
    from opentelemetry.propagate import set_global_textmap
    from opentelemetry.trace import StatusCode, Status
    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False
    logger.info("opentelemetry_not_installed_telemetry_disabled")

# Optional OTLP exporter (requires opentelemetry-exporter-otlp)
try:
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
        OTLPSpanExporter,
    )
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
        OTLPMetricExporter,
    )
    OTLP_AVAILABLE = True
except ImportError:
    OTLP_AVAILABLE = False

# Optional FastAPI instrumentor
try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    FASTAPI_INSTRUMENTOR_AVAILABLE = True
except ImportError:
    FASTAPI_INSTRUMENTOR_AVAILABLE = False

# Optional SQLAlchemy instrumentor
try:
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    SQLALCHEMY_INSTRUMENTOR_AVAILABLE = True
except ImportError:
    SQLALCHEMY_INSTRUMENTOR_AVAILABLE = False

# Optional Redis instrumentor
try:
    from opentelemetry.instrumentation.redis import RedisInstrumentor
    REDIS_INSTRUMENTOR_AVAILABLE = True
except ImportError:
    REDIS_INSTRUMENTOR_AVAILABLE = False

# Optional HTTPX instrumentor
try:
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    HTTPX_INSTRUMENTOR_AVAILABLE = True
except ImportError:
    HTTPX_INSTRUMENTOR_AVAILABLE = False


# ── Configuration ──────────────────────────────────────────────────

DEFAULT_SERVICE_NAME = "angavu-backend"
DEFAULT_OTLP_ENDPOINT = "http://localhost:4317"


class TelemetryConfig:
    """Telemetry configuration from environment variables."""

    def __init__(
        self,
        service_name: str = DEFAULT_SERVICE_NAME,
        otlp_endpoint: Optional[str] = None,
        enable_console_export: bool = False,
        enable_fastapi: bool = True,
        enable_sqlalchemy: bool = True,
        enable_redis: bool = True,
        enable_httpx: bool = True,
        trace_sample_rate: float = 1.0,
    ):
        import os
        self.service_name = os.getenv("OTEL_SERVICE_NAME", service_name)
        self.otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", otlp_endpoint)
        self.enable_console_export = enable_console_export or os.getenv(
            "OTEL_CONSOLE_EXPORT", ""
        ).lower() in ("true", "1", "yes")
        self.enable_fastapi = enable_fastapi
        self.enable_sqlalchemy = enable_sqlalchemy
        self.enable_redis = enable_redis
        self.enable_httpx = enable_httpx
        self.trace_sample_rate = float(
            os.getenv("OTEL_TRACE_SAMPLE_RATE", str(trace_sample_rate))
        )


# ── Agent-Specific Metrics ─────────────────────────────────────────

class AgentMetricsRecorder:
    """
    Records custom metrics for agent performance.

    Provides high-level metrics not covered by auto-instrumentation:
    - Agent execution duration (per agent type)
    - Event processing lag
    - Circuit breaker state
    - Event bus throughput
    - Agent error rates

    Usage:
        metrics = AgentMetricsRecorder()
        with metrics.agent_execution("IntelligenceGenerator", "generate"):
            result = await agent.execute()
    """

    def __init__(self):
        if not OTEL_AVAILABLE:
            self._meter = None
            return

        self._meter = metrics.get_meter("angavu-agents")

        # Agent execution duration histogram
        self._agent_duration = self._meter.create_histogram(
            name="angavu.agent.execution.duration",
            description="Agent execution duration in seconds",
            unit="s",
        )

        # Agent execution counter
        self._agent_executions = self._meter.create_counter(
            name="angavu.agent.executions.total",
            description="Total agent executions",
        )

        # Agent error counter
        self._agent_errors = self._meter.create_counter(
            name="angavu.agent.errors.total",
            description="Total agent errors",
        )

        # Event bus publish counter
        self._events_published = self._meter.create_counter(
            name="angavu.eventbus.published.total",
            description="Total events published to event bus",
        )

        # Event bus consume counter
        self._events_consumed = self._meter.create_counter(
            name="angavu.eventbus.consumed.total",
            description="Total events consumed from event bus",
        )

        # Event processing lag histogram
        self._event_lag = self._meter.create_histogram(
            name="angavu.eventbus.processing.lag",
            description="Event processing lag (publish → consume) in seconds",
            unit="s",
        )

        # Circuit breaker state gauge
        self._circuit_state = self._meter.create_up_down_counter(
            name="angavu.circuit_breaker.state",
            description="Circuit breaker state (0=closed, 1=open, 2=half_open)",
        )

        # Circuit breaker failures counter
        self._circuit_failures = self._meter.create_counter(
            name="angavu.circuit_breaker.failures.total",
            description="Total circuit breaker recorded failures",
        )

        # Dead letter queue size
        self._dead_letters = self._meter.create_up_down_counter(
            name="angavu.eventbus.dead_letters.total",
            description="Total events moved to dead letter queue",
        )

    @contextmanager
    def agent_execution(
        self,
        agent_name: str,
        phase: str = "full_cycle",
    ) -> Generator[None, None, None]:
        """
        Context manager for measuring agent execution with tracing.

        Usage:
            with metrics.agent_execution("IntelligenceGenerator", "think"):
                decision = await agent.think(context)
        """
        if not OTEL_AVAILABLE or not self._meter:
            yield
            return

        tracer = trace.get_tracer("angavu-agents")
        attributes = {"agent.name": agent_name, "agent.phase": phase}

        with tracer.start_as_current_span(
            f"agent.{agent_name}.{phase}",
            attributes=attributes,
        ) as span:
            start = time.monotonic()
            status = "success"
            try:
                yield
            except Exception as exc:
                status = "error"
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                span.record_exception(exc)
                self._agent_errors.add(1, {**attributes, "error.type": type(exc).__name__})
                raise
            finally:
                duration = time.monotonic() - start
                span.set_attribute("agent.duration_s", duration)
                span.set_attribute("agent.status", status)
                self._agent_duration.record(duration, attributes)
                self._agent_executions.add(1, {**attributes, "status": status})

    def record_event_published(self, event_type: str, source: str) -> None:
        """Record an event publication."""
        if OTEL_AVAILABLE and self._meter:
            self._events_published.add(1, {
                "event.type": event_type,
                "event.source": source,
            })

    def record_event_consumed(
        self,
        event_type: str,
        consumer: str,
        lag_seconds: float = 0.0,
    ) -> None:
        """Record an event consumption with optional lag."""
        if OTEL_AVAILABLE and self._meter:
            attributes = {
                "event.type": event_type,
                "event.consumer": consumer,
            }
            self._events_consumed.add(1, attributes)
            if lag_seconds > 0:
                self._event_lag.record(lag_seconds, attributes)

    def record_circuit_breaker_state(
        self,
        name: str,
        state: str,
    ) -> None:
        """Record circuit breaker state change."""
        if OTEL_AVAILABLE and self._meter:
            state_value = {"closed": 0, "open": 1, "half_open": 2}.get(state, 0)
            self._circuit_state.add(state_value, {"circuit.name": name, "circuit.state": state})

    def record_circuit_breaker_failure(self, name: str) -> None:
        """Record a circuit breaker failure."""
        if OTEL_AVAILABLE and self._meter:
            self._circuit_failures.add(1, {"circuit.name": name})

    def record_dead_letter(self, stream: str, reason: str) -> None:
        """Record a dead letter event."""
        if OTEL_AVAILABLE and self._meter:
            self._dead_letters.add(1, {"stream": stream, "reason": reason})


# ── Telemetry Manager ──────────────────────────────────────────────

class TelemetryManager:
    """
    Central manager for OpenTelemetry setup and lifecycle.

    Initializes tracing and metrics providers, instruments libraries,
    and provides access to tracers and meters.

    Usage:
        telemetry = TelemetryManager()
        telemetry.setup()

        # Get a tracer for custom spans
        tracer = telemetry.get_tracer("my-component")
        with tracer.start_as_current_span("my-operation"):
            ...

        # Access agent metrics
        telemetry.agent_metrics.record_event_published("txn.processed", "TxnProcessor")

        # Instrument FastAPI app
        telemetry.instrument_app(app)

        # Shutdown
        telemetry.shutdown()
    """

    def __init__(self, config: Optional[TelemetryConfig] = None):
        self._config = config or TelemetryConfig()
        self._tracer_provider: Optional[TracerProvider] = None
        self._meter_provider: Optional[MeterProvider] = None
        self._agent_metrics: Optional[AgentMetricsRecorder] = None
        self._setup = False

        self._logger = logger.bind(component="telemetry")

    def setup(self) -> None:
        """
        Initialize OpenTelemetry providers and instrumentors.

        Call once at application startup. Safe to call multiple times
        (idempotent).
        """
        if self._setup:
            return

        if not OTEL_AVAILABLE:
            self._logger.info("telemetry_setup_skipped_no_opentelemetry")
            return

        # Create resource with service info
        resource = Resource.create({
            SERVICE_NAME: self._config.service_name,
            "service.version": "0.1.0",
            "deployment.environment": self._config.service_name,
        })

        # ── Tracing ────────────────────────────────────────────────
        self._tracer_provider = TracerProvider(resource=resource)

        # Add span processors
        if self._config.otlp_endpoint and OTLP_AVAILABLE:
            otlp_exporter = OTLPSpanExporter(
                endpoint=self._config.otlp_endpoint,
                insecure=True,
            )
            self._tracer_provider.add_span_processor(
                BatchSpanProcessor(otlp_exporter)
            )
            self._logger.info("otlp_trace_exporter_enabled", endpoint=self._config.otlp_endpoint)

        if self._config.enable_console_export:
            self._tracer_provider.add_span_processor(
                BatchSpanProcessor(ConsoleSpanExporter())
            )

        trace.set_tracer_provider(self._tracer_provider)

        # Set W3C TraceContext propagator for cross-service trace context
        set_global_textmap(TraceContextTextMapPropagator())

        # ── Metrics ────────────────────────────────────────────────
        metric_readers = []

        if self._config.otlp_endpoint and OTLP_AVAILABLE:
            otlp_metric_exporter = OTLPMetricExporter(
                endpoint=self._config.otlp_endpoint,
                insecure=True,
            )
            metric_readers.append(
                PeriodicExportingMetricReader(otlp_metric_exporter, export_interval_millis=30000)
            )

        if self._config.enable_console_export:
            metric_readers.append(
                PeriodicExportingMetricReader(ConsoleMetricExporter(), export_interval_millis=60000)
            )

        if metric_readers:
            self._meter_provider = MeterProvider(
                resource=resource,
                metric_readers=metric_readers,
            )
            metrics.set_meter_provider(self._meter_provider)

        # ── Agent Metrics ──────────────────────────────────────────
        self._agent_metrics = AgentMetricsRecorder()

        self._setup = True
        self._logger.info(
            "telemetry_initialized",
            service=self._config.service_name,
            otlp_endpoint=self._config.otlp_endpoint,
            console_export=self._config.enable_console_export,
        )

    def instrument_app(self, app) -> None:
        """Instrument a FastAPI application."""
        if not self._setup or not OTEL_AVAILABLE:
            return

        if self._config.enable_fastapi and FASTAPI_INSTRUMENTOR_AVAILABLE:
            FastAPIInstrumentor.instrument_app(app)
            self._logger.info("fastapi_instrumented")

    def instrument_sqlalchemy(self, engine) -> None:
        """Instrument a SQLAlchemy engine."""
        if not self._setup or not OTEL_AVAILABLE:
            return

        if self._config.enable_sqlalchemy and SQLALCHEMY_INSTRUMENTOR_AVAILABLE:
            SQLAlchemyInstrumentor().instrument(engine=engine)
            self._logger.info("sqlalchemy_instrumented")

    def instrument_redis(self) -> None:
        """Instrument Redis client libraries."""
        if not self._setup or not OTEL_AVAILABLE:
            return

        if self._config.enable_redis and REDIS_INSTRUMENTOR_AVAILABLE:
            RedisInstrumentor().instrument()
            self._logger.info("redis_instrumented")

    def instrument_httpx(self) -> None:
        """Instrument HTTPX client."""
        if not self._setup or not OTEL_AVAILABLE:
            return

        if self._config.enable_httpx and HTTPX_INSTRUMENTOR_AVAILABLE:
            HTTPXClientInstrumentor().instrument()
            self._logger.info("httpx_instrumented")

    def get_tracer(self, name: str) -> Any:
        """Get a tracer for the given component name."""
        if not OTEL_AVAILABLE:
            return _NoopTracer()
        return trace.get_tracer(name)

    @property
    def agent_metrics(self) -> Optional[AgentMetricsRecorder]:
        """Access agent-specific metrics recorder."""
        return self._agent_metrics

    def get_trace_context(self) -> Dict[str, str]:
        """
        Get current trace context as a dictionary for propagation.

        Used to propagate trace context across agents via event bus
        metadata.
        """
        if not OTEL_AVAILABLE:
            return {}
        carrier: Dict[str, str] = {}
        TraceContextTextMapPropagator().inject(carrier)
        return carrier

    def inject_trace_context(self, carrier: Dict[str, str]) -> None:
        """Inject current trace context into a carrier dict."""
        if OTEL_AVAILABLE:
            TraceContextTextMapPropagator().inject(carrier)

    def extract_trace_context(self, carrier: Dict[str, str]) -> Optional[context.Context]:
        """
        Extract trace context from a carrier dict.

        Returns a Context object that can be attached to the current
        execution context.
        """
        if not OTEL_AVAILABLE:
            return None
        return TraceContextTextMapPropagator().extract(carrier)

    def shutdown(self) -> None:
        """Flush and shut down telemetry providers."""
        if self._tracer_provider:
            try:
                self._tracer_provider.shutdown()
            except Exception as exc:
                self._logger.warning("tracer_shutdown_error", error=str(exc))

        if self._meter_provider:
            try:
                self._meter_provider.shutdown()
            except Exception as exc:
                self._logger.warning("meter_shutdown_error", error=str(exc))

        self._setup = False
        self._logger.info("telemetry_shutdown")


class _NoopTracer:
    """No-op tracer when OpenTelemetry is not available."""

    @contextmanager
    def start_as_current_span(self, name: str, **kwargs):
        yield _NoopSpan()


class _NoopSpan:
    """No-op span when OpenTelemetry is not available."""

    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def set_status(self, status: Any, description: str = "") -> None:
        pass

    def record_exception(self, exc: Exception) -> None:
        pass

    def add_event(self, name: str, attributes: Dict[str, Any] = None) -> None:
        pass


# ── Singleton ──────────────────────────────────────────────────────

_telemetry_manager: Optional[TelemetryManager] = None


def get_telemetry_manager() -> TelemetryManager:
    """Get the singleton TelemetryManager."""
    global _telemetry_manager
    if _telemetry_manager is None:
        _telemetry_manager = TelemetryManager()
    return _telemetry_manager
