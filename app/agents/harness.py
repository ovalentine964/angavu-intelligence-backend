"""
Agent Harness — Execution harness with circuit breakers and canary routing.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)

# Global harness instance
_harness = None


class CanaryRouter:
    """
    Canary router for gradual rollout of agent changes.

    Routes a percentage of traffic to new implementations
    while monitoring for regressions.
    """

    def __init__(self):
        self._weights: dict[str, float] = {}
        self._metrics: dict[str, dict] = defaultdict(lambda: {"requests": 0, "errors": 0})

    def set_weight(self, agent_name: str, weight: float):
        """Set canary weight (0.0 to 1.0) for an agent."""
        self._weights[agent_name] = max(0.0, min(1.0, weight))

    def get_weight(self, agent_name: str) -> float:
        """Get canary weight for an agent."""
        return self._weights.get(agent_name, 1.0)

    def get_weights(self) -> dict:
        """Get all canary weights."""
        return dict(self._weights)

    def record(self, agent_name: str, success: bool):
        """Record a request outcome."""
        self._metrics[agent_name]["requests"] += 1
        if not success:
            self._metrics[agent_name]["errors"] += 1


@dataclass
class CircuitBreaker:
    """Simple circuit breaker for agent execution."""
    name: str
    failure_threshold: int = 5
    recovery_timeout: float = 60.0
    state: str = "closed"
    failure_count: int = 0
    last_failure_time: Optional[float] = None

    def record_success(self):
        self.failure_count = 0
        self.state = "closed"

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = "open"

    def allow_request(self) -> bool:
        if self.state == "closed":
            return True
        if self.last_failure_time and (time.time() - self.last_failure_time) > self.recovery_timeout:
            self.state = "half-open"
            return True
        return False


class ExecutionHarness:
    """
    Execution harness that wraps agent execution with:
    - Circuit breakers per agent
    - Canary routing
    - Cost tracking
    - Performance metrics
    """

    def __init__(self):
        self._circuit_breakers: dict[str, CircuitBreaker] = {}
        self._canary = CanaryRouter()
        self._costs: dict[str, float] = defaultdict(float)
        self._user_costs: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self._metrics: dict[str, dict] = defaultdict(
            lambda: {"requests": 0, "errors": 0, "total_ms": 0}
        )

    def get_circuit_breaker(self, name: str) -> CircuitBreaker:
        if name not in self._circuit_breakers:
            self._circuit_breakers[name] = CircuitBreaker(name=name)
        return self._circuit_breakers[name]

    def get_health(self) -> dict:
        return {
            "agents": {
                name: {
                    "requests": m["requests"],
                    "errors": m["errors"],
                    "avg_ms": m["total_ms"] / max(m["requests"], 1),
                }
                for name, m in self._metrics.items()
            },
            "circuit_breakers": {
                name: {"state": cb.state, "failures": cb.failure_count}
                for name, cb in self._circuit_breakers.items()
            },
            "canary_weights": self._canary.get_weights(),
        }

    def get_agent_metrics(self) -> dict:
        return dict(self._metrics)

    def get_costs(self) -> dict:
        return dict(self._costs)

    def get_user_costs(self, user_id: str) -> dict:
        return dict(self._user_costs.get(user_id, {}))

    def reset_circuit_breaker(self, name: str) -> bool:
        if name in self._circuit_breakers:
            self._circuit_breakers[name].state = "closed"
            self._circuit_breakers[name].failure_count = 0
            return True
        return False


def get_execution_harness() -> ExecutionHarness:
    """Get or create the global execution harness."""
    global _harness
    if _harness is None:
        _harness = ExecutionHarness()
    return _harness
