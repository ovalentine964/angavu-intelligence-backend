"""
Per-phase cognitive loop metrics for Prometheus.

Architecture: arch_backend.md §3.7
"""
import time
from contextlib import contextmanager
from functools import wraps

import structlog
from prometheus_client import Counter, Gauge, Histogram

logger = structlog.get_logger(__name__)

PHASE_LATENCY = Histogram(
    "angavu_phase_latency_seconds",
    "Cognitive loop phase latency in seconds",
    ["phase"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

PHASE_SUCCESS_RATE = Gauge(
    "angavu_phase_success_rate",
    "Cognitive loop phase success rate (0.0-1.0)",
    ["phase"],
)

PHASE_ERRORS = Counter(
    "angavu_phase_errors_total",
    "Total cognitive loop phase errors",
    ["phase"],
)

_phase_totals: dict[str, dict] = {}


def _update_success_rate(phase: str, success: bool):
    if phase not in _phase_totals:
        _phase_totals[phase] = {"success": 0, "total": 0}
    _phase_totals[phase]["total"] += 1
    if success:
        _phase_totals[phase]["success"] += 1
    rate = _phase_totals[phase]["success"] / _phase_totals[phase]["total"]
    PHASE_SUCCESS_RATE.labels(phase=phase).set(rate)
    if _phase_totals[phase]["total"] >= 1000:
        _phase_totals[phase] = {
            "success": _phase_totals[phase]["success"] // 2,
            "total": _phase_totals[phase]["total"] // 2,
        }


@contextmanager
def measure_phase(phase: str):
    start = time.monotonic()
    success = True
    try:
        yield
    except Exception:
        success = False
        PHASE_ERRORS.labels(phase=phase).inc()
        raise
    finally:
        elapsed = time.monotonic() - start
        PHASE_LATENCY.labels(phase=phase).observe(elapsed)
        _update_success_rate(phase, success)
        if elapsed > 1.0:
            logger.warning("slow_phase", phase=phase, duration_s=round(elapsed, 3))


def phase_timer(phase: str):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            with measure_phase(phase):
                return await func(*args, **kwargs)
        return wrapper
    return decorator
