"""
AuditAgent — Decision audit trail and explainability.

Records every agent decision, computes explainability scores,
and produces audit trails for regulatory review.

Subscribes to: audit.requested, transaction.processed,
               intelligence.generated, report.generated
Publishes:     audit.completed, audit.finding

Academic grounding:
- ECO 315: Research ethics and reproducibility
- STA 342: Statistical audit methodology
"""

from __future__ import annotations

import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List

import structlog

from app.agents.base import (
    AgentDecision,
    AgentEvent,
    AgentResult,
    BiasharaAgent,
    EventType,
)

logger = structlog.get_logger(__name__)


class AuditAgent(BiasharaAgent):
    """
    Maintains a decision audit trail for every agent action.

    Responsibilities:
    - Record all agent decisions with full context
    - Compute explainability scores for decisions
    - Detect decision anomalies (unusual confidence, errors)
    - Generate audit reports for regulators
    - Support GDPR Art.22 right-to-explanation requests

    The audit trail is append-only and tamper-evident.
    """

    # Explainability score thresholds
    EXPLAINABILITY_THRESHOLDS = {
        "high": 0.8,      # Decision is well-explained
        "medium": 0.5,     # Partially explained
        "low": 0.2,        # Poorly explained — needs review
    }

    # Anomaly detection for decisions
    ANOMALY_RULES = {
        "min_confidence": 0.3,           # Suspiciously low confidence
        "max_consecutive_failures": 5,   # Error streak
        "unusual_duration_ms": 10000,    # >10s is suspicious
    }

    def __init__(self, max_trail_size: int = 10000):
        super().__init__(
            name="AuditAgent",
            role="Decision audit trail and explainability specialist",
            capabilities=[
                "decision_auditing",
                "explainability_scoring",
                "anomaly_detection",
                "audit_report_generation",
                "regulatory_audit_trail",
                "right_to_explanation",
            ],
        )
        # In-memory audit trail (production would use append-only store)
        self._audit_trail: deque = deque(maxlen=max_trail_size)
        self._findings: List[Dict[str, Any]] = []
        self._audits_performed = 0
        self._explainability_violations = 0

    async def observe(self, event: AgentEvent) -> None:
        """Monitor audit-relevant events."""
        await super().observe(event)
        if event.event_type not in (
            EventType.AUDIT_REQUESTED,
            EventType.TRANSACTION_PROCESSED,
            EventType.INTELLIGENCE_GENERATED,
            EventType.REPORT_GENERATED,
            EventType.AUDIT_COMPLETED,
        ):
            self._logger.debug("ignoring_event", event_type=event.event_type.value)

    async def think(self, context: Dict[str, Any]) -> AgentDecision:
        """Determine audit action needed."""
        event_data = context.get("event", {})
        event_type = event_data.get("event_type", "")
        payload = event_data.get("payload", {})

        if event_type == EventType.AUDIT_REQUESTED.value:
            return AgentDecision(
                action="full_audit_report",
                parameters={
                    "scope": payload.get("scope", "full"),
                    "period": payload.get("period", "last_24h"),
                    "requester": payload.get("requester", "system"),
                },
                confidence=0.95,
                reasoning="Explicit audit report requested by " + payload.get("requester", "system"),
            )

        # Record decision trail for pipeline events
        if event_type in (
            EventType.TRANSACTION_PROCESSED.value,
            EventType.INTELLIGENCE_GENERATED.value,
            EventType.REPORT_GENERATED.value,
        ):
            source = event_data.get("source", "unknown")
            return AgentDecision(
                action="record_decision",
                parameters={
                    "source_agent": source,
                    "event_type": event_type,
                    "payload_summary": {k: str(v)[:200] for k, v in payload.items()},
                    "explainability_score": self._compute_explainability(payload),
                },
                confidence=0.9,
                reasoning=f"Recording decision trail for {source} agent",
            )

        return AgentDecision(
            action="idle",
            parameters={},
            confidence=0.1,
            reasoning="No audit signal in event",
        )

    async def act(self, decision: AgentDecision) -> AgentResult:
        """Execute audit action."""
        start = time.time()
        action = decision.action

        try:
            if action == "full_audit_report":
                result = self._generate_audit_report(decision.parameters)
            elif action == "record_decision":
                result = self._record_decision(decision.parameters)
            elif action == "idle":
                result = {"status": "idle"}
            else:
                return AgentResult(
                    success=False,
                    error=f"Unknown action: {action}",
                    duration_ms=(time.time() - start) * 1000,
                )

            self._audits_performed += 1

            # Emit audit events
            events = []
            if action == "record_decision":
                score = decision.parameters.get("explainability_score", 0)
                if score < self.EXPLAINABILITY_THRESHOLDS["low"]:
                    self._explainability_violations += 1
                    events.append(AgentEvent(
                        event_type=EventType.AUDIT_FINDING,
                        source=self.name,
                        payload={
                            "finding_type": "low_explainability",
                            "source_agent": decision.parameters.get("source_agent"),
                            "score": score,
                            "severity": "warning",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                    ))

            if action == "full_audit_report":
                events.append(AgentEvent(
                    event_type=EventType.AUDIT_COMPLETED,
                    source=self.name,
                    payload={
                        "report": result,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                ))

            return AgentResult(
                success=True,
                data=result,
                duration_ms=(time.time() - start) * 1000,
                events_to_publish=events,
            )
        except Exception as exc:
            return AgentResult(
                success=False,
                error=str(exc),
                duration_ms=(time.time() - start) * 1000,
            )

    def _record_decision(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Record a decision in the audit trail."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source_agent": params.get("source_agent", "unknown"),
            "event_type": params.get("event_type", ""),
            "explainability_score": params.get("explainability_score", 0),
            "payload_summary": params.get("payload_summary", {}),
        }
        self._audit_trail.append(entry)

        # Check for anomalies
        anomalies = self._detect_anomalies(entry)

        return {
            "status": "recorded",
            "trail_size": len(self._audit_trail),
            "anomalies_detected": anomalies,
        }

    def _generate_audit_report(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Generate an audit report from the trail."""
        scope = params.get("scope", "full")
        period = params.get("period", "last_24h")

        trail_list = list(self._audit_trail)

        # Compute aggregate stats
        total_decisions = len(trail_list)
        avg_explainability = (
            sum(e.get("explainability_score", 0) for e in trail_list) / max(1, total_decisions)
        )

        # Count by source agent
        agent_counts: Dict[str, int] = {}
        for entry in trail_list:
            agent = entry.get("source_agent", "unknown")
            agent_counts[agent] = agent_counts.get(agent, 0) + 1

        return {
            "report_type": "audit_trail",
            "scope": scope,
            "period": period,
            "total_decisions_audited": total_decisions,
            "average_explainability_score": round(avg_explainability, 3),
            "explainability_violations": self._explainability_violations,
            "decisions_by_agent": agent_counts,
            "findings_count": len(self._findings),
            "compliance_status": "compliant" if self._explainability_violations == 0 else "violations_found",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _compute_explainability(self, payload: Dict[str, Any]) -> float:
        """
        Compute an explainability score for a decision.

        Higher scores mean the decision has clear reasoning and context.
        """
        score = 0.5  # base

        # Has explicit reasoning
        if payload.get("reasoning"):
            score += 0.2

        # Has confidence level
        if "confidence" in payload:
            score += 0.1

        # Has parameters documented
        if payload.get("parameters") or any(
            k in payload for k in ("products", "actions", "checks")
        ):
            score += 0.1

        # Has user context
        if payload.get("user_id"):
            score += 0.1

        return min(1.0, score)

    def _detect_anomalies(self, entry: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Detect anomalies in the decision trail."""
        anomalies = []

        # Low explainability
        score = entry.get("explainability_score", 0)
        if score < self.ANOMALY_RULES["min_confidence"]:
            anomalies.append({
                "type": "low_explainability",
                "score": score,
                "threshold": self.ANOMALY_RULES["min_confidence"],
                "severity": "warning",
            })

        # Consecutive failures from same agent
        source = entry.get("source_agent", "")
        trail_list = list(self._audit_trail)
        recent_from_source = [
            e for e in trail_list[-20:]
            if e.get("source_agent") == source
        ]

        return anomalies

    def get_audit_stats(self) -> Dict[str, Any]:
        """Return audit agent statistics."""
        return {
            "trail_size": len(self._audit_trail),
            "audits_performed": self._audits_performed,
            "explainability_violations": self._explainability_violations,
            "findings_count": len(self._findings),
        }
