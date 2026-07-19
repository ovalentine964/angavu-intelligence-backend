"""
OODA Loop — Observe-Orient-Decide-Act.

The foundational decision loop from military strategist John Boyd.
Optimized for speed-critical decisions where rapid orientation
and action matter more than deep reasoning.

Use cases for Angavu:
- Price alerts and market change detection
- Real-time risk assessment
- Time-sensitive recommendations
- Rapid market anomaly response

The OODA loop differs from ReAct in that it prioritizes speed
over thoroughness. Where ReAct might spend tokens on detailed
reasoning, OODA orients quickly and acts.

Architecture:
    ┌─────────────┐
    │   OBSERVE   │ ← Gather signals (market data, events, context)
    └──────┬──────┘
           ▼
    ┌─────────────┐
    │   ORIENT    │ ← Contextualize against persistent orientation state
    └──────┬──────┘
           ▼
    ┌─────────────┐
    │   DECIDE    │ ← Choose action (fast heuristic or LLM-assisted)
    └──────┬──────┘
           ▼
    ┌─────────────┐
    │    ACT      │ ← Execute and record outcome
    └──────┬──────┘
           │
           └──→ Update orientation → Loop back to OBSERVE
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog

from app.agents.base import (
    AgentDecision,
    AgentEvent,
    AgentResult,
    BiasharaAgent,
    EventType,
)

logger = structlog.get_logger(__name__)


# ════════════════════════════════════════════════════════════════════
# Data Structures
# ════════════════════════════════════════════════════════════════════


class OrientationAxis(str, Enum):
    """Axes along which the orientation state tracks context."""
    MARKET_TREND = "market_trend"           # up / down / stable
    VOLATILITY = "volatility"               # low / medium / high
    URGENCY = "urgency"                     # low / medium / high / critical
    CONFIDENCE = "confidence"               # 0.0 – 1.0
    RISK_LEVEL = "risk_level"               # low / medium / high
    SENTIMENT = "sentiment"                 # negative / neutral / positive
    SUPPLY_DEMAND = "supply_demand"         # surplus / balanced / shortage


@dataclass
class OrientationState:
    """
    Persistent orientation state that evolves across OODA cycles.

    This is the key differentiator from ReAct: the agent maintains
    a continuously updated mental model of the environment, not
    just a per-event context window.
    """
    state_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    axes: dict[str, float] = field(default_factory=lambda: {
        "market_trend": 0.0,       # -1.0 (bearish) to 1.0 (bullish)
        "volatility": 0.0,         # 0.0 (calm) to 1.0 (volatile)
        "urgency": 0.0,            # 0.0 (routine) to 1.0 (critical)
        "confidence": 0.5,         # 0.0 (uncertain) to 1.0 (certain)
        "risk_level": 0.0,         # 0.0 (safe) to 1.0 (dangerous)
        "sentiment": 0.0,          # -1.0 (negative) to 1.0 (positive)
        "supply_demand": 0.0,      # -1.0 (surplus) to 1.0 (shortage)
    })
    last_updated: float = field(default_factory=time.time)
    cycle_count: int = 0
    drift_history: list[dict[str, float]] = field(default_factory=list)

    def update_axis(self, axis: str, value: float, weight: float = 0.3) -> None:
        """
        Update an orientation axis with exponential moving average.

        Args:
            axis: The axis to update
            value: New observation value (-1.0 to 1.0)
            weight: How much to weight the new observation (0.0-1.0)
        """
        old = self.axes.get(axis, 0.0)
        self.axes[axis] = old * (1 - weight) + value * weight
        self.last_updated = time.time()

    def record_drift(self) -> None:
        """Record current state for drift analysis."""
        self.drift_history.append(dict(self.axes))
        if len(self.drift_history) > 100:
            self.drift_history = self.drift_history[-100:]
        self.cycle_count += 1

    def get_drift(self) -> dict[str, float]:
        """
        Calculate orientation drift since last cycle.

        Returns dict of axis → drift magnitude.
        Large drift = significant environmental change.
        """
        if len(self.drift_history) < 2:
            return {}
        prev = self.drift_history[-2]
        return {
            axis: abs(self.axes[axis] - prev.get(axis, 0.0))
            for axis in self.axes
        }

    def is_volatile(self, threshold: float = 0.5) -> bool:
        """Check if the environment is volatile (large recent drift)."""
        drift = self.get_drift()
        return any(v > threshold for v in drift.values())

    def get_urgency_label(self) -> str:
        """Human-readable urgency label."""
        u = self.axes["urgency"]
        if u > 0.8:
            return "critical"
        elif u > 0.5:
            return "high"
        elif u > 0.2:
            return "medium"
        return "low"

    def to_dict(self) -> dict[str, Any]:
        return {
            "state_id": self.state_id,
            "axes": {k: round(v, 3) for k, v in self.axes.items()},
            "last_updated": self.last_updated,
            "cycle_count": self.cycle_count,
            "urgency_label": self.get_urgency_label(),
            "is_volatile": self.is_volatile(),
        }


@dataclass
class OODACycle:
    """Record of a single OODA cycle."""
    cycle_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    cycle_number: int = 0
    started_at: float = field(default_factory=time.time)
    ended_at: float | None = None

    # Phase timings (ms)
    observe_ms: float = 0.0
    orient_ms: float = 0.0
    decide_ms: float = 0.0
    act_ms: float = 0.0

    # Phase outputs
    observations: dict[str, Any] = field(default_factory=dict)
    orientation_snapshot: dict[str, Any] = field(default_factory=dict)
    decision: dict[str, Any] | None = None
    action_result: dict[str, Any] | None = None

    # Outcome
    success: bool = False
    total_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "cycle_number": self.cycle_number,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "phase_timings_ms": {
                "observe": round(self.observe_ms, 1),
                "orient": round(self.orient_ms, 1),
                "decide": round(self.decide_ms, 1),
                "act": round(self.act_ms, 1),
            },
            "total_ms": round(self.total_ms, 1),
            "success": self.success,
            "observations": self.observations,
            "orientation_snapshot": self.orientation_snapshot,
            "decision": self.decision,
        }


@dataclass
class OODAMetrics:
    """Aggregated OODA loop performance metrics."""
    total_cycles: int = 0
    successful_cycles: int = 0
    failed_cycles: int = 0
    avg_cycle_ms: float = 0.0
    avg_observe_ms: float = 0.0
    avg_orient_ms: float = 0.0
    avg_decide_ms: float = 0.0
    avg_act_ms: float = 0.0
    decision_velocity: float = 0.0  # decisions per second
    orientation_stability: float = 0.0  # 0=chaotic, 1=stable
    escalations: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_cycles": self.total_cycles,
            "success_rate": round(self.successful_cycles / max(1, self.total_cycles), 3),
            "avg_cycle_ms": round(self.avg_cycle_ms, 1),
            "phase_avg_ms": {
                "observe": round(self.avg_observe_ms, 1),
                "orient": round(self.avg_orient_ms, 1),
                "decide": round(self.avg_decide_ms, 1),
                "act": round(self.avg_act_ms, 1),
            },
            "decision_velocity": round(self.decision_velocity, 2),
            "orientation_stability": round(self.orientation_stability, 3),
            "escalations": self.escalations,
        }


# ════════════════════════════════════════════════════════════════════
# OODA Agent
# ════════════════════════════════════════════════════════════════════


class OODAAgent(BiasharaAgent):
    """
    Agent with OODA (Observe-Orient-Decide-Act) loop.

    Optimized for speed-critical decisions. Maintains a persistent
    orientation state that evolves across cycles, enabling rapid
    context-aware decisions without re-deriving context each time.

    Key differences from ReAct:
    - ReAct reasons explicitly (expensive, thorough)
    - OODA orients implicitly (cheap, fast)
    - ReAct is per-task; OODA is continuous
    - ReAct produces reasoning traces; OODA produces cycle metrics

    Usage:
        agent = OODAAgent(
            name="PriceAlert",
            role="Real-time price monitoring",
            capabilities=["price_alerts", "market_signals"],
        )
        # Agent handles events via the standard handle_event interface
        # but internally runs an OODA cycle instead of ReAct reasoning
    """

    def __init__(
        self,
        name: str,
        role: str,
        capabilities: Sequence[str],
        escalation_threshold: float = 0.3,
        max_cycle_ms: float = 500.0,
    ):
        super().__init__(name, role, capabilities)
        self._orientation = OrientationState()
        self._cycle_history: list[OODACycle] = []
        self._max_cycle_history = 200
        self._escalation_threshold = escalation_threshold
        self._max_cycle_ms = max_cycle_ms
        self._cycle_counter = 0
        self._metrics = OODAMetrics()

    @property
    def orientation(self) -> OrientationState:
        """Access the current orientation state."""
        return self._orientation

    async def think(self, context: dict[str, Any]) -> AgentDecision:
        """Make a fast decision based on orientation state."""
        event_data = context.get("event", {})
        event = AgentEvent(
            event_type=EventType(event_data.get("event_type", "agent.health.check")),
            source=event_data.get("source", "unknown"),
            payload=event_data.get("payload", {}),
        )
        observations = await self._observe(event)
        await self._orient(observations)
        return await self._decide(event, observations)

    async def act(self, decision: AgentDecision) -> AgentResult:
        """Execute the decision."""
        return await self._act(decision)

    async def handle_event(self, event: AgentEvent) -> AgentResult:
        """Run an OODA cycle for the incoming event."""
        cycle = OODACycle(cycle_number=self._cycle_counter)
        self._cycle_counter += 1

        try:
            # ── OBSERVE ──
            t0 = time.time()
            observations = await self._observe(event)
            cycle.observe_ms = (time.time() - t0) * 1000
            cycle.observations = {
                k: str(v)[:200] for k, v in observations.items()
            }

            # ── ORIENT ──
            t0 = time.time()
            await self._orient(observations)
            cycle.orient_ms = (time.time() - t0) * 1000
            cycle.orientation_snapshot = self._orientation.to_dict()

            # ── DECIDE ──
            t0 = time.time()
            decision = await self._decide(event, observations)
            cycle.decide_ms = (time.time() - t0) * 1000
            cycle.decision = {
                "action": decision.action,
                "confidence": decision.confidence,
                "reasoning": decision.reasoning[:300],
            }

            # Check if we should escalate to a slower loop
            if decision.confidence < self._escalation_threshold:
                self._metrics.escalations += 1
                self._logger.info(
                    "ooda_escalation",
                    confidence=decision.confidence,
                    threshold=self._escalation_threshold,
                    cycle=cycle.cycle_number,
                )
                return AgentResult(
                    success=False,
                    error="low_confidence_escalation",
                    data={
                        "escalation_reason": "OODA confidence below threshold",
                        "confidence": decision.confidence,
                        "orientation": self._orientation.to_dict(),
                        "observations": cycle.observations,
                    },
                )

            # ── ACT ──
            t0 = time.time()
            result = await self._act(decision)
            cycle.act_ms = (time.time() - t0) * 1000
            cycle.action_result = {
                "success": result.success,
                "data_summary": str(result.data)[:200] if result.data else None,
            }

            # Record cycle
            cycle.ended_at = time.time()
            cycle.total_ms = (cycle.ended_at - cycle.started_at) * 1000
            cycle.success = result.success
            self._record_cycle(cycle)

            # Update orientation based on outcome
            await self._post_act_orient(result)

            return result

        except Exception as exc:
            cycle.ended_at = time.time()
            cycle.total_ms = (cycle.ended_at - cycle.started_at) * 1000
            cycle.success = False
            self._record_cycle(cycle)
            return AgentResult(success=False, error=str(exc))

    # ── Phase implementations ──────────────────────────────────────

    async def _observe(self, event: AgentEvent) -> dict[str, Any]:
        """
        Gather signals from the event and recent context.

        Subclasses should override _extract_observations for
        domain-specific signal extraction.
        """
        observations = {
            "event_type": event.event_type.value if hasattr(event.event_type, 'value') else str(event.event_type),
            "source": event.source,
            "timestamp": event.timestamp,
            "payload_keys": list(event.payload.keys()) if event.payload else [],
        }

        # Add domain-specific observations
        domain_obs = await self._extract_observations(event)
        observations.update(domain_obs)

        # Add recent memory context
        recent = self.memory.recall_recent(3)
        if recent:
            observations["recent_event_types"] = [
                r.get("event_type") for r in recent
            ]

        return observations

    async def _extract_observations(self, event: AgentEvent) -> dict[str, Any]:
        """
        Extract domain-specific observations from the event.

        Subclasses override this for specialized signal extraction.
        Default returns payload data.
        """
        return {"payload": event.payload}

    async def _orient(self, observations: dict[str, Any]) -> None:
        """
        Update orientation state based on new observations.

        This is where the OODA loop maintains its persistent
        mental model. Each observation nudges the orientation
        axes, and the cumulative effect creates a rich context
        that informs fast decisions.

        Subclasses can override _compute_orientation_update for
        domain-specific orientation logic.
        """
        updates = await self._compute_orientation_update(observations)
        for axis, value in updates.items():
            if axis in self._orientation.axes:
                self._orientation.update_axis(axis, value)

        self._orientation.record_drift()

    async def _compute_orientation_update(
        self, observations: dict[str, Any]
    ) -> dict[str, float]:
        """
        Compute orientation axis updates from observations.

        Subclasses override this for domain-specific logic.
        Default: no updates (orientation stays unchanged).
        """
        return {}

    async def _decide(
        self, event: AgentEvent, observations: dict[str, Any]
    ) -> AgentDecision:
        """
        Make a fast decision based on orientation state.

        Subclasses should override _ooda_decide for domain logic.
        """
        return await self._ooda_decide(event, observations)

    async def _ooda_decide(
        self, event: AgentEvent, observations: dict[str, Any]
    ) -> AgentDecision:
        """
        Domain-specific decision logic.

        Args:
            event: The triggering event
            observations: Extracted observations

        Returns:
            AgentDecision with action, parameters, confidence, reasoning
        """
        return AgentDecision(
            action="pass_through",
            parameters={"event_type": event.event_type.value if hasattr(event.event_type, 'value') else str(event.event_type)},
            confidence=0.5,
            reasoning="Default OODA decision — no domain logic implemented",
        )

    async def _act(self, decision: AgentDecision) -> AgentResult:
        """
        Execute the decision.

        Subclasses should override _ooda_act for domain logic.
        """
        return await self._ooda_act(decision)

    async def _ooda_act(self, decision: AgentDecision) -> AgentResult:
        """
        Domain-specific action execution.

        Args:
            decision: The decision to execute

        Returns:
            AgentResult with success status and data
        """
        return AgentResult(
            success=True,
            data={"action": decision.action, "parameters": decision.parameters},
        )

    async def _post_act_orient(self, result: AgentResult) -> None:
        """
        Update orientation based on action outcome.

        This closes the loop: the outcome of the action feeds
        back into orientation for the next cycle.

        Subclasses can override for domain-specific feedback.
        """
        if result.success:
            self._orientation.update_axis("confidence", 1.0, weight=0.1)
        else:
            self._orientation.update_axis("confidence", 0.0, weight=0.15)
            self._orientation.update_axis("risk_level", 0.8, weight=0.2)

    # ── Cycle tracking ─────────────────────────────────────────────

    def _record_cycle(self, cycle: OODACycle) -> None:
        """Record a completed cycle and update metrics."""
        self._cycle_history.append(cycle)
        if len(self._cycle_history) > self._max_cycle_history:
            self._cycle_history = self._cycle_history[-self._max_cycle_history:]

        # Update metrics
        m = self._metrics
        m.total_cycles += 1
        if cycle.success:
            m.successful_cycles += 1
        else:
            m.failed_cycles += 1

        n = m.total_cycles
        m.avg_cycle_ms = m.avg_cycle_ms + (cycle.total_ms - m.avg_cycle_ms) / n
        m.avg_observe_ms = m.avg_observe_ms + (cycle.observe_ms - m.avg_observe_ms) / n
        m.avg_orient_ms = m.avg_orient_ms + (cycle.orient_ms - m.avg_orient_ms) / n
        m.avg_decide_ms = m.avg_decide_ms + (cycle.decide_ms - m.avg_decide_ms) / n
        m.avg_act_ms = m.avg_act_ms + (cycle.act_ms - m.avg_act_ms) / n

        # Decision velocity (decisions per second over last 60s)
        now = time.time()
        recent_cycles = [c for c in self._cycle_history if c.started_at > now - 60]
        if recent_cycles:
            span = now - recent_cycles[0].started_at
            m.decision_velocity = len(recent_cycles) / max(span, 0.001)

        # Orientation stability (inverse of average drift)
        drift = self._orientation.get_drift()
        if drift:
            avg_drift = sum(drift.values()) / len(drift)
            m.orientation_stability = 1.0 - min(1.0, avg_drift * 5)

        self._logger.debug(
            "ooda_cycle_complete",
            cycle_number=cycle.cycle_number,
            total_ms=round(cycle.total_ms, 1),
            success=cycle.success,
            orientation=self._orientation.to_dict(),
        )

    def get_recent_cycles(self, n: int = 10) -> list[dict[str, Any]]:
        """Get recent OODA cycle records."""
        return [c.to_dict() for c in self._cycle_history[-n:]]

    def get_metrics(self) -> dict[str, Any]:
        """Get aggregated OODA performance metrics."""
        return self._metrics.to_dict()

    def get_orientation(self) -> dict[str, Any]:
        """Get current orientation state."""
        return self._orientation.to_dict()

    def get_orientation_drift(self) -> dict[str, float]:
        """Get orientation drift (environmental change magnitude)."""
        return self._orientation.get_drift()

    def get_decision_velocity(self) -> float:
        """Get current decision velocity (decisions per second)."""
        return self._metrics.decision_velocity
