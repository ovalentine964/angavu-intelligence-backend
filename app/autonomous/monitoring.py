"""
Agent Performance Monitoring — Track metrics across all autonomous agents.

Monitors:
    - Success rate (target: >95%)
    - Error rate (target: <5%)
    - Cost per task (track and optimize)
    - Escalation rate (target: <5% by month 3)
    - Task latency (p50, p95, p99)
    - Agent availability (uptime)

Integrates with the existing AgentTracer for detailed traces
and EventBus for real-time event flow.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class TaskRecord:
    """Record of a single task execution."""
    task_id: str
    agent_name: str
    task_type: str
    success: bool
    duration_ms: float
    cost_usd: float = 0.0
    error: str | None = None
    escalated: bool = False
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "agent_name": self.agent_name,
            "task_type": self.task_type,
            "success": self.success,
            "duration_ms": round(self.duration_ms, 2),
            "cost_usd": round(self.cost_usd, 4),
            "error": self.error,
            "escalated": self.escalated,
            "timestamp": self.timestamp,
        }


class AgentMonitor:
    """
    Tracks per-agent performance metrics.

    Usage:
        monitor = AgentMonitor()
        monitor.record_task(TaskRecord(...))
        metrics = monitor.get_metrics()
        agent_metrics = monitor.get_agent_metrics("SalesAgent")
    """

    def __init__(self, max_records: int = 10000):
        self._records: list[TaskRecord] = []
        self._max_records = max_records

        # Per-agent aggregations
        self._agent_tasks: dict[str, int] = defaultdict(int)
        self._agent_successes: dict[str, int] = defaultdict(int)
        self._agent_errors: dict[str, int] = defaultdict(int)
        self._agent_escalations: dict[str, int] = defaultdict(int)
        self._agent_costs: dict[str, float] = defaultdict(float)
        self._agent_durations: dict[str, list[float]] = defaultdict(list)
        self._agent_last_active: dict[str, float] = {}

        # Global counters
        self._total_tasks: int = 0
        self._total_successes: int = 0
        self._total_errors: int = 0
        self._total_escalations: int = 0
        self._total_cost: float = 0.0

        # Time-series data (hourly buckets)
        self._hourly_tasks: dict[str, int] = defaultdict(int)      # "YYYY-MM-DD HH" → count
        self._hourly_errors: dict[str, int] = defaultdict(int)
        self._hourly_cost: dict[str, float] = defaultdict(float)

        self._logger = logger.bind(component="agent_monitor")

    def record_task(self, record: TaskRecord) -> None:
        """Record a task execution result."""
        # Ring buffer
        self._records.append(record)
        if len(self._records) > self._max_records:
            self._records = self._records[-self._max_records:]

        agent = record.agent_name
        hour_key = time.strftime("%Y-%m-%d %H", time.localtime(record.timestamp))

        # Update counters
        self._total_tasks += 1
        self._agent_tasks[agent] += 1
        self._agent_last_active[agent] = record.timestamp

        if record.success:
            self._total_successes += 1
            self._agent_successes[agent] += 1
        else:
            self._total_errors += 1
            self._agent_errors[agent] += 1

        if record.escalated:
            self._total_escalations += 1
            self._agent_escalations[agent] += 1

        self._total_cost += record.cost_usd
        self._agent_costs[agent] += record.cost_usd
        self._agent_durations[agent].append(record.duration_ms)

        # Hourly buckets
        self._hourly_tasks[hour_key] += 1
        if not record.success:
            self._hourly_errors[hour_key] += 1
        self._hourly_cost[hour_key] += record.cost_usd

    # ── Global Metrics ──────────────────────────────────────────────

    def get_metrics(self) -> dict[str, Any]:
        """Get global performance metrics."""
        all_durations = [r.duration_ms for r in self._records]
        return {
            "total_tasks": self._total_tasks,
            "total_successes": self._total_successes,
            "total_errors": self._total_errors,
            "success_rate": self._safe_rate(self._total_successes, self._total_tasks),
            "error_rate": self._safe_rate(self._total_errors, self._total_tasks),
            "total_escalations": self._total_escalations,
            "escalation_rate": self._safe_rate(self._total_escalations, self._total_tasks),
            "total_cost_usd": round(self._total_cost, 4),
            "avg_cost_per_task": round(
                self._total_cost / self._total_tasks, 4
            ) if self._total_tasks else 0.0,
            "latency": self._calculate_percentiles(all_durations),
            "active_agents": len(self._agent_tasks),
            "agents": {
                name: self.get_agent_metrics(name)
                for name in self._agent_tasks
            },
        }

    def get_agent_metrics(self, agent_name: str) -> dict[str, Any]:
        """Get metrics for a specific agent."""
        tasks = self._agent_tasks.get(agent_name, 0)
        durations = self._agent_durations.get(agent_name, [])
        last_active = self._agent_last_active.get(agent_name)

        return {
            "agent_name": agent_name,
            "total_tasks": tasks,
            "successes": self._agent_successes.get(agent_name, 0),
            "errors": self._agent_errors.get(agent_name, 0),
            "success_rate": self._safe_rate(
                self._agent_successes.get(agent_name, 0), tasks
            ),
            "error_rate": self._safe_rate(
                self._agent_errors.get(agent_name, 0), tasks
            ),
            "escalations": self._agent_escalations.get(agent_name, 0),
            "escalation_rate": self._safe_rate(
                self._agent_escalations.get(agent_name, 0), tasks
            ),
            "total_cost_usd": round(self._agent_costs.get(agent_name, 0), 4),
            "avg_cost_per_task": round(
                self._agent_costs.get(agent_name, 0) / tasks, 4
            ) if tasks else 0.0,
            "latency": self._calculate_percentiles(durations),
            "last_active": last_active,
            "uptime_seconds": (
                time.time() - last_active if last_active else 0
            ),
        }

    def get_hourly_series(self, hours: int = 24) -> list[dict[str, Any]]:
        """Get hourly time-series data for charting."""
        series = []
        now = time.localtime()
        for h in range(hours - 1, -1, -1):
            t = time.localtime(time.time() - h * 3600)
            key = time.strftime("%Y-%m-%d %H", t)
            series.append({
                "hour": key,
                "tasks": self._hourly_tasks.get(key, 0),
                "errors": self._hourly_errors.get(key, 0),
                "cost_usd": round(self._hourly_cost.get(key, 0), 4),
            })
        return series

    def get_recent_tasks(self, limit: int = 50) -> list[dict[str, Any]]:
        """Get most recent task records."""
        return [r.to_dict() for r in self._records[-limit:]]

    def get_error_summary(self, limit: int = 20) -> list[dict[str, Any]]:
        """Get recent errors with context."""
        errors = [r for r in self._records if not r.success]
        return [
            {
                "task_id": r.task_id,
                "agent_name": r.agent_name,
                "error": r.error,
                "timestamp": r.timestamp,
                "task_type": r.task_type,
            }
            for r in errors[-limit:]
        ]

    # ── Helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _safe_rate(numerator: int, denominator: int) -> float:
        return round(numerator / denominator * 100, 2) if denominator else 0.0

    @staticmethod
    def _calculate_percentiles(durations: list[float]) -> dict[str, float]:
        if not durations:
            return {"p50": 0, "p95": 0, "p99": 0, "avg": 0, "min": 0, "max": 0}
        sorted_d = sorted(durations)
        n = len(sorted_d)
        return {
            "p50": round(sorted_d[int(n * 0.5)], 2),
            "p95": round(sorted_d[int(n * 0.95)], 2) if n >= 20 else round(sorted_d[-1], 2),
            "p99": round(sorted_d[int(n * 0.99)], 2) if n >= 100 else round(sorted_d[-1], 2),
            "avg": round(sum(sorted_d) / n, 2),
            "min": round(sorted_d[0], 2),
            "max": round(sorted_d[-1], 2),
        }
