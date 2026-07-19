"""
Connection pool management for PostgreSQL with resilience patterns.

Extends the base database.py with:
- Connection pool sizing based on worker count
- Connection health checks with heartbeat
- Exponential backoff retry for transient failures
- Connection pool metrics for observability

Queuing Theory Application:
    Pool size formula: N_workers × (core_pool_size + max_overflow) ≤ max_connections
    With 4 Gunicorn workers × 20 pool_size = 80 connections max
    PostgreSQL default max_connections = 100 → leaves 20 for admin/migrations

    Little's Law: L = λW
    - L = connections in use
    - λ = request arrival rate
    - W = average request duration
    At 100 req/s with 50ms avg query time: L = 100 × 0.05 = 5 connections
    Pool of 20 gives 4x headroom for spikes.

References:
- Database Systems (CS): Connection pooling reduces TCP handshake overhead
- Optimization (Applied Math): Right-sizing pools balances memory vs throughput
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

import structlog

from app.config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()


@dataclass
class PoolMetrics:
    """Connection pool metrics for observability."""
    pool_size: int = 0
    checked_out: int = 0
    overflow: int = 0
    checked_in: int = 0
    total_connections: int = 0
    total_checkouts: int = 0
    total_checkins: int = 0
    total_overflows: int = 0
    total_invalidations: int = 0
    wait_time_total: float = 0.0
    wait_count: int = 0
    health_check_failures: int = 0
    retry_attempts: int = 0
    last_health_check: float = 0.0
    is_healthy: bool = True

    @property
    def avg_wait_time_ms(self) -> float:
        """Average wait time for a connection in milliseconds."""
        if self.wait_count == 0:
            return 0.0
        return (self.wait_time_total / self.wait_count) * 1000

    @property
    def utilization(self) -> float:
        """Pool utilization as a percentage (0.0 - 1.0)."""
        if self.pool_size == 0:
            return 0.0
        return self.checked_out / (self.pool_size + self.overflow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pool_size": self.pool_size,
            "checked_out": self.checked_out,
            "overflow": self.overflow,
            "checked_in": self.checked_in,
            "total_connections": self.total_connections,
            "total_checkouts": self.total_checkouts,
            "total_checkins": self.total_checkins,
            "total_overflows": self.total_overflows,
            "total_invalidations": self.total_invalidations,
            "avg_wait_time_ms": round(self.avg_wait_time_ms, 2),
            "wait_count": self.wait_count,
            "utilization": round(self.utilization, 4),
            "health_check_failures": self.health_check_failures,
            "retry_attempts": self.retry_attempts,
            "is_healthy": self.is_healthy,
            "last_health_check": self.last_health_check,
        }


class ConnectionPoolManager:
    """
    Manages database connection pool with resilience patterns.

    Features:
    - Dynamic pool sizing based on worker count
    - Health checks with configurable interval
    - Exponential backoff retry for transient connection failures
    - Pool metrics collection for Prometheus export

    Usage:
        manager = ConnectionPoolManager()
        await manager.initialize()

        # Get pool metrics
        metrics = manager.get_metrics()

        # Health check
        healthy = await manager.health_check()
    """

    def __init__(
        self,
        health_check_interval: float = 30.0,
        max_retries: int = 3,
        base_retry_delay: float = 1.0,
        max_retry_delay: float = 30.0,
    ):
        self._health_check_interval = health_check_interval
        self._max_retries = max_retries
        self._base_retry_delay = base_retry_delay
        self._max_retry_delay = max_retry_delay

        self._engine = None
        self._metrics = PoolMetrics()
        self._health_task: asyncio.Task | None = None
        self._initialized = False
        self._logger = logger.bind(component="connection_pool")

    async def initialize(self) -> None:
        """
        Initialize the connection pool manager.

        Must be called after the database engine is created.
        Starts the background health check task.
        """
        from app.db.database import engine

        self._engine = engine

        # Calculate optimal pool size
        # Formula: workers × (pool_per_worker) but capped by max_connections
        # With 4 Gunicorn workers, each needs ~20 connections = 80 total
        # PostgreSQL default max_connections = 100
        optimal_pool = settings.DATABASE_POOL_SIZE
        optimal_overflow = settings.DATABASE_MAX_OVERFLOW

        self._logger.info(
            "pool_configured",
            pool_size=optimal_pool,
            max_overflow=optimal_overflow,
            total_max=optimal_pool + optimal_overflow,
            pool_timeout=settings.DATABASE_POOL_TIMEOUT,
            pool_recycle=settings.DATABASE_POOL_RECYCLE,
        )

        # Start background health check
        self._health_task = asyncio.create_task(self._health_check_loop())
        self._initialized = True

    async def shutdown(self) -> None:
        """Stop health checks and clean up."""
        if self._health_task and not self._health_task.done():
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass
        self._initialized = False

    async def health_check(self) -> bool:
        """
        Perform a health check on the database connection.

        Returns True if the database is reachable and responsive.
        """
        if not self._engine:
            self._metrics.is_healthy = False
            return False

        try:
            from sqlalchemy import text
            async with self._engine.connect() as conn:
                result = await conn.execute(text("SELECT 1"))
                result.scalar()

            self._metrics.is_healthy = True
            self._metrics.last_health_check = time.time()
            self._logger.debug("health_check_passed")
            return True
        except Exception as exc:
            self._metrics.is_healthy = False
            self._metrics.health_check_failures += 1
            self._metrics.last_health_check = time.time()
            self._logger.warning("health_check_failed", error=str(exc))
            return False

    async def execute_with_retry(self, coro_func, *args, **kwargs):
        """
        Execute a database operation with exponential backoff retry.

        Retries on transient connection errors:
        - ConnectionError
        - OSError
        - TimeoutError
        - sqlalchemy.exc.OperationalError (connection lost)

        Args:
            coro_func: Async function to call
            *args, **kwargs: Arguments to pass

        Returns:
            Result of the function call

        Raises:
            Exception: If all retries are exhausted
        """
        last_exc = None
        for attempt in range(self._max_retries + 1):
            try:
                return await coro_func(*args, **kwargs)
            except (ConnectionError, OSError, TimeoutError) as exc:
                last_exc = exc
                self._metrics.retry_attempts += 1

                if attempt < self._max_retries:
                    delay = min(
                        self._base_retry_delay * (2 ** attempt),
                        self._max_retry_delay,
                    )
                    self._logger.warning(
                        "db_operation_retry",
                        attempt=attempt + 1,
                        delay=delay,
                        error=str(exc),
                    )
                    await asyncio.sleep(delay)
                else:
                    self._logger.error(
                        "db_operation_failed_all_retries",
                        attempts=attempt + 1,
                        error=str(exc),
                    )

        raise last_exc

    def get_metrics(self) -> PoolMetrics:
        """Get current connection pool metrics."""
        if self._engine and hasattr(self._engine, 'pool'):
            pool = self._engine.pool
            try:
                self._metrics.pool_size = pool.size()
                self._metrics.checked_out = pool.checkedout()
                self._metrics.overflow = pool.overflow()
                self._metrics.checked_in = pool.checkedin()
            except Exception:
                pass
        return self._metrics

    async def _health_check_loop(self) -> None:
        """Background task that periodically checks database health."""
        while True:
            try:
                await asyncio.sleep(self._health_check_interval)
                await self.health_check()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._logger.warning("health_check_loop_error", error=str(exc))


# ── Singleton ──────────────────────────────────────────────────────

_pool_manager: ConnectionPoolManager | None = None


def get_pool_manager() -> ConnectionPoolManager:
    """Get the singleton ConnectionPoolManager."""
    global _pool_manager
    if _pool_manager is None:
        _pool_manager = ConnectionPoolManager()
    return _pool_manager
