"""
Lead Qualification Agent — Autonomous lead scoring and routing.

Lifecycle:
    observe → New lead event or manual trigger
    think   → Score the lead across 5 dimensions
    act     → Qualify, reject, or escalate to Valentine
    reflect → Learn from conversion outcomes

Scoring dimensions (each 0-100):
    1. Company Size   — larger companies score higher
    2. Industry Fit   — alignment with Angavu's target verticals
    3. Budget Signal  — explicit or inferred budget clarity
    4. Timing         — urgency and buying cycle alignment
    5. Engagement     — response rate, meeting requests, etc.

Thresholds:
    composite >= 70  → ESCALATE to Valentine (high-value)
    composite >= 40  → QUALIFY (nurture pipeline)
    composite <  40  → REJECT (not viable now)
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

import structlog

from app.agents.base import (
    AgentDecision,
    AgentEvent,
    AgentResult,
    BiasharaAgent,
    EventType,
)
from app.autonomous.models.lead import Lead, LeadScore, LeadStatus

logger = structlog.get_logger(__name__)

# ── Scoring configuration ──────────────────────────────────────────

# Industries ranked by fit for Angavu Intelligence
INDUSTRY_FIT_SCORES: dict[str, float] = {
    "fmcg": 95.0,
    "retail": 90.0,
    "wholesale": 85.0,
    "agriculture": 80.0,
    "manufacturing": 75.0,
    "logistics": 70.0,
    "financial_services": 65.0,
    "healthcare": 55.0,
    "education": 50.0,
    "technology": 45.0,
    "construction": 40.0,
    "hospitality": 35.0,
    "other": 20.0,
}

# Company size bands → score
COMPANY_SIZE_SCORES: dict[str, float] = {
    "1-10": 20.0,
    "11-50": 45.0,
    "51-200": 70.0,
    "201-1000": 85.0,
    "1000+": 95.0,
}

# Qualification thresholds
ESCALATE_THRESHOLD = 70.0   # → Valentine
QUALIFY_THRESHOLD = 40.0    # → Nurture pipeline
# Below QUALIFY_THRESHOLD → reject

# Budget scoring: KES per month
BANDS = [
    (500_000, 95.0),   # 500K+ → near-max
    (100_000, 80.0),
    (50_000, 60.0),
    (10_000, 40.0),
    (1_000, 20.0),
    (0, 5.0),
]


class LeadQualifierAgent(BiasharaAgent):
    """
    Autonomous lead qualification agent.

    Subscribes to: lead.created
    Publishes:     lead.qualified, lead.rejected, lead.escalated

    Scoring is deterministic (rule-based) so it's fast and explainable.
    The reflect phase learns from conversion outcomes to adjust weights.
    """

    def __init__(self):
        super().__init__(
            name="LeadQualifier",
            role="Lead scoring and qualification specialist",
            capabilities=[
                "lead_scoring",
                "lead_qualification",
                "lead_routing",
                "conversion_tracking",
            ],
        )
        # Adaptive weights — adjusted by reflect() based on outcomes
        self._weights = {
            "company_size": 0.25,
            "industry_fit": 0.25,
            "budget_signal": 0.20,
            "timing": 0.15,
            "engagement": 0.15,
        }
        # Track conversions for learning
        self._conversion_outcomes: list[dict[str, Any]] = []

    # ── Lifecycle ───────────────────────────────────────────────────

    async def observe(self, event: AgentEvent) -> None:
        """Filter for lead events only."""
        await super().observe(event)
        if event.event_type not in (
            EventType.LEAD_CREATED,
            EventType.LEAD_QUALIFIED,
            EventType.CUSTOMER_FEEDBACK_RECEIVED,
        ):
            self._logger.debug("ignoring_event", event_type=event.event_type.value)

    async def think(self, context: dict[str, Any]) -> AgentDecision:
        """
        Score the lead and decide: qualify, reject, or escalate.

        Scoring algorithm:
        1. Company size → score from lookup table
        2. Industry fit → score from target vertical mapping
        3. Budget signal → score from budget band table
        4. Timing → score from urgency indicators
        5. Engagement → score from interaction history
        6. Composite = weighted average
        7. Route based on composite threshold
        """
        event_data = context.get("event", {})
        payload = event_data.get("payload", {})

        # Extract or reconstruct lead
        lead_data = payload.get("lead", {})
        if lead_data:
            lead = Lead.from_dict(lead_data)
        else:
            # Build lead from individual fields in payload
            lead = Lead(
                company_name=payload.get("company_name", ""),
                contact_name=payload.get("contact_name", ""),
                contact_email=payload.get("contact_email", ""),
                industry=payload.get("industry", "other"),
                company_size=payload.get("company_size", "1-10"),
                estimated_budget=payload.get("estimated_budget", 0.0),
            )

        # Score each dimension
        scores = self._score_lead(lead, payload)

        # Apply strategy adjustment from reflect→behavior loop
        strategy = context.get("strategy_adjustment")
        if strategy:
            factor = strategy.get("threshold_factor", 1.0)
            scores.composite *= factor

        # Decide action based on composite score
        if scores.composite >= ESCALATE_THRESHOLD:
            action = "escalate"
        elif scores.composite >= QUALIFY_THRESHOLD:
            action = "qualify"
        else:
            action = "reject"

        reasoning = (
            f"Lead '{lead.company_name}' scored {scores.composite:.0f}/100. "
            f"Size={scores.company_size:.0f}, Industry={scores.industry_fit:.0f}, "
            f"Budget={scores.budget_signal:.0f}, Timing={scores.timing:.0f}, "
            f"Engagement={scores.engagement:.0f}. "
            f"Decision: {action.upper()} "
            f"(threshold: escalate>={ESCALATE_THRESHOLD}, qualify>={QUALIFY_THRESHOLD})."
        )

        return AgentDecision(
            action=action,
            parameters={
                "lead": lead.to_dict(),
                "scores": scores.to_dict(),
                "weights": self._weights,
            },
            confidence=scores.composite / 100.0,
            reasoning=reasoning,
        )

    async def act(self, decision: AgentDecision) -> AgentResult:
        """
        Execute the qualification decision.

        - qualify: Update lead status, emit lead.qualified
        - reject: Update lead status, emit lead.rejected
        - escalate: Update lead status + assign to Valentine, emit lead.escalated
        """
        start = time.time()

        try:
            action = decision.action
            lead_data = decision.parameters["lead"]
            scores = decision.parameters["scores"]
            lead = Lead.from_dict(lead_data)
            lead.score = LeadScore(**scores)
            lead.score.calculate_composite()

            events_to_publish = []

            if action == "escalate":
                lead.status = LeadStatus.ESCALATED
                lead.assigned_to = "valentine"
                lead.qualified_at = datetime.now(UTC)
                events_to_publish.append(AgentEvent(
                    event_type=EventType.LEAD_ESCALATED,
                    source=self.name,
                    payload={
                        "lead": lead.to_dict(),
                        "reason": "high_value_lead",
                        "assigned_to": "valentine",
                        "composite_score": lead.score.composite,
                    },
                ))
                self._logger.info(
                    "lead_escalated",
                    lead_id=lead.lead_id,
                    company=lead.company_name,
                    score=round(lead.score.composite, 1),
                )

            elif action == "qualify":
                lead.status = LeadStatus.QUALIFIED
                lead.qualified_at = datetime.now(UTC)
                events_to_publish.append(AgentEvent(
                    event_type=EventType.LEAD_QUALIFIED,
                    source=self.name,
                    payload={
                        "lead": lead.to_dict(),
                        "composite_score": lead.score.composite,
                    },
                ))
                self._logger.info(
                    "lead_qualified",
                    lead_id=lead.lead_id,
                    company=lead.company_name,
                    score=round(lead.score.composite, 1),
                )

            else:  # reject
                lead.status = LeadStatus.REJECTED
                lead.qualified_at = datetime.now(UTC)
                events_to_publish.append(AgentEvent(
                    event_type=EventType.LEAD_REJECTED,
                    source=self.name,
                    payload={
                        "lead": lead.to_dict(),
                        "reason": "below_threshold",
                        "composite_score": lead.score.composite,
                    },
                ))
                self._logger.info(
                    "lead_rejected",
                    lead_id=lead.lead_id,
                    company=lead.company_name,
                    score=round(lead.score.composite, 1),
                )

            # Store lead in memory for reflection
            self.memory.remember({
                "event_type": f"lead.{action}",
                "lead_id": lead.lead_id,
                "composite_score": lead.score.composite,
                "action": action,
            })

            duration_ms = (time.time() - start) * 1000

            return AgentResult(
                success=True,
                data={
                    "lead_id": lead.lead_id,
                    "action": action,
                    "composite_score": round(lead.score.composite, 1),
                    "status": lead.status.value,
                    "assigned_to": lead.assigned_to,
                },
                duration_ms=duration_ms,
                events_to_publish=events_to_publish,
            )

        except Exception as exc:
            return AgentResult(
                success=False,
                error=str(exc),
                duration_ms=(time.time() - start) * 1000,
                events_to_publish=[
                    AgentEvent(
                        event_type=EventType.PIPELINE_ERROR,
                        source=self.name,
                        payload={"error": str(exc), "phase": "lead_qualification"},
                    )
                ],
            )

    async def reflect(self, result: AgentResult) -> None:
        """
        Learn from qualification outcomes.

        When conversion feedback arrives, adjusts scoring weights
        to improve future qualification accuracy.
        """
        await super().reflect(result)

        if result.success:
            data = result.data or {}
            self._conversion_outcomes.append({
                "lead_id": data.get("lead_id"),
                "action": data.get("action"),
                "score": data.get("composite_score"),
                "timestamp": time.time(),
            })

            # Keep only recent outcomes
            if len(self._conversion_outcomes) > 100:
                self._conversion_outcomes = self._conversion_outcomes[-100:]

    # ── Scoring helpers ─────────────────────────────────────────────

    def _score_lead(self, lead: Lead, payload: dict[str, Any]) -> LeadScore:
        """Score a lead across all 5 dimensions."""
        scores = LeadScore()

        # 1. Company size
        scores.company_size = self._score_company_size(lead.company_size)

        # 2. Industry fit
        scores.industry_fit = self._score_industry_fit(lead.industry)

        # 3. Budget signal
        scores.budget_signal = self._score_budget(lead.estimated_budget)

        # 4. Timing
        scores.timing = self._score_timing(payload)

        # 5. Engagement
        scores.engagement = self._score_engagement(payload)

        scores.calculate_composite()
        return scores

    @staticmethod
    def _score_company_size(size_band: str) -> float:
        """Score based on company size band."""
        return COMPANY_SIZE_SCORES.get(size_band, 20.0)

    @staticmethod
    def _score_industry_fit(industry: str) -> float:
        """Score based on industry alignment with Angavu's target markets."""
        industry_lower = industry.lower().replace(" ", "_")
        return INDUSTRY_FIT_SCORES.get(industry_lower, INDUSTRY_FIT_SCORES["other"])

    @staticmethod
    def _score_budget(estimated_monthly: float) -> float:
        """Score based on estimated monthly budget in KES."""
        for threshold, score in BANDS:
            if estimated_monthly >= threshold:
                return score
        return 5.0

    @staticmethod
    def _score_timing(payload: dict[str, Any]) -> float:
        """Score based on timing signals."""
        score = 50.0  # baseline

        # Explicit urgency
        urgency = payload.get("urgency", "").lower()
        if urgency in ("immediate", "urgent", "asap"):
            score = 90.0
        elif urgency in ("this_quarter", "q1", "q2", "q3", "q4"):
            score = 70.0
        elif urgency in ("next_quarter", "next_year"):
            score = 30.0
        elif urgency in ("exploring", "just_looking"):
            score = 15.0

        # Decision timeline
        timeline_days = payload.get("decision_timeline_days")
        if timeline_days is not None:
            if timeline_days <= 14:
                score = max(score, 85.0)
            elif timeline_days <= 30:
                score = max(score, 65.0)
            elif timeline_days <= 90:
                score = max(score, 45.0)
            else:
                score = max(score, 20.0)

        return min(score, 100.0)

    @staticmethod
    def _score_engagement(payload: dict[str, Any]) -> float:
        """Score based on engagement signals."""
        score = 30.0  # baseline for inbound

        # Meetings requested
        meetings = payload.get("meetings_requested", 0)
        score += min(meetings * 15, 40)

        # Emails opened
        email_opens = payload.get("email_opens", 0)
        score += min(email_opens * 5, 20)

        # Content downloaded
        downloads = payload.get("content_downloads", 0)
        score += min(downloads * 10, 20)

        # Referral bonus
        if payload.get("source") == "referral":
            score += 15

        return min(score, 100.0)
