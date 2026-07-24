"""
Agent Observability — Tracing and performance tracking.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class TraceSpan:
    """A single trace span."""
    name: str
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    attributes: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def finish(self, error: Optional[str] = None):
        self.end_time = time.time()
        self.error = error

    @property
    def duration_ms(self) -> float:
        end = self.end_time or time.time()
        return (end - self.start_time) * 1000


class AgentTracer:
    """
    Distributed tracing for agent operations.

    Tracks per-agent performance metrics: latency, error rates,
    throughput, and P95 latencies.
    """

    def __init__(self):
        self._traces: dict[str, list[TraceSpan]] = defaultdict(list)
        self._active_spans: dict[str, TraceSpan] = {}

    def start_span(self, agent_name: str, operation: str) -> TraceSpan:
        """Start a new trace span."""
        span = TraceSpan(name=f"{agent_name}.{operation}")
        span_key = f"{agent_name}:{id(span)}"
        self._active_spans[span_key] = span
        return span

    def end_span(self, span: TraceSpan, agent_name: str, error: Optional[str] = None):
        """End a trace span and record it."""
        span.finish(error=error)
        self._traces[agent_name].append(span)
        # Trim old traces
        if len(self._traces[agent_name]) > 1000:
            self._traces[agent_name] = self._traces[agent_name][-500:]

    def get_stats(self) -> dict:
        """Get aggregated tracing statistics."""
        agent_stats = {}
        for name, spans in self._traces.items():
            durations = [s.duration_ms for s in spans if s.end_time]
            errors = [s for s in spans if s.error]
            agent_stats[name] = {
                "total_traces": len(spans),
                "error_rate": len(errors) / max(len(spans), 1),
                "avg_duration_ms": sum(durations) / max(len(durations), 1),
                "p95_duration_ms": (
                    sorted(durations)[int(len(durations) * 0.95)]
                    if durations else 0
                ),
            }
        return {"agents": agent_stats}
