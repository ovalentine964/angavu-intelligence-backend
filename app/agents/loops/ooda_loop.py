"""
OODA Loop Agent — Observe-Orient-Decide-Act reasoning loop.

Implements the OODA (Boyd) loop pattern for systematic
decision-making with full cycle tracking and metrics.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.agents.base import BiasharaAgent


@dataclass
class OODACycleRecord:
    """Record of one OODA cycle."""
    cycle_id: int
    observation: dict[str, Any]
    orientation: dict[str, Any]
    decision: dict[str, Any]
    action_result: dict[str, Any]
    duration_ms: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "observation": self.observation,
            "orientation": self.orientation,
            "decision": self.decision,
            "action_result": self.action_result,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp.isoformat(),
        }


class OODAAgent(BiasharaAgent):
    """
    OODA loop agent that wraps a SuperagentEngine.

    Tracks observe-orient-decide-act cycles with timing
    and provides introspection endpoints.
    """

    def __init__(self, name: str = "OODAAgent", superagent: Any = None):
        super().__init__(name=name, description="OODA reasoning loop agent")
        self._superagent = superagent
        self._cycles: list[OODACycleRecord] = []
        self._cycle_count = 0
        self._total_duration_ms = 0.0

    async def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        """Execute an OODA cycle."""
        start = time.time()
        self._cycle_count += 1

        # Delegate to superagent if available
        if self._superagent and hasattr(self._superagent, "process_request"):
            result = await self._superagent.process_request(context)
        else:
            result = {"status": "no_superagent", "cycle_id": self._cycle_count}

        duration_ms = (time.time() - start) * 1000
        self._total_duration_ms += duration_ms

        cycle = OODACycleRecord(
            cycle_id=self._cycle_count,
            observation=context.get("observation", {}),
            orientation=context.get("orientation", {}),
            decision=context.get("decision", {}),
            action_result=result,
            duration_ms=duration_ms,
        )
        self._cycles.append(cycle)
        if len(self._cycles) > 500:
            self._cycles = self._cycles[-250:]

        return result

    def get_recent_cycles(self, limit: int = 20) -> list[dict[str, Any]]:
        """Get recent OODA cycles."""
        return [c.to_dict() for c in self._cycles[-limit:]]

    def get_orientation(self) -> dict[str, Any]:
        """Get the current orientation state."""
        if self._cycles:
            return self._cycles[-1].orientation
        return {"status": "no_cycles_yet"}

    def get_metrics(self) -> dict[str, Any]:
        """Get OODA loop metrics."""
        return {
            "total_cycles": self._cycle_count,
            "avg_cycle_ms": self._total_duration_ms / max(self._cycle_count, 1),
            "decision_velocity": self._total_duration_ms / max(self._cycle_count, 1),
        }

    def get_recent_traces(self, limit: int = 20) -> list[dict[str, Any]]:
        """Get recent reasoning traces (for agent_loops API)."""
        return [c.to_dict() for c in self._cycles[-limit:]]
