"""
Agent Observability — Tracing and metrics for agent decisions.

Logs every agent lifecycle event so you can answer:
    - Which agent was triggered?
    - What context did it receive?
    - What decision did it make?
    - What action did it take?
    - What result did it get?
    - How long did it take?

Output: structured logs (via structlog) + optional in-memory trace store
for API introspection (/api/v1/agents/traces).

This is the Biashara Intelligence equivalent of LangSmith / Phoenix.
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


class TraceStatus(str, Enum):
    STARTED = "started"
    DECIDED = "decided"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AgentTrace:
    """
    A single trace of an agent's lifecycle.

    Captures the full observe → think → act → reflect cycle
    for debugging and performance analysis.
    """
    trace_id: str
    agent_name: str
    status: TraceStatus = TraceStatus.STARTED
    started_at: float = field(default_factory=time.time)
    ended_at: Optional[float] = None
    context: Dict[str, Any] = field(default_factory=dict)
    decision: Optional[Dict[str, Any]] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    duration_ms: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "agent_name": self.agent_name,
            "status": self.status.value,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_ms": self.duration_ms,
            "context": self.context,
            "decision": self.decision,
            "result": self.result,
            "error": self.error,
        }


class AgentTracer:
    """
    Records traces for every agent decision.

    Usage:
        tracer = AgentTracer()

        # Inside agent lifecycle:
        trace_id = tracer.start_trace("TransactionProcessor", context)
        tracer.record_decision(trace_id, decision)
        tracer.record_result(trace_id, result)
        tracer.end_trace(trace_id, success=True)

        # Query traces:
        traces = tracer.get_traces(agent_name="TransactionProcessor", limit=10)
        stats = tracer.get_stats()
    """

    def __init__(self, max_traces: int = 1000):
        self._traces: Dict[str, AgentTrace] = {}         # trace_id → trace
        self._completed: List[AgentTrace] = []            # ring buffer
        self._max_traces = max_traces

        # Per-agent metrics
        self._agent_counts: Dict[str, int] = defaultdict(int)
        self._agent_durations: Dict[str, List[float]] = defaultdict(list)
        self._agent_errors: Dict[str, int] = defaultdict(int)

        self._logger = logger.bind(component="agent_tracer")

    def start_trace(self, agent_name: str, context: Dict[str, Any]) -> str:
        """Begin a new trace for an agent lifecycle."""
        trace_id = uuid.uuid4().hex[:16]
        trace = AgentTrace(
            trace_id=trace_id,
            agent_name=agent_name,
            context=self._sanitize_context(context),
        )
        self._traces[trace_id] = trace

        self._logger.info(
            "trace_started",
            trace_id=trace_id,
            agent=agent_name,
        )
        return trace_id

    def record_decision(self, trace_id: str, decision: Any) -> None:
        """Record the agent's decision (output of think phase)."""
        trace = self._traces.get(trace_id)
        if not trace:
            return

        if hasattr(decision, "__dict__"):
            trace.decision = {
                "action": getattr(decision, "action", None),
                "confidence": getattr(decision, "confidence", None),
                "reasoning": getattr(decision, "reasoning", None),
                "parameters": {
                    k: str(v)[:200] for k, v in
                    getattr(decision, "parameters", {}).items()
                },
            }
        else:
            trace.decision = {"raw": str(decision)[:500]}

        trace.status = TraceStatus.DECIDED

        self._logger.info(
            "trace_decision",
            trace_id=trace_id,
            agent=trace.agent_name,
            action=trace.decision.get("action"),
            confidence=trace.decision.get("confidence"),
        )

    def record_result(self, trace_id: str, result: Any) -> None:
        """Record the agent's result (output of act phase)."""
        trace = self._traces.get(trace_id)
        if not trace:
            return

        if hasattr(result, "__dict__"):
            trace.result = {
                "success": getattr(result, "success", None),
                "duration_ms": getattr(result, "duration_ms", None),
                "error": getattr(result, "error", None),
                "data_summary": str(getattr(result, "data", ""))[:300],
            }
        else:
            trace.result = {"raw": str(result)[:500]}

        self._logger.info(
            "trace_result",
            trace_id=trace_id,
            agent=trace.agent_name,
            success=trace.result.get("success"),
            duration_ms=trace.result.get("duration_ms"),
        )

    def end_trace(
        self,
        trace_id: str,
        success: bool = True,
        error: Optional[str] = None,
    ) -> None:
        """Finalize a trace."""
        trace = self._traces.pop(trace_id, None)
        if not trace:
            return

        trace.ended_at = time.time()
        trace.duration_ms = (trace.ended_at - trace.started_at) * 1000

        if success:
            trace.status = TraceStatus.COMPLETED
        else:
            trace.status = TraceStatus.FAILED
            trace.error = error

        # Update metrics
        agent = trace.agent_name
        self._agent_counts[agent] += 1
        self._agent_durations[agent].append(trace.duration_ms)
        if not success:
            self._agent_errors[agent] += 1

        # Ring buffer
        self._completed.append(trace)
        if len(self._completed) > self._max_traces:
            self._completed = self._completed[-self._max_traces:]

        self._logger.info(
            "trace_completed",
            trace_id=trace_id,
            agent=agent,
            status=trace.status.value,
            duration_ms=round(trace.duration_ms, 2),
            success=success,
        )

    # ── Query API ───────────────────────────────────────────────────

    def get_traces(
        self,
        agent_name: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Get completed traces, optionally filtered by agent."""
        traces = self._completed
        if agent_name:
            traces = [t for t in traces if t.agent_name == agent_name]
        return [t.to_dict() for t in traces[-limit:]]

    def get_active_traces(self) -> List[Dict[str, Any]]:
        """Get traces currently in progress."""
        return [t.to_dict() for t in self._traces.values()]

    def get_stats(self) -> Dict[str, Any]:
        """Get aggregate stats for all agents."""
        stats = {}
        for agent, count in self._agent_counts.items():
            durations = self._agent_durations.get(agent, [])
            errors = self._agent_errors.get(agent, 0)
            stats[agent] = {
                "total_traces": count,
                "error_count": errors,
                "error_rate": round(errors / count, 4) if count else 0,
                "avg_duration_ms": round(sum(durations) / len(durations), 2) if durations else 0,
                "p95_duration_ms": round(
                    sorted(durations)[int(len(durations) * 0.95)] if durations else 0, 2
                ),
                "min_duration_ms": round(min(durations), 2) if durations else 0,
                "max_duration_ms": round(max(durations), 2) if durations else 0,
            }
        return {
            "agents": stats,
            "total_traces": sum(self._agent_counts.values()),
            "active_traces": len(self._traces),
            "completed_traces": len(self._completed),
        }

    # ── Helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _sanitize_context(context: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize context for storage — truncate large values."""
        sanitized = {}
        for k, v in context.items():
            str_v = str(v)
            sanitized[k] = str_v[:500] if len(str_v) > 500 else v
        return sanitized
