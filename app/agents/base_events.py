"""
BiasharaAgent — Event & Message Type Definitions.

All event types, agent states, and data transfer objects
that flow through the agent event bus.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


# ════════════════════════════════════════════════════════════════════
# Event & Message Types
# ════════════════════════════════════════════════════════════════════


class EventType(StrEnum):
    """All event types that flow through the event bus."""

    # Data pipeline
    TRANSACTION_RECEIVED = "transaction.received"
    TRANSACTION_PROCESSED = "transaction.processed"
    BATCH_PROCESSED = "batch.processed"

    # Intelligence
    INTELLIGENCE_REQUESTED = "intelligence.requested"
    INTELLIGENCE_GENERATED = "intelligence.generated"
    PRICE_FORECAST_READY = "price.forecast.ready"
    CREDIT_SCORE_READY = "credit.score.ready"
    MARKET_ALERT = "market.alert"

    # Reports
    REPORT_REQUESTED = "report.requested"
    REPORT_GENERATED = "report.generated"
    REPORT_DELIVERED = "report.delivered"

    # Self-evolution
    FEEDBACK_RECEIVED = "feedback.received"
    FEATURE_SPEC_GENERATED = "feature.spec.generated"
    EVOLUTION_CYCLE_COMPLETE = "evolution.cycle.complete"

    # Revenue Operations — Leads
    LEAD_CREATED = "lead.created"
    LEAD_QUALIFIED = "lead.qualified"
    LEAD_REJECTED = "lead.rejected"
    LEAD_ESCALATED = "lead.escalated"

    # Revenue Operations — Content
    CONTENT_REQUESTED = "content.requested"
    CONTENT_GENERATED = "content.generated"
    CONTENT_PUBLISHED = "content.published"

    # Revenue Operations — Invoicing
    INVOICE_DRAFTED = "invoice.drafted"
    INVOICE_SENT = "invoice.sent"
    INVOICE_PAID = "invoice.paid"
    INVOICE_OVERDUE = "invoice.overdue"

    # Revenue Operations — Onboarding
    ONBOARDING_STARTED = "onboarding.started"
    ONBOARDING_COMPLETED = "onboarding.completed"
    ONBOARDING_FEEDBACK = "onboarding.feedback"

    # Revenue Operations — Feedback Loops
    AGENT_PERFORMANCE_RECORDED = "agent.performance.recorded"
    CUSTOMER_FEEDBACK_RECEIVED = "customer.feedback.received"
    REVENUE_METRIC_RECORDED = "revenue.metric.recorded"

    # V5: Hermes Agent Protocol
    HERMES_SESSION_CREATED = "hermes.session.created"
    HERMES_SKILL_DISCOVERED = "hermes.skill.discovered"
    HERMES_SKILL_IMPROVED = "hermes.skill.improved"
    HERMES_MEMORY_CONSOLIDATED = "hermes.memory.consolidated"

    # V2: Domain & System Coordination
    DOMAIN_ANALYSIS_REQUESTED = "domain.analysis.requested"
    DOMAIN_ANALYSIS_COMPLETED = "domain.analysis.completed"
    CONFLICT_DETECTED = "conflict.detected"

    # Voice Pipeline
    VOICE_INPUT_RECEIVED = "voice.input.received"
    VOICE_TRANSCRIBED = "voice.transcribed"
    VOICE_RESPONSE_GENERATED = "voice.response.generated"

    # Compliance & Security
    COMPLIANCE_CHECK = "compliance.check"
    COMPLIANCE_VIOLATION = "compliance.violation"
    COMPLIANCE_REPORT = "compliance.report"
    SECURITY_SCAN = "security.scan"
    SECURITY_ALERT = "security.alert"
    SECURITY_INCIDENT = "security.incident"

    # Onboarding
    ONBOARDING_STEP_COMPLETED = "onboarding.step.completed"
    ONBOARDING_VERIFICATION = "onboarding.verification"

    # Social / Community
    SOCIAL_PEER_COMPARISON = "social.peer_comparison"
    SOCIAL_LEADERBOARD = "social.leaderboard"
    SOCIAL_COMMUNITY_TIPS = "social.community_tips"
    SOCIAL_TIP_SUBMITTED = "social.tip_submitted"

    # Adaptive Learning
    ADAPTIVE_LEARNING_SIGNAL = "adaptive_learning.signal"
    ADAPTIVE_LEARNING_AGGREGATED = "adaptive_learning.aggregated"
    ADAPTIVE_LEARNING_PUSHED = "adaptive_learning.pushed"
    ADAPTIVE_LEARNING_SYNCED = "adaptive_learning.synced"

    # Governance Swarm
    AUDIT_REQUESTED = "audit.requested"
    AUDIT_COMPLETED = "audit.completed"
    AUDIT_FINDING = "audit.finding"
    ETHICS_REVIEW = "ethics.review"
    ETHICS_VIOLATION = "ethics.violation"
    ETHICS_ASSESSMENT = "ethics.assessment"
    PRIVACY_REQUEST = "privacy.request"
    PRIVACY_AUDIT = "privacy.audit"
    PRIVACY_BREACH = "privacy.breach"
    GOVERNANCE_REPORT = "governance.report"

    # Research Swarm
    RESEARCH_REQUESTED = "research.requested"
    RESEARCH_COMPLETED = "research.completed"
    MARKET_TREND_DETECTED = "market.trend.detected"
    COMPETITOR_ALERT = "competitor.alert"
    USER_INSIGHT_GENERATED = "user.insight.generated"
    INNOVATION_PROPOSED = "innovation.proposed"
    FEATURE_IDEA = "feature.idea"

    # System
    AGENT_HEALTH_CHECK = "agent.health.check"
    PIPELINE_ERROR = "pipeline.error"


class AgentStatus(StrEnum):
    """Agent lifecycle states."""

    IDLE = "idle"
    OBSERVING = "observing"
    THINKING = "thinking"
    ACTING = "acting"
    REFLECTING = "reflecting"
    ERROR = "error"


@dataclass
class AgentEvent:
    """
    An event flowing through the event bus.

    Every event has a type, a source agent, a payload, and metadata
    for tracing and observability.
    """

    event_type: EventType
    source: str  # agent name that produced this
    payload: dict[str, Any]
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    timestamp: float = field(default_factory=time.time)
    correlation_id: str | None = None  # links related events
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize event to dictionary for storage/transmission."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "source": self.source,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "correlation_id": self.correlation_id,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentEvent:
        """Deserialize event from dictionary."""
        return cls(
            event_type=EventType(data["event_type"]),
            source=data["source"],
            payload=data["payload"],
            event_id=data.get("event_id", uuid.uuid4().hex[:16]),
            timestamp=data.get("timestamp", time.time()),
            correlation_id=data.get("correlation_id"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class AgentDecision:
    """
    The output of an agent's think phase.

    Contains the action to take, confidence level, and reasoning
    for observability / explainability.
    """

    action: str  # what to do (e.g. "process_batch", "generate_report")
    parameters: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0  # 0.0 – 1.0
    reasoning: str = ""  # human-readable explanation
    decision_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])


@dataclass
class AgentResult:
    """
    The output of an agent's act phase.

    Wraps the raw result with success/failure status, timing,
    and any events to publish downstream.
    """

    success: bool
    data: Any = None
    error: str | None = None
    duration_ms: float = 0.0
    events_to_publish: list[AgentEvent] = field(default_factory=list)
    result_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentMessage:
    """
    A message from one agent to another (via event bus).

    Unlike events (broadcast), messages are point-to-point.
    """

    sender: str
    recipient: str
    content: dict[str, Any]
    message_type: str = "request"  # request | response | notification
    correlation_id: str | None = None
    message_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
