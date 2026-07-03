"""
Human-in-the-Loop (HITL) — Feedback collection and integration.

Integrates human feedback into the agent lifecycle:
    1. Agent produces output
    2. If uncertain (confidence < threshold), requests human review
    3. Human provides feedback (correction, approval, preference, constraint)
    4. Feedback is stored in the agent's memory
    5. Future think() calls incorporate past feedback

Approval gates:
    Critical actions (high-value transactions, report delivery)
    can require explicit human approval before execution.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


# ════════════════════════════════════════════════════════════════════
# Data Structures
# ════════════════════════════════════════════════════════════════════


class FeedbackType(str, Enum):
    """Types of human feedback."""
    CORRECTION = "correction"
    APPROVAL = "approval"
    PREFERENCE = "preference"
    CONSTRAINT = "constraint"


class ReviewStatus(str, Enum):
    """Status of a pending review."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMED_OUT = "timed_out"


@dataclass
class HumanFeedback:
    """Feedback from a human user."""
    feedback_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    agent_name: str = ""
    feedback_type: FeedbackType = FeedbackType.APPROVAL
    original_output: Any = None
    corrected_output: Optional[Any] = None
    explanation: str = ""
    confidence: float = 1.0
    timestamp: float = field(default_factory=time.time)
    applied: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feedback_id": self.feedback_id,
            "agent_name": self.agent_name,
            "feedback_type": self.feedback_type.value,
            "original_output": str(self.original_output)[:200],
            "corrected_output": str(self.corrected_output)[:200] if self.corrected_output else None,
            "explanation": self.explanation,
            "confidence": self.confidence,
            "timestamp": self.timestamp,
            "applied": self.applied,
        }


@dataclass
class PendingReview:
    """A review request waiting for human feedback."""
    review_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    agent_name: str = ""
    action: str = ""
    output: Any = None
    context: Dict[str, Any] = field(default_factory=dict)
    requested_at: float = field(default_factory=time.time)
    status: ReviewStatus = ReviewStatus.PENDING
    expires_at: Optional[float] = None
    resolved_at: Optional[float] = None
    resolution: Optional[HumanFeedback] = None

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "review_id": self.review_id,
            "agent_name": self.agent_name,
            "action": self.action,
            "status": self.status.value,
            "requested_at": self.requested_at,
            "expires_at": self.expires_at,
            "is_expired": self.is_expired(),
        }


@dataclass
class ApprovalGate:
    """A gate that requires human approval before an action executes."""
    gate_id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    name: str = ""
    description: str = ""
    action_pattern: str = ""
    timeout_seconds: float = 300.0
    auto_approve_above: float = 0.0   # auto-approve if confidence > this
    enabled: bool = True


# ════════════════════════════════════════════════════════════════════
# HITL Manager
# ════════════════════════════════════════════════════════════════════


class HITLManager:
    """
    Human-in-the-Loop feedback manager.

    Responsibilities:
    - Track when human review is needed (low confidence, repeated errors)
    - Collect and store human feedback (corrections, approvals, preferences)
    - Make past feedback available for agent context injection
    - Manage approval gates for critical actions
    - Track learned constraints from human corrections
    """

    def __init__(
        self,
        confidence_threshold: float = 0.7,
        correction_window: int = 5,
        correction_threshold: int = 3,
        default_gate_timeout: float = 300.0,
    ):
        self._confidence_threshold = confidence_threshold
        self._correction_window = correction_window
        self._correction_threshold = correction_threshold
        self._default_gate_timeout = default_gate_timeout

        self._pending_reviews: Dict[str, PendingReview] = {}
        self._feedback_history: List[HumanFeedback] = []
        self._learned_constraints: List[str] = []
        self._approval_gates: Dict[str, ApprovalGate] = {}

        self._logger = logger.bind(component="hitl_manager")
        self._register_default_gates()

    # ── Approval gates ─────────────────────────────────────────────

    def _register_default_gates(self) -> None:
        """Register default approval gates for critical financial actions."""
        defaults = [
            ApprovalGate(
                name="high_value_report",
                description="Reports involving high-value transactions",
                action_pattern="deliver_report",
                timeout_seconds=600.0,
            ),
            ApprovalGate(
                name="credit_score_override",
                description="Manual override of credit score",
                action_pattern="override_credit",
                timeout_seconds=300.0,
            ),
        ]
        for gate in defaults:
            self._approval_gates[gate.gate_id] = gate

    def register_gate(self, gate: ApprovalGate) -> str:
        """Register a custom approval gate."""
        self._approval_gates[gate.gate_id] = gate
        self._logger.info("approval_gate_registered", gate_id=gate.gate_id, name=gate.name)
        return gate.gate_id

    def remove_gate(self, gate_id: str) -> bool:
        """Remove an approval gate."""
        if gate_id in self._approval_gates:
            del self._approval_gates[gate_id]
            return True
        return False

    def get_gates(self) -> List[Dict[str, Any]]:
        """Get all registered approval gates."""
        return [
            {
                "gate_id": g.gate_id,
                "name": g.name,
                "description": g.description,
                "action_pattern": g.action_pattern,
                "enabled": g.enabled,
            }
            for g in self._approval_gates.values()
        ]

    def check_approval_gate(
        self,
        action: str,
        confidence: float,
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """
        Check if an action requires approval via a gate.

        Returns:
            review_id if approval is needed
            None if no gate matches or gate is disabled/auto-approved
        """
        for gate in self._approval_gates.values():
            if not gate.enabled:
                continue
            if not self._action_matches_gate(action, gate):
                continue

            if gate.auto_approve_above > 0 and confidence > gate.auto_approve_above:
                self._logger.info(
                    "gate_auto_approved",
                    gate=gate.name, action=action, confidence=confidence,
                )
                return None

            review_id = self.request_review(
                agent_name=context.get("agent_name", "unknown") if context else "unknown",
                action=action,
                output={"action": action, "confidence": confidence},
                context=context or {},
                timeout_seconds=gate.timeout_seconds,
            )
            self._logger.info(
                "gate_approval_required",
                gate=gate.name, action=action, review_id=review_id,
            )
            return review_id

        return None

    def _action_matches_gate(self, action: str, gate: ApprovalGate) -> bool:
        return gate.action_pattern.lower() in action.lower()

    # ── Review requests ────────────────────────────────────────────

    def should_request_review(
        self,
        agent_name: str,
        decision_confidence: float,
        output: Any = None,
    ) -> bool:
        """
        Determine if human review is needed.

        Triggers:
        - Confidence below threshold
        - Agent has been corrected frequently recently
        """
        if decision_confidence < self._confidence_threshold:
            return True

        recent_corrections = [
            f for f in self._feedback_history
            if f.agent_name == agent_name
            and f.feedback_type == FeedbackType.CORRECTION
        ]
        if len(recent_corrections) >= self._correction_threshold:
            return True

        return False

    def request_review(
        self,
        agent_name: str,
        action: str,
        output: Any,
        context: Dict[str, Any],
        timeout_seconds: Optional[float] = None,
    ) -> str:
        """Request human review of agent output. Returns review_id."""
        timeout = timeout_seconds or self._default_gate_timeout
        review = PendingReview(
            agent_name=agent_name,
            action=action,
            output=output,
            context=context,
            expires_at=time.time() + timeout,
        )
        self._pending_reviews[review.review_id] = review

        self._logger.info(
            "review_requested",
            review_id=review.review_id,
            agent=agent_name, action=action, timeout=timeout,
        )
        return review.review_id

    def get_pending_reviews(self, agent_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all pending reviews, optionally filtered by agent."""
        reviews = self._pending_reviews.values()
        if agent_name:
            reviews = [r for r in reviews if r.agent_name == agent_name]
        return [
            r.to_dict() for r in reviews
            if r.status == ReviewStatus.PENDING and not r.is_expired()
        ]

    # ── Feedback submission ────────────────────────────────────────

    def submit_feedback(
        self,
        review_id: str,
        feedback_type: FeedbackType,
        corrected_output: Any = None,
        explanation: str = "",
        confidence: float = 1.0,
    ) -> HumanFeedback:
        """Submit human feedback for a review request."""
        review = self._pending_reviews.get(review_id)
        if not review:
            raise ValueError(f"Review {review_id} not found")

        feedback = HumanFeedback(
            agent_name=review.agent_name,
            feedback_type=feedback_type,
            original_output=review.output,
            corrected_output=corrected_output,
            explanation=explanation,
            confidence=confidence,
        )

        self._feedback_history.append(feedback)

        review.status = (
            ReviewStatus.APPROVED if feedback_type == FeedbackType.APPROVAL
            else ReviewStatus.REJECTED
        )
        review.resolved_at = time.time()
        review.resolution = feedback

        if feedback_type == FeedbackType.CORRECTION and explanation:
            self._learned_constraints.append(explanation)
            self._logger.info(
                "constraint_learned",
                agent=review.agent_name,
                constraint=explanation[:100],
            )

        self._logger.info(
            "feedback_submitted",
            review_id=review_id,
            feedback_type=feedback_type.value,
            agent=review.agent_name,
        )
        return feedback

    def submit_direct_feedback(
        self,
        agent_name: str,
        feedback_type: FeedbackType,
        original_output: Any = None,
        corrected_output: Any = None,
        explanation: str = "",
        confidence: float = 1.0,
    ) -> HumanFeedback:
        """Submit feedback directly without a review request."""
        feedback = HumanFeedback(
            agent_name=agent_name,
            feedback_type=feedback_type,
            original_output=original_output,
            corrected_output=corrected_output,
            explanation=explanation,
            confidence=confidence,
        )
        self._feedback_history.append(feedback)

        if feedback_type == FeedbackType.CORRECTION and explanation:
            self._learned_constraints.append(explanation)

        return feedback

    # ── Context injection ──────────────────────────────────────────

    def get_feedback_context(
        self,
        agent_name: str,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Get recent feedback for an agent to inject into context.

        This is how feedback changes behavior: the agent's think()
        call includes past human corrections and preferences.
        """
        relevant = [
            f for f in self._feedback_history
            if f.agent_name == agent_name
        ]
        return [
            {
                "type": f.feedback_type.value,
                "original": str(f.original_output)[:200] if f.original_output else None,
                "corrected": str(f.corrected_output)[:200] if f.corrected_output else None,
                "explanation": f.explanation,
                "timestamp": f.timestamp,
            }
            for f in relevant[-limit:]
        ]

    def get_learned_constraints(self) -> List[str]:
        """Get all learned constraints from human corrections."""
        return list(self._learned_constraints)

    # ── Timeout management ─────────────────────────────────────────

    def check_expired_reviews(self) -> List[PendingReview]:
        """Find and mark expired reviews."""
        expired = []
        for review in self._pending_reviews.values():
            if review.status == ReviewStatus.PENDING and review.is_expired():
                review.status = ReviewStatus.TIMED_OUT
                review.resolved_at = time.time()
                expired.append(review)
        return expired

    # ── Statistics ─────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Get HITL statistics."""
        return {
            "total_feedback": len(self._feedback_history),
            "corrections": sum(
                1 for f in self._feedback_history
                if f.feedback_type == FeedbackType.CORRECTION
            ),
            "approvals": sum(
                1 for f in self._feedback_history
                if f.feedback_type == FeedbackType.APPROVAL
            ),
            "preferences": sum(
                1 for f in self._feedback_history
                if f.feedback_type == FeedbackType.PREFERENCE
            ),
            "constraints": sum(
                1 for f in self._feedback_history
                if f.feedback_type == FeedbackType.CONSTRAINT
            ),
            "pending_reviews": sum(
                1 for r in self._pending_reviews.values()
                if r.status == ReviewStatus.PENDING and not r.is_expired()
            ),
            "expired_reviews": sum(
                1 for r in self._pending_reviews.values()
                if r.status == ReviewStatus.TIMED_OUT
            ),
            "learned_constraints": len(self._learned_constraints),
            "approval_gates": len([g for g in self._approval_gates.values() if g.enabled]),
        }

    def get_feedback_history(
        self,
        agent_name: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Get feedback history, optionally filtered by agent."""
        history = self._feedback_history
        if agent_name:
            history = [f for f in history if f.agent_name == agent_name]
        return [f.to_dict() for f in history[-limit:]]
