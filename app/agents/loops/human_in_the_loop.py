"""
Human-in-the-Loop Agent — Escalation and trust management.

Manages trust scores for workers, determines autonomy levels,
and handles escalation requests that require human approval.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.agents.base import AgentResult, BiasharaAgent


class AutonomyLevel(str, Enum):
    """Worker autonomy levels based on trust score."""
    FULL_HUMAN = "full_human"           # 0.0–0.2: System only suggests
    HUMAN_CONFIRMS = "human_confirms"   # 0.2–0.4: System proposes, human approves
    HUMAN_INFORMED = "human_informed"   # 0.4–0.6: System acts, human notified
    HUMAN_OVERRIDE = "human_override"   # 0.6–0.8: System acts, human can override
    FULL_AUTONOMY = "full_autonomy"     # 0.8–1.0: System acts, periodic summary


class EscalationStatus(str, Enum):
    """Status of an escalation request."""
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    MODIFIED = "modified"
    TIMED_OUT = "timed_out"


@dataclass
class Escalation:
    """An escalation request pending human resolution."""
    escalation_id: str
    worker_id: str
    action: dict[str, Any]
    reason: str
    status: EscalationStatus = EscalationStatus.PENDING
    created_at: float = field(default_factory=time.time)
    resolved_at: float | None = None
    human_response: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "escalation_id": self.escalation_id,
            "worker_id": self.worker_id,
            "action": self.action,
            "reason": self.reason,
            "status": self.status.value,
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
        }


@dataclass
class WorkerTrust:
    """Trust tracking for a single worker."""
    worker_id: str
    trust_score: float = 0.5
    total_actions: int = 0
    successful_actions: int = 0
    escalated_actions: int = 0
    last_updated: float = field(default_factory=time.time)


class HumanInTheLoopAgent(BiasharaAgent):
    """
    Human-in-the-Loop agent for trust and escalation management.

    Tracks worker trust scores, determines autonomy levels,
    and manages escalation workflows.
    """

    def __init__(self, name: str = "HumanInTheLoopAgent"):
        super().__init__(name=name, description="Human escalation and trust management")
        self._trust_scores: dict[str, WorkerTrust] = {}
        self._escalations: list[Escalation] = []
        self._total_decisions = 0
        self._escalated_decisions = 0

    def get_trust_score(self, worker_id: str) -> dict[str, Any]:
        """Get trust score for a worker."""
        trust = self._trust_scores.get(worker_id)
        if trust:
            return {
                "worker_id": worker_id,
                "trust_score": trust.trust_score,
                "autonomy_level": self._get_autonomy_level(trust.trust_score),
                "total_actions": trust.total_actions,
            }
        return {"worker_id": worker_id, "trust_score": 0.5, "autonomy_level": "human_informed"}

    def get_all_trust_scores(self) -> list[dict[str, Any]]:
        """Get trust scores for all workers."""
        return [self.get_trust_score(wid) for wid in self._trust_scores]

    def _get_autonomy_level(self, score: float) -> str:
        """Determine autonomy level from trust score."""
        if score < 0.2:
            return AutonomyLevel.FULL_HUMAN.value
        elif score < 0.4:
            return AutonomyLevel.HUMAN_CONFIRMS.value
        elif score < 0.6:
            return AutonomyLevel.HUMAN_INFORMED.value
        elif score < 0.8:
            return AutonomyLevel.HUMAN_OVERRIDE.value
        else:
            return AutonomyLevel.FULL_AUTONOMY.value

    def get_escalation_history(self, limit: int = 50) -> list[dict[str, Any]]:
        """Get escalation history."""
        return [e.to_dict() for e in self._escalations[-limit:]]

    def get_pending_escalations(self) -> list[dict[str, Any]]:
        """Get pending escalation requests."""
        return [e.to_dict() for e in self._escalations if e.status == EscalationStatus.PENDING]

    async def resolve_escalation(
        self,
        escalation_id: str,
        resolution: str,
        human_response: dict[str, Any] | None = None,
    ) -> AgentResult:
        """Resolve a pending escalation."""
        for esc in self._escalations:
            if esc.escalation_id == escalation_id and esc.status == EscalationStatus.PENDING:
                esc.status = EscalationStatus(resolution)
                esc.resolved_at = time.time()
                esc.human_response = human_response

                # Update trust score based on resolution
                trust = self._trust_scores.get(esc.worker_id)
                if trust:
                    if resolution == "accepted":
                        trust.trust_score = min(1.0, trust.trust_score + 0.05)
                    elif resolution == "rejected":
                        trust.trust_score = max(0.0, trust.trust_score - 0.1)
                    trust.last_updated = time.time()

                return AgentResult(success=True, data=esc.to_dict())

        return AgentResult(success=False, error=f"Escalation {escalation_id} not found")

    def get_hitl_stats(self) -> dict[str, Any]:
        """Get HITL statistics."""
        autonomy_dist: dict[str, int] = {}
        for trust in self._trust_scores.values():
            level = self._get_autonomy_level(trust.trust_score)
            autonomy_dist[level] = autonomy_dist.get(level, 0) + 1

        return {
            "total_workers": len(self._trust_scores),
            "total_escalations": len(self._escalations),
            "pending_escalations": sum(1 for e in self._escalations if e.status == EscalationStatus.PENDING),
            "total_decisions": self._total_decisions,
            "escalated_decisions": self._escalated_decisions,
            "autonomy_distribution": autonomy_dist,
        }

    def get_metrics(self) -> dict[str, Any]:
        """Get HITL metrics."""
        return self.get_hitl_stats()
