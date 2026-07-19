"""
Human-in-the-Loop (HITL) — Progressive Autonomy & Escalation Patterns.

Implements trust-building architecture where agents earn increasing
autonomy based on demonstrated reliability. Based on Stanford's
Three-Pillar Model (Transparency, Accountability, Trustworthiness)
and Microsoft's defense-in-depth framework.

Not just an error handler — HITL is the trust bridge between
AI agents and informal workers who are new to AI.

Progressive Autonomy Levels:
    Level 0 — Full Human:       System observes and suggests only
    Level 1 — Human Confirms:   System proposes, human approves each action
    Level 2 — Human Informed:   System acts, human is notified
    Level 3 — Human Override:   System autonomous, human can override
    Level 4 — Full Autonomy:    System autonomous, periodic human review

Escalation Triggers:
    - Financial threshold exceeded
    - Novel/unseen situation
    - Agent confidence below threshold
    - Consecutive failures
    - Worker preference
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog

from app.agents.base import (
    AgentDecision,
    AgentEvent,
    AgentResult,
    BiasharaAgent,
)

logger = structlog.get_logger(__name__)


# ════════════════════════════════════════════════════════════════════
# Data Structures
# ════════════════════════════════════════════════════════════════════


class AutonomyLevel(int, Enum):
    """Progressive autonomy levels."""
    FULL_HUMAN = 0          # System suggests only
    HUMAN_CONFIRMS = 1      # System proposes, human approves
    HUMAN_INFORMED = 2      # System acts, human notified
    HUMAN_OVERRIDE = 3      # System autonomous, human can override
    FULL_AUTONOMY = 4       # System fully autonomous


class EscalationReason(str, Enum):
    """Reasons for escalating to human."""
    FINANCIAL_THRESHOLD = "financial_threshold"
    NOVEL_SITUATION = "novel_situation"
    LOW_CONFIDENCE = "low_confidence"
    CONSECUTIVE_FAILURES = "consecutive_failures"
    WORKER_PREFERENCE = "worker_preference"
    HIGH_RISK = "high_risk"
    REGULATORY = "regulatory"
    EXPLICIT_REQUEST = "explicit_request"


@dataclass
class TrustScore:
    """
    Trust score for a worker-agent relationship.

    Trust is built through consistent, correct recommendations.
    It decays slowly over time and drops on failures.

    Components:
    - accuracy:    How often the agent's recommendations were correct
    - reliability: How consistently the agent performs
    - recency:     How recent the interactions are
    - acceptance:  How often the worker accepts recommendations
    """
    worker_id: str = ""
    accuracy: float = 0.5          # 0.0 – 1.0
    reliability: float = 0.5       # 0.0 – 1.0
    recency: float = 0.5           # 0.0 – 1.0
    acceptance_rate: float = 0.5   # 0.0 – 1.0
    total_interactions: int = 0
    successful_interactions: int = 0
    last_interaction: float = field(default_factory=time.time)
    last_updated: float = field(default_factory=time.time)

    @property
    def overall(self) -> float:
        """Weighted overall trust score."""
        return (
            self.accuracy * 0.35
            + self.reliability * 0.25
            + self.recency * 0.15
            + self.acceptance_rate * 0.25
        )

    @property
    def recommended_autonomy(self) -> AutonomyLevel:
        """Recommended autonomy level based on trust score."""
        s = self.overall
        if s >= 0.9:
            return AutonomyLevel.FULL_AUTONOMY
        elif s >= 0.75:
            return AutonomyLevel.HUMAN_OVERRIDE
        elif s >= 0.6:
            return AutonomyLevel.HUMAN_INFORMED
        elif s >= 0.4:
            return AutonomyLevel.HUMAN_CONFIRMS
        return AutonomyLevel.FULL_HUMAN

    def record_interaction(self, accepted: bool, successful: bool) -> None:
        """Record an interaction outcome."""
        self.total_interactions += 1
        if successful:
            self.successful_interactions += 1

        # Update accuracy (exponential moving average)
        target = 1.0 if successful else 0.0
        self.accuracy = self.accuracy * 0.9 + target * 0.1

        # Update acceptance rate
        acc_target = 1.0 if accepted else 0.0
        self.acceptance_rate = self.acceptance_rate * 0.9 + acc_target * 0.1

        # Update reliability (consistency of accuracy)
        self.reliability = min(1.0, self.reliability + 0.02) if successful else max(0.0, self.reliability - 0.05)

        # Update recency
        self.recency = 1.0  # fresh interaction
        self.last_interaction = time.time()
        self.last_updated = time.time()

    def decay_recency(self) -> None:
        """Decay recency score based on time since last interaction."""
        hours_since = (time.time() - self.last_interaction) / 3600
        self.recency = max(0.1, 1.0 - hours_since / 168)  # decay over 1 week

    def to_dict(self) -> dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "overall": round(self.overall, 3),
            "accuracy": round(self.accuracy, 3),
            "reliability": round(self.reliability, 3),
            "recency": round(self.recency, 3),
            "acceptance_rate": round(self.acceptance_rate, 3),
            "total_interactions": self.total_interactions,
            "successful_interactions": self.successful_interactions,
            "recommended_autonomy": self.recommended_autonomy.name,
        }


@dataclass
class EscalationRecord:
    """Record of an escalation to human."""
    escalation_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    worker_id: str = ""
    reason: EscalationReason = EscalationReason.LOW_CONFIDENCE
    agent_name: str = ""
    action_proposed: str = ""
    confidence: float = 0.0
    financial_amount: float | None = None
    context: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    resolved: bool = False
    resolution: str = ""        # "accepted" | "rejected" | "modified" | "timeout"
    resolution_time_ms: float = 0.0
    human_response: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "escalation_id": self.escalation_id,
            "worker_id": self.worker_id,
            "reason": self.reason.value,
            "agent_name": self.agent_name,
            "action_proposed": self.action_proposed[:200],
            "confidence": round(self.confidence, 3),
            "financial_amount": self.financial_amount,
            "resolved": self.resolved,
            "resolution": self.resolution,
            "resolution_time_ms": round(self.resolution_time_ms, 1),
            "timestamp": self.timestamp,
        }


@dataclass
class HITLMetrics:
    """Aggregated HITL performance metrics."""
    total_decisions: int = 0
    autonomous_decisions: int = 0
    escalated_decisions: int = 0
    accepted_escalations: int = 0
    rejected_escalations: int = 0
    modified_escalations: int = 0
    avg_resolution_time_ms: float = 0.0
    autonomy_distribution: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_decisions": self.total_decisions,
            "autonomous_rate": round(
                self.autonomous_decisions / max(1, self.total_decisions), 3
            ),
            "escalation_rate": round(
                self.escalated_decisions / max(1, self.total_decisions), 3
            ),
            "escalation_acceptance_rate": round(
                self.accepted_escalations
                / max(1, self.accepted_escalations + self.rejected_escalations),
                3,
            ),
            "avg_resolution_time_ms": round(self.avg_resolution_time_ms, 1),
            "autonomy_distribution": self.autonomy_distribution,
        }


# ════════════════════════════════════════════════════════════════════
# Human-in-the-Loop Agent
# ════════════════════════════════════════════════════════════════════


class HumanInTheLoopAgent(BiasharaAgent):
    """
    Agent wrapper that implements progressive autonomy and
    human escalation patterns.

    Wraps another agent and intercepts its decisions to determine
    whether they should be executed autonomously or escalated
    to a human for approval.

    The key insight: HITL is not about failure handling. It's
    about trust building. Workers new to AI need to see the
    system being right before they'll trust it with more autonomy.

    Usage:
        # Wrap an existing agent
        pricing_agent = OODAAgent(name="Pricing", ...)
        hitl_agent = HumanInTheLoopAgent(
            wrapped_agent=pricing_agent,
            worker_id="worker_123",
            financial_threshold=10000.0,  # KSh 10,000
            confidence_threshold=0.7,
        )

        # Decisions are automatically routed
        result = await hitl_agent.handle_event(event)
    """

    def __init__(
        self,
        wrapped_agent: BiasharaAgent,
        worker_id: str,
        initial_autonomy: AutonomyLevel = AutonomyLevel.HUMAN_CONFIRMS,
        financial_threshold: float = 10000.0,
        confidence_threshold: float = 0.7,
        max_consecutive_failures: int = 3,
        escalation_timeout_s: float = 300.0,  # 5 minutes
    ):
        super().__init__(
            name=f"HITL:{wrapped_agent.name}",
            role=f"Human oversight for {wrapped_agent.name}",
            capabilities=list(wrapped_agent.capabilities) + [
                "escalation",
                "trust_tracking",
                "progressive_autonomy",
            ],
        )
        self._wrapped = wrapped_agent
        self._worker_id = worker_id
        self._autonomy_level = initial_autonomy
        self._trust_score = TrustScore(worker_id=worker_id)
        self._financial_threshold = financial_threshold
        self._confidence_threshold = confidence_threshold
        self._max_consecutive_failures = max_consecutive_failures
        self._escalation_timeout = escalation_timeout_s

        # Tracking
        self._consecutive_failures = 0
        self._escalations: list[EscalationRecord] = []
        self._max_escalation_history = 500
        self._metrics = HITLMetrics()
        self._novel_contexts: set = set()

    @property
    def autonomy_level(self) -> AutonomyLevel:
        return self._autonomy_level

    @property
    def trust_score(self) -> TrustScore:
        return self._trust_score

    async def think(self, context: dict[str, Any]) -> AgentDecision:
        """Delegate thinking to wrapped agent."""
        return await self._wrapped.think(context)

    async def act(self, decision: AgentDecision) -> AgentResult:
        """Delegate action to wrapped agent with HITL routing."""
        result = await self._wrapped.act(decision)
        # Track trust
        self._trust_score.record_interaction(accepted=True, successful=result.success)
        return result

    async def handle_event(self, event: AgentEvent) -> AgentResult:
        """
        Handle event with human-in-the-loop routing.

        1. Get decision from wrapped agent
        2. Check if escalation is needed
        3. Either execute autonomously or escalate
        4. Track outcome for trust scoring
        """
        self._metrics.total_decisions += 1

        # Decay trust recency periodically
        self._trust_score.decay_recency()

        # Get the wrapped agent's decision
        try:
            result = await self._wrapped.handle_event(event)
        except Exception as exc:
            # Agent crashed — always escalate
            return await self._escalate(
                event=event,
                reason=EscalationReason.LOW_CONFIDENCE,
                proposed_action=f"Agent error: {str(exc)[:200]}",
                confidence=0.0,
            )

        # Check escalation conditions
        should_escalate, reason = await self._check_escalation(event, result)

        if should_escalate:
            return await self._escalate(
                event=event,
                reason=reason,
                proposed_action=str(result.data)[:300] if result.data else "unknown",
                confidence=0.5,
                result=result,
            )

        # Execute autonomously
        self._metrics.autonomous_decisions += 1
        self._consecutive_failures = 0 if result.success else self._consecutive_failures + 1

        # Track trust
        self._trust_score.record_interaction(accepted=True, successful=result.success)

        # Update autonomy level based on trust
        self._update_autonomy_level()

        # Track autonomy distribution
        level_name = self._autonomy_level.name
        self._metrics.autonomy_distribution[level_name] = (
            self._metrics.autonomy_distribution.get(level_name, 0) + 1
        )

        return result

    async def _check_escalation(
        self, event: AgentEvent, result: AgentResult
    ) -> tuple[bool, EscalationReason | None]:
        """
        Check if this decision should be escalated to human.

        Returns (should_escalate, reason).
        """
        # If autonomy level is FULL_HUMAN or HUMAN_CONFIRMS, always escalate
        if self._autonomy_level == AutonomyLevel.FULL_HUMAN:
            return True, EscalationReason.WORKER_PREFERENCE
        if self._autonomy_level == AutonomyLevel.HUMAN_CONFIRMS:
            return True, EscalationReason.WORKER_PREFERENCE

        # Check financial threshold
        payload = event.payload or {}
        amount = payload.get("amount") or payload.get("financial_amount")
        if amount and float(amount) > self._financial_threshold:
            return True, EscalationReason.FINANCIAL_THRESHOLD

        # Check confidence
        if result.success is False:
            return True, EscalationReason.LOW_CONFIDENCE

        # Check consecutive failures
        if self._consecutive_failures >= self._max_consecutive_failures:
            return True, EscalationReason.CONSECUTIVE_FAILURES

        # Check for novel context
        context_key = self._extract_context_key(event)
        if context_key and context_key not in self._novel_contexts:
            self._novel_contexts.add(context_key)
            if len(self._novel_contexts) > 2:  # First 2 are "learning"
                return True, EscalationReason.NOVEL_SITUATION

        return False, None

    def _extract_context_key(self, event: AgentEvent) -> str | None:
        """Extract a context key for novelty detection."""
        payload = event.payload or {}
        parts = []
        if "market" in payload:
            parts.append(f"market:{payload['market']}")
        if "product_type" in payload:
            parts.append(f"product:{payload['product_type']}")
        if "action" in payload:
            parts.append(f"action:{payload['action']}")
        return "|".join(parts) if parts else None

    async def _escalate(
        self,
        event: AgentEvent,
        reason: EscalationReason,
        proposed_action: str,
        confidence: float,
        result: AgentResult | None = None,
        financial_amount: float | None = None,
    ) -> AgentResult:
        """
        Escalate a decision to the human worker.

        In a real system, this would:
        - Send a notification via WhatsApp/SMS
        - Wait for human response (with timeout)
        - Record the resolution

        For now, we record the escalation and return the
        proposed action for human review.
        """
        record = EscalationRecord(
            worker_id=self._worker_id,
            reason=reason,
            agent_name=self._wrapped.name,
            action_proposed=proposed_action,
            confidence=confidence,
            financial_amount=financial_amount or event.payload.get("amount"),
            context={
                "event_type": event.event_type.value if hasattr(event.event_type, 'value') else str(event.event_type),
                "source": event.source,
                "payload_keys": list(event.payload.keys()) if event.payload else [],
            },
        )

        self._escalations.append(record)
        if len(self._escalations) > self._max_escalation_history:
            self._escalations = self._escalations[-self._max_escalation_history:]

        self._metrics.escalated_decisions += 1

        self._logger.info(
            "escalation_created",
            escalation_id=record.escalation_id,
            reason=reason.value,
            worker=self._worker_id,
            agent=self._wrapped.name,
            autonomy_level=self._autonomy_level.name,
        )

        # In production: send notification and wait for response
        # For now, return escalation result
        return AgentResult(
            success=False,
            error=f"escalated:{reason.value}",
            data={
                "escalation_id": record.escalation_id,
                "reason": reason.value,
                "proposed_action": proposed_action,
                "autonomy_level": self._autonomy_level.name,
                "trust_score": self._trust_score.overall,
                "awaiting_human_input": True,
            },
        )

    async def resolve_escalation(
        self,
        escalation_id: str,
        resolution: str,
        human_response: dict[str, Any] | None = None,
    ) -> AgentResult:
        """
        Resolve a pending escalation with human input.

        Args:
            escalation_id: The escalation to resolve
            resolution: "accepted" | "rejected" | "modified"
            human_response: Optional human feedback/modification
        """
        record = next(
            (e for e in self._escalations if e.escalation_id == escalation_id),
            None,
        )
        if not record:
            return AgentResult(
                success=False,
                error=f"Escalation {escalation_id} not found",
            )

        record.resolved = True
        record.resolution = resolution
        record.resolution_time_ms = (time.time() - record.timestamp) * 1000
        record.human_response = human_response

        # Update metrics
        if resolution == "accepted":
            self._metrics.accepted_escalations += 1
            self._trust_score.record_interaction(accepted=True, successful=True)
            self._consecutive_failures = 0
        elif resolution == "rejected":
            self._metrics.rejected_escalations += 1
            self._trust_score.record_interaction(accepted=False, successful=False)
        elif resolution == "modified":
            self._metrics.modified_escalations += 1
            self._trust_score.record_interaction(accepted=True, successful=True)

        # Update average resolution time
        n = (
            self._metrics.accepted_escalations
            + self._metrics.rejected_escalations
            + self._metrics.modified_escalations
        )
        self._metrics.avg_resolution_time_ms = (
            self._metrics.avg_resolution_time_ms
            + (record.resolution_time_ms - self._metrics.avg_resolution_time_ms) / max(1, n)
        )

        # Update autonomy level
        self._update_autonomy_level()

        self._logger.info(
            "escalation_resolved",
            escalation_id=escalation_id,
            resolution=resolution,
            resolution_time_ms=round(record.resolution_time_ms, 1),
            trust_score=round(self._trust_score.overall, 3),
            new_autonomy=self._autonomy_level.name,
        )

        return AgentResult(
            success=True,
            data={
                "escalation_id": escalation_id,
                "resolution": resolution,
                "trust_score": round(self._trust_score.overall, 3),
                "autonomy_level": self._autonomy_level.name,
            },
        )

    def _update_autonomy_level(self) -> None:
        """
        Update autonomy level based on trust score.

        Uses the trust score's recommended autonomy, but can
        only move one level at a time (gradual progression).
        """
        recommended = self._trust_score.recommended_autonomy
        current = self._autonomy_level

        if recommended > current:
            # Can only go up one level at a time
            self._autonomy_level = AutonomyLevel(current.value + 1)
        elif recommended < current:
            # Can drop multiple levels on trust violation
            self._autonomy_level = recommended

        # Track distribution
        level_name = self._autonomy_level.name
        self._metrics.autonomy_distribution[level_name] = (
            self._metrics.autonomy_distribution.get(level_name, 0) + 1
        )

    def force_autonomy_level(self, level: AutonomyLevel) -> None:
        """Force a specific autonomy level (for testing or worker preference)."""
        self._autonomy_level = level
        self._logger.info(
            "autonomy_forced",
            worker=self._worker_id,
            level=level.name,
        )

    # ── Query methods ──────────────────────────────────────────────

    def get_pending_escalations(self) -> list[dict[str, Any]]:
        """Get unresolved escalations."""
        return [e.to_dict() for e in self._escalations if not e.resolved]

    def get_escalation_history(self, n: int = 20) -> list[dict[str, Any]]:
        """Get recent escalation history."""
        return [e.to_dict() for e in self._escalations[-n:]]

    def get_trust_score(self, worker_id: str | None = None) -> dict[str, Any]:
        """Get current trust score."""
        return self._trust_score.to_dict()

    def get_autonomy_status(self) -> dict[str, Any]:
        """Get current autonomy status."""
        return {
            "worker_id": self._worker_id,
            "current_level": self._autonomy_level.name,
            "current_level_value": self._autonomy_level.value,
            "trust_score": round(self._trust_score.overall, 3),
            "recommended_level": self._trust_score.recommended_autonomy.name,
            "consecutive_failures": self._consecutive_failures,
            "novel_contexts_seen": len(self._novel_contexts),
        }

    def get_metrics(self) -> dict[str, Any]:
        """Get HITL metrics."""
        return self._metrics.to_dict()

    def get_all_trust_scores(self) -> list[dict[str, Any]]:
        """Get trust scores for all tracked workers."""
        return [self._trust_score.to_dict()]

    def get_hitl_stats(self) -> dict[str, Any]:
        """Get overall HITL statistics."""
        metrics = self._metrics.to_dict()
        metrics["total_escalations"] = len(self._escalations)
        metrics["pending_escalations"] = len([e for e in self._escalations if not e.resolved])
        metrics["trust_score"] = round(self._trust_score.overall, 3)
        metrics["autonomy_level"] = self._autonomy_level.name
        return metrics
