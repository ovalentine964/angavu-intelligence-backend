"""
Circuit Breaker — Resilience pattern for external service calls.

States:
    CLOSED   → normal operation, requests pass through
    OPEN     → requests fail fast without calling the service
    HALF_OPEN → limited requests pass through to test recovery

Transitions:
    CLOSED → OPEN:      after `failure_threshold` consecutive failures
    OPEN → HALF_OPEN:   after `recovery_timeout` seconds
    HALF_OPEN → CLOSED: after `success_threshold` consecutive successes
    HALF_OPEN → OPEN:   on any failure

Applied to: Redis Streams, PostgreSQL, ClickHouse, OpenWA

References:
- Release It! (Michael Nygard) — Circuit Breaker pattern
- Martin Fowler's Circuit Breaker article
- Netflix Hystrix (resilience engineering)
"""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, Optional, TypeVar

import structlog

logger = structlog.get_logger(__name__)

T = TypeVar("T")


class CircuitState(str, Enum):
    """Circuit breaker states."""
    CLOSED = "closed"         # Normal — requests pass through
    OPEN = "open"             # Tripped — fail fast
    HALF_OPEN = "half_open"   # Testing — limited requests


@dataclass
class CircuitStats:
    """Statistics for circuit breaker monitoring."""
    name: str
    state: CircuitState
    failure_count: int = 0
    success_count: int = 0
    total_requests: int = 0
    total_failures: int = 0
    total_successes: int = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None
    last_state_change: float = field(default_factory=time.time)
    consecutive_failures: int = 0
    consecutive_successes: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "total_requests": self.total_requests,
            "total_failures": self.total_failures,
            "total_successes": self.total_successes,
            "consecutive_failures": self.consecutive_failures,
            "consecutive_successes": self.consecutive_successes,
            "last_failure_time": self.last_failure_time,
            "last_success_time": self.last_success_time,
            "last_state_change": self.last_state_change,
            "uptime_seconds": round(time.time() - self.last_state_change, 1),
        }


class CircuitBreakerError(Exception):
    """Raised when the circuit breaker is open (fail-fast)."""

    def __init__(self, name: str, retry_after: float):
        self.name = name
        self.retry_after = retry_after
        super().__init__(
            f"Circuit breaker '{name}' is OPEN. "
            f"Retry after {retry_after:.1f}s."
        )


class CircuitBreaker:
    """
    Async circuit breaker for external service calls.

    Usage:
        cb = CircuitBreaker("redis", failure_threshold=5, recovery_timeout=30)

        # Manual usage
        if cb.is_open:
            raise CircuitBreakerError(cb.name, cb.retry_after)
        try:
            result = await some_redis_call()
            cb.record_success()
        except Exception:
            cb.record_failure()
            raise

        # Context manager (preferred)
        async with cb.protect():
            result = await some_redis_call()

        # Decorator
        @cb.wrap
        async def my_redis_call():
            return await redis.get(key)

    Thread-safe: all state mutations are atomic (single-threaded async).
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        success_threshold: int = 3,
        half_open_max_calls: int = 3,
        excluded_exceptions: tuple = (),
    ):
        """
        Args:
            name: Human-readable name (e.g. "redis", "clickhouse")
            failure_threshold: Consecutive failures before opening
            recovery_timeout: Seconds before transitioning to half-open
            success_threshold: Consecutive successes to close from half-open
            half_open_max_calls: Max concurrent calls allowed in half-open
            excluded_exceptions: Exceptions that don't count as failures
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold
        self.half_open_max_calls = half_open_max_calls
        self.excluded_exceptions = excluded_exceptions

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._last_state_change = time.time()
        self._half_open_semaphore: Optional[asyncio.Semaphore] = None

        # Stats
        self._total_requests = 0
        self._total_failures = 0
        self._total_successes = 0
        self._last_success_time: Optional[float] = None

        # Governance hook (injected, feature-flagged)
        self._governance: Any = None  # CircuitBreakerGovernance | None

        self._logger = logger.bind(component="circuit_breaker", name=name)

    @property
    def state(self) -> CircuitState:
        """Get current state, auto-transitioning OPEN → HALF_OPEN if timeout elapsed."""
        if self._state == CircuitState.OPEN:
            if self._last_failure_time and \
               (time.time() - self._last_failure_time) >= self.recovery_timeout:
                self._transition(CircuitState.HALF_OPEN)
        return self._state

    @property
    def is_open(self) -> bool:
        return self.state == CircuitState.OPEN

    @property
    def is_closed(self) -> bool:
        return self.state == CircuitState.CLOSED

    @property
    def is_half_open(self) -> bool:
        return self.state == CircuitState.HALF_OPEN

    @property
    def retry_after(self) -> float:
        """Seconds until the circuit might transition to half-open."""
        if self._state != CircuitState.OPEN or not self._last_failure_time:
            return 0.0
        elapsed = time.time() - self._last_failure_time
        return max(0.0, self.recovery_timeout - elapsed)

    def set_governance(self, governance: Any) -> None:
        """Inject governance hook for state change notifications."""
        self._governance = governance

    def record_success(self) -> None:
        """Record a successful call."""
        self._total_requests += 1
        self._total_successes += 1
        self._success_count += 1
        self._failure_count = 0
        self._last_success_time = time.time()

        if self._state == CircuitState.HALF_OPEN:
            if self._success_count >= self.success_threshold:
                self._transition(CircuitState.CLOSED)

    def record_failure(self) -> None:
        """Record a failed call."""
        self._total_requests += 1
        self._total_failures += 1
        self._failure_count += 1
        self._success_count = 0
        self._last_failure_time = time.time()

        if self._state == CircuitState.CLOSED:
            if self._failure_count >= self.failure_threshold:
                self._transition(CircuitState.OPEN)
        elif self._state == CircuitState.HALF_OPEN:
            # Any failure in half-open → back to open
            self._transition(CircuitState.OPEN)

    def _transition(self, new_state: CircuitState) -> None:
        """Transition to a new state and log it."""
        old_state = self._state
        self._state = new_state
        self._last_state_change = time.time()

        if new_state == CircuitState.HALF_OPEN:
            self._half_open_semaphore = asyncio.Semaphore(self.half_open_max_calls)
        elif new_state == CircuitState.CLOSED:
            self._failure_count = 0
            self._success_count = 0
            self._half_open_semaphore = None
        elif new_state == CircuitState.OPEN:
            self._success_count = 0
            self._half_open_semaphore = None

        self._logger.warning(
            "circuit_state_change",
            old_state=old_state.value,
            new_state=new_state.value,
            failure_count=self._failure_count,
            success_count=self._success_count,
        )

        # Notify governance of state change (feature flag)
        if self._governance:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._governance.on_state_change(
                    agent_name=self.name,
                    old_state=old_state.value,
                    new_state=new_state.value,
                    failure_count=self._failure_count,
                    recovery_timeout_s=self.recovery_timeout,
                ))
            except RuntimeError:
                pass

    @asynccontextmanager
    async def protect(self):
        """
        Context manager that enforces circuit breaker semantics.

        In CLOSED: passes through, records success/failure automatically.
        In OPEN: raises CircuitBreakerError immediately (fail-fast).
        In HALF_OPEN: allows limited calls through to test recovery.

        Usage:
            async with cb.protect():
                result = await some_external_call()
        """
        current_state = self.state

        if current_state == CircuitState.OPEN:
            raise CircuitBreakerError(self.name, self.retry_after)

        if current_state == CircuitState.HALF_OPEN:
            if self._half_open_semaphore is None:
                self._half_open_semaphore = asyncio.Semaphore(self.half_open_max_calls)
            acquired = await self._half_open_semaphore.acquire()
            if not acquired:
                raise CircuitBreakerError(self.name, self.retry_after)

        try:
            yield
            self.record_success()
        except self.excluded_exceptions:
            # Excluded exceptions don't count as failures
            raise
        except Exception:
            self.record_failure()
            raise
        finally:
            if current_state == CircuitState.HALF_OPEN and self._half_open_semaphore:
                try:
                    self._half_open_semaphore.release()
                except (ValueError, RuntimeError):
                    pass

    def wrap(self, fn: Callable[..., Coroutine]) -> Callable[..., Coroutine]:
        """
        Decorator that wraps an async function with circuit breaker protection.

        Usage:
            @cb.wrap
            async def my_redis_call(key: str):
                return await redis.get(key)
        """
        async def wrapper(*args, **kwargs):
            async with self.protect():
                return await fn(*args, **kwargs)
        wrapper.__name__ = getattr(fn, "__name__", "wrapped")
        wrapper.__doc__ = getattr(fn, "__doc__", None)
        return wrapper

    def get_stats(self) -> CircuitStats:
        """Get current circuit breaker statistics."""
        return CircuitStats(
            name=self.name,
            state=self.state,
            failure_count=self._failure_count,
            success_count=self._success_count,
            total_requests=self._total_requests,
            total_failures=self._total_failures,
            total_successes=self._total_successes,
            last_failure_time=self._last_failure_time,
            last_success_time=self._last_success_time,
            last_state_change=self._last_state_change,
            consecutive_failures=self._failure_count,
            consecutive_successes=self._success_count,
        )

    def reset(self) -> None:
        """Manually reset the circuit breaker to closed state."""
        self._transition(CircuitState.CLOSED)
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = None


class CircuitBreakerRegistry:
    """
    Registry of all circuit breakers in the application.

    Provides centralized monitoring and management of all circuit
    breakers across services.

    Usage:
        registry = CircuitBreakerRegistry()
        redis_cb = registry.get_or_create("redis", failure_threshold=5)
        pg_cb = registry.get_or_create("postgresql", failure_threshold=3)

        # Get all stats
        all_stats = registry.get_all_stats()
    """

    def __init__(self):
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._logger = logger.bind(component="circuit_breaker_registry")

    def get_or_create(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        success_threshold: int = 3,
        **kwargs,
    ) -> CircuitBreaker:
        """Get an existing circuit breaker or create a new one."""
        if name not in self._breakers:
            self._breakers[name] = CircuitBreaker(
                name=name,
                failure_threshold=failure_threshold,
                recovery_timeout=recovery_timeout,
                success_threshold=success_threshold,
                **kwargs,
            )
            self._logger.info("circuit_breaker_created", name=name)
        return self._breakers[name]

    def get(self, name: str) -> Optional[CircuitBreaker]:
        """Get a circuit breaker by name."""
        return self._breakers.get(name)

    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get stats for all registered circuit breakers."""
        return {
            name: cb.get_stats().to_dict()
            for name, cb in self._breakers.items()
        }

    def get_open_circuits(self) -> list[str]:
        """Get names of all open (tripped) circuit breakers."""
        return [
            name for name, cb in self._breakers.items()
            if cb.is_open
        ]

    def reset_all(self) -> None:
        """Reset all circuit breakers to closed state."""
        for cb in self._breakers.values():
            cb.reset()

    def reset(self, name: str) -> bool:
        """Reset a specific circuit breaker. Returns True if found."""
        cb = self._breakers.get(name)
        if cb:
            cb.reset()
            return True
        return False


# ── Singleton ──────────────────────────────────────────────────────

_registry: Optional[CircuitBreakerRegistry] = None


def get_circuit_breaker_registry() -> CircuitBreakerRegistry:
    """Get the singleton CircuitBreakerRegistry."""
    global _registry
    if _registry is None:
        _registry = CircuitBreakerRegistry()
    return _registry


def get_circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    recovery_timeout: float = 30.0,
    success_threshold: int = 3,
) -> CircuitBreaker:
    """Convenience function: get or create a circuit breaker."""
    return get_circuit_breaker_registry().get_or_create(
        name=name,
        failure_threshold=failure_threshold,
        recovery_timeout=recovery_timeout,
        success_threshold=success_threshold,
    )
