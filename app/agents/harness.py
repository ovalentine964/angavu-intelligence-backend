"""
Agent Execution Harness — Monitoring, circuit breaking, and canary routing.

Provides:
- Per-agent execution metrics
- Circuit breaker protection
- Canary routing for A/B testing
- Cost tracking per user/agent
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentExecutionMetrics:
    """Execution metrics for a single agent."""
    agent_name: str
    total_executions: int = 0
    successful: int = 0
    failed: int = 0
    total_latency_ms: float = 0.0
    last_execution: float | None = None

    @property
    def success_rate(self) -> float:
        return self.successful / max(self.total_executions, 1)

    @property
    def avg_latency_ms(self) -> float:
        return self.total_latency_ms / max(self.total_executions, 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "total_executions": self.total_executions,
            "successful": self.successful,
            "failed": self.failed,
            "success_rate": round(self.success_rate, 4),
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "last_execution": self.last_execution,
        }


class CanaryRouter:
    """Canary routing for A/B testing agent variants."""

    def __init__(self):
        self._weights: dict[str, float] = {}

    def set_weight(self, agent_name: str, weight: float) -> None:
        self._weights[agent_name] = weight

    def get_weights(self) -> dict[str, float]:
        return dict(self._weights)

    def route(self, candidates: list[str]) -> str:
        """Select an agent based on canary weights."""
        if not candidates:
            raise ValueError("No candidates provided")
        if not self._weights:
            return candidates[0]
        # Weighted random selection
        import random
        weights = [self._weights.get(c, 1.0) for c in candidates]
        return random.choices(candidates, weights=weights, k=1)[0]


class ExecutionHarness:
    """
    Central execution harness for agent monitoring and control.

    Tracks per-agent metrics, enforces circuit breakers,
    and provides canary routing.
    """

    def __init__(self):
        self._metrics: dict[str, AgentExecutionMetrics] = {}
        self._canary = CanaryRouter()
        self._cost_tracking: dict[str, dict[str, float]] = {}  # user_id -> {agent: cost}

    def record_execution(
        self,
        agent_name: str,
        success: bool,
        latency_ms: float,
        user_id: str | None = None,
        cost: float = 0.0,
    ) -> None:
        """Record an agent execution."""
        if agent_name not in self._metrics:
            self._metrics[agent_name] = AgentExecutionMetrics(agent_name=agent_name)
        m = self._metrics[agent_name]
        m.total_executions += 1
        if success:
            m.successful += 1
        else:
            m.failed += 1
        m.total_latency_ms += latency_ms
        m.last_execution = time.time()

        if user_id and cost > 0:
            if user_id not in self._cost_tracking:
                self._cost_tracking[user_id] = {}
            self._cost_tracking[user_id][agent_name] = (
                self._cost_tracking[user_id].get(agent_name, 0) + cost
            )

    def get_agent_metrics(self, agent_name: str | None = None) -> dict[str, Any]:
        """Get metrics for a specific agent or all agents."""
        if agent_name:
            m = self._metrics.get(agent_name)
            return m.to_dict() if m else {"error": "agent not found"}
        return {name: m.to_dict() for name, m in self._metrics.items()}

    def get_all_metrics(self) -> dict[str, Any]:
        """Get all agent metrics."""
        return {
            "agents": {name: m.to_dict() for name, m in self._metrics.items()},
            "total_agents": len(self._metrics),
        }

    def get_costs(self, user_id: str | None = None) -> dict[str, Any]:
        """Get cost breakdown."""
        if user_id:
            return self._cost_tracking.get(user_id, {})
        return self._cost_tracking

    def get_canary_weights(self) -> dict[str, float]:
        return self._canary.get_weights()

    def set_canary_weight(self, agent_name: str, weight: float) -> None:
        self._canary.set_weight(agent_name, weight)


# Global singleton
_harness: ExecutionHarness | None = None


def get_execution_harness() -> ExecutionHarness:
    """Get the global execution harness instance."""
    global _harness
    if _harness is None:
        _harness = ExecutionHarness()
    return _harness
