"""
Agent Observability — Tracing and performance tracking.

Provides distributed tracing for agent operations, enabling:
- Per-agent performance metrics (latency, error rate, p95)
- Trace visualization for debugging
- Integration with OpenTelemetry
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TraceSpan:
    """A single trace span."""
    trace_id: str
    span_id: str
    agent_name: str
    operation: str
    start_time: float
    end_time: float | None = None
    status: str = "ok"
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_ms(self) -> float:
        if self.end_time is None:
            return 0.0
        return (self.end_time - self.start_time) * 1000


@dataclass
class AgentMetrics:
    """Aggregated metrics for a single agent."""
    total_traces: int = 0
    total_errors: int = 0
    total_duration_ms: float = 0.0
    durations: list[float] = field(default_factory=list)

    @property
    def error_rate(self) -> float:
        return self.total_errors / max(self.total_traces, 1)

    @property
    def avg_duration_ms(self) -> float:
        return self.total_duration_ms / max(self.total_traces, 1)

    @property
    def p95_duration_ms(self) -> float:
        if not self.durations:
            return 0.0
        sorted_d = sorted(self.durations)
        idx = int(len(sorted_d) * 0.95)
        return sorted_d[min(idx, len(sorted_d) - 1)]


class AgentTracer:
    """
    Distributed tracer for agent operations.

    Tracks per-agent performance metrics and stores recent traces
    for debugging and observability.
    """

    def __init__(self, max_traces: int = 1000):
        self._traces: list[TraceSpan] = []
        self._max_traces = max_traces
        self._agent_metrics: dict[str, AgentMetrics] = defaultdict(AgentMetrics)

    def start_trace(
        self,
        agent_name: str,
        operation: str,
        trace_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TraceSpan:
        """Start a new trace span."""
        import uuid
        span = TraceSpan(
            trace_id=trace_id or str(uuid.uuid4()),
            span_id=str(uuid.uuid4()),
            agent_name=agent_name,
            operation=operation,
            start_time=time.time(),
            metadata=metadata or {},
        )
        return span

    def end_trace(self, span: TraceSpan, status: str = "ok") -> None:
        """End a trace span and record metrics."""
        span.end_time = time.time()
        span.status = status

        self._traces.append(span)
        if len(self._traces) > self._max_traces:
            self._traces = self._traces[-self._max_traces // 2:]

        metrics = self._agent_metrics[span.agent_name]
        metrics.total_traces += 1
        metrics.total_duration_ms += span.duration_ms
        metrics.durations.append(span.duration_ms)
        if len(metrics.durations) > 100:
            metrics.durations = metrics.durations[-50:]
        if status == "error":
            metrics.total_errors += 1

    def get_stats(self) -> dict[str, Any]:
        """Return tracer statistics."""
        agents = {}
        for name, m in self._agent_metrics.items():
            agents[name] = {
                "total_traces": m.total_traces,
                "error_rate": round(m.error_rate, 4),
                "avg_duration_ms": round(m.avg_duration_ms, 2),
                "p95_duration_ms": round(m.p95_duration_ms, 2),
            }
        return {
            "total_traces": len(self._traces),
            "agents": agents,
        }

    def get_recent_traces(self, agent_name: str | None = None, limit: int = 20) -> list[dict]:
        """Get recent traces, optionally filtered by agent."""
        traces = self._traces
        if agent_name:
            traces = [t for t in traces if t.agent_name == agent_name]
        return [
            {
                "trace_id": t.trace_id,
                "agent": t.agent_name,
                "operation": t.operation,
                "duration_ms": round(t.duration_ms, 2),
                "status": t.status,
                "timestamp": t.start_time,
            }
            for t in traces[-limit:]
        ]
