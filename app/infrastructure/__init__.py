"""
Infrastructure package for Angavu Intelligence backend scalability.

Provides:
- Redis Streams (inter-service communication)
- Connection pool management (database resilience)
- Async task queue (background processing)
- Caching layer (cache-aside pattern)
- Metrics & observability (Prometheus-compatible)
- Enhanced health checks (comprehensive monitoring)
- Circuit breaker (resilience for external services)
- OpenTelemetry (distributed tracing & metrics)
"""

from app.infrastructure.cache import CacheAside, get_cache_aside
from app.infrastructure.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerError,
    CircuitBreakerRegistry,
    CircuitState,
    get_circuit_breaker,
    get_circuit_breaker_registry,
)
from app.infrastructure.connection_pool import ConnectionPoolManager, get_pool_manager
from app.infrastructure.metrics import MetricsCollector, get_metrics_collector
from app.infrastructure.redis_streams import (
    RedisStreamsConsumer,
    RedisStreamsManager,
    RedisStreamsProducer,
    get_streams_manager,
)
from app.infrastructure.task_queue import AsyncTaskQueue, Priority, get_async_task_queue
from app.infrastructure.telemetry import (
    AgentMetricsRecorder,
    TelemetryConfig,
    TelemetryManager,
    get_telemetry_manager,
)

__all__ = [
    # Cache
    "CacheAside",
    "get_cache_aside",
    # Circuit Breaker
    "CircuitBreaker",
    "CircuitBreakerError",
    "CircuitBreakerRegistry",
    "CircuitState",
    "get_circuit_breaker",
    "get_circuit_breaker_registry",
    # Connection Pool
    "ConnectionPoolManager",
    "get_pool_manager",
    # Metrics
    "MetricsCollector",
    "get_metrics_collector",
    # Redis Streams
    "RedisStreamsProducer",
    "RedisStreamsConsumer",
    "RedisStreamsManager",
    "get_streams_manager",
    # Task Queue
    "AsyncTaskQueue",
    "Priority",
    "get_async_task_queue",
    # Telemetry
    "AgentMetricsRecorder",
    "TelemetryConfig",
    "TelemetryManager",
    "get_telemetry_manager",
]
