"""
Sales Agent — Autonomous lead qualification, outreach, and follow-up.

Operates the sales pipeline without human intervention:
    - Scans for new leads from multiple channels
    - Qualifies leads based on ICP (Ideal Customer Profile)
    - Executes personalized outreach sequences
    - Follows up with warm leads on schedule
    - Escalates high-value opportunities to Valentine

Target customers:
    - Microfinance institutions (MFIs)
    - SACCOs (Savings and Credit Co-operatives)
    - Mobile money operators
    - FMCG distributors targeting informal markets
    - Government agencies (financial inclusion programs)

DeerFlow Pattern: Uses observe → think → act → reflect cycle.
"""

from __future__ import annotations

import time
from typing import Any

import structlog

from app.agents.base import AgentDecision, AgentResult, EventType
from app.autonomous.agents.base import AutonomousAgent
from app.autonomous.config import AgentConfig

logger = structlog.get_logger(__name__)


class SalesAgent(AutonomousAgent):
    """
    Autonomous sales agent for Angavu Intelligence / Msaidizi.

    Handles the full sales lifecycle:
    1. Lead Discovery — scan CRM, website, referrals for new leads
    2. Qualification — score leads against ICP criteria
    3. Outreach — personalized first contact
    4. Follow-up — scheduled nurture sequences
    5. Handoff — escalate qualified opportunities to Valentine
    """

    CONFIG_NAME = "sales_agent"
    SUBSCRIBED_EVENTS = [
        EventType.TRANSACTION_PROCESSED,
        EventType.INTELLIGENCE_GENERATED,
        EventType.FEEDBACK_RECEIVED,
    ]

    def __init__(self, config: AgentConfig | None = None):
        super().__init__(
            name="SalesAgent",
            role="Autonomous Sales — lead qualification, outreach, follow-up",
            capabilities=[
                "lead_discovery",
                "lead_qualification",
                "outreach_execution",
                "follow_up_scheduling",
                "pipeline_management",
                "crm_integration",
            ],
            config=config,
        )

        # Sales pipeline state
        self._leads: dict[str, dict[str, Any]] = {}
        self._outreach_queue: list[dict[str, Any]] = []
        self._follow_up_schedule: dict[str, float] = {}

        # ICP (Ideal Customer Profile) scoring weights
        self._icp_weights = {
            "sector_fit": 0.25,        # MFI, SACCO, mobile money
            "size_fit": 0.20,          # Number of users/clients
            "tech_readiness": 0.15,    # Digital infrastructure
            "budget_fit": 0.20,        # Can afford the solution
            "geography": 0.10,         # East Africa focus
            "urgency": 0.10,           # Active pain point
        }

        # Register tools
        self.tools.register("qualify_lead", self._qualify_lead, "Score a lead against ICP")
        self.tools.register("draft_outreach", self._draft_outreach, "Draft outreach message")
        self.tools.register("schedule_follow_up", self._schedule_follow_up, "Schedule follow-up")

    async def think(self, context: dict[str, Any]) -> AgentDecision:
        """
        Analyze the event context and decide what sales action to take.

        Decision logic:
        - New transaction data → discover potential leads
        - Intelligence generated → identify market opportunities
        - Feedback received → adjust outreach strategy
        - Follow-up due → execute scheduled follow-up
        """
        event_data = context.get("event", {})
        event_type = event_data.get("event_type", "")

        # Check for due follow-ups first
        due_follow_ups = self._get_due_follow_ups()
        if due_follow_ups:
            return AgentDecision(
                action="execute_follow_up",
                parameters={"leads": due_follow_ups[:3]},  # Batch up to 3
                confidence=0.9,
                reasoning=f"{len(due_follow_ups)} follow-up(s) due",
            )

        # React to event type
        if event_type == EventType.TRANSACTION_PROCESSED.value:
            payload = event_data.get("payload", {})
            if payload.get("business_type") in ("mfi", "sacco", "mobile_money"):
                return AgentDecision(
                    action="qualify_lead",
                    parameters={"lead_data": payload},
                    confidence=0.7,
                    reasoning="Transaction from potential ICP match",
                )

        if event_type == EventType.INTELLIGENCE_GENERATED.value:
            return AgentDecision(
                action="scan_opportunities",
                parameters={"intelligence": event_data.get("payload", {})},
                confidence=0.6,
                reasoning="Intelligence report may contain sales signals",
            )

        if event_type == EventType.FEEDBACK_RECEIVED.value:
            return AgentDecision(
                action="adjust_strategy",
                parameters={"feedback": event_data.get("payload", {})},
                confidence=0.8,
                reasoning="Feedback received — review and adjust approach",
            )

        return AgentDecision(
            action="idle",
            parameters={},
            confidence=0.5,
            reasoning="No actionable sales signal in current event",
        )

    async def act(self, decision: AgentDecision) -> AgentResult:
        """Execute the sales action."""
        action = decision.action
        params = decision.parameters
        start = time.time()

        try:
            if action == "qualify_lead":
                result_data = await self._qualify_lead(params.get("lead_data", {}))
            elif action == "execute_follow_up":
                result_data = await self._execute_follow_ups(params.get("leads", []))
            elif action == "scan_opportunities":
                result_data = await self._scan_opportunities(params.get("intelligence", {}))
            elif action == "adjust_strategy":
                result_data = await self._adjust_strategy(params.get("feedback", {}))
            elif action == "idle":
                result_data = {"status": "idle", "reason": "no actionable signal"}
            else:
                return AgentResult(
                    success=False,
                    error=f"Unknown action: {action}",
                    duration_ms=(time.time() - start) * 1000,
                )

            return AgentResult(
                success=True,
                data=result_data,
                duration_ms=(time.time() - start) * 1000,
            )

        except Exception as exc:
            self._logger.error("sales_action_failed", action=action, error=str(exc))
            return AgentResult(
                success=False,
                error=str(exc),
                duration_ms=(time.time() - start) * 1000,
            )

    # ── Sales Operations ────────────────────────────────────────────

    async def _qualify_lead(self, lead_data: dict[str, Any]) -> dict[str, Any]:
        """Qualify a lead against ICP criteria."""
        if not lead_data:
            return {"status": "no_data"}

        scores = {}
        for criterion, weight in self._icp_weights.items():
            raw_score = self._score_criterion(criterion, lead_data)
            scores[criterion] = round(raw_score * weight, 2)

        total_score = sum(scores.values())
        qualified = total_score >= 0.6

        lead_id = lead_data.get("id", f"lead_{int(time.time())}")
        self._leads[lead_id] = {
            "lead_id": lead_id,
            "data": lead_data,
            "scores": scores,
            "total_score": round(total_score, 2),
            "qualified": qualified,
            "status": "qualified" if qualified else "nurture",
            "created_at": time.time(),
        }

        self._logger.info(
            "lead_qualified",
            lead_id=lead_id,
            score=round(total_score, 2),
            qualified=qualified,
        )

        if qualified:
            # Schedule outreach
            self._outreach_queue.append(self._leads[lead_id])

        return {
            "lead_id": lead_id,
            "score": round(total_score, 2),
            "qualified": qualified,
            "scores": scores,
            "next_action": "outreach" if qualified else "nurture",
        }

    async def _execute_follow_ups(self, leads: list[dict[str, Any]]) -> dict[str, Any]:
        """Execute scheduled follow-ups."""
        results = []
        for lead in leads:
            lead_id = lead.get("lead_id", "unknown")
            self._logger.info("executing_follow_up", lead_id=lead_id)
            results.append({
                "lead_id": lead_id,
                "action": "follow_up_sent",
                "timestamp": time.time(),
            })
            # Schedule next follow-up
            self._follow_up_schedule[lead_id] = time.time() + 86400 * 3  # 3 days

        return {"follow_ups_executed": len(results), "results": results}

    async def _scan_opportunities(self, intelligence: dict[str, Any]) -> dict[str, Any]:
        """Scan intelligence data for sales opportunities."""
        opportunities = []
        # Look for market signals that indicate potential customers
        for key, value in intelligence.items():
            if isinstance(value, dict) and value.get("growth_rate", 0) > 0.1:
                opportunities.append({
                    "signal": key,
                    "growth_rate": value.get("growth_rate"),
                    "potential": "high",
                })

        return {
            "opportunities_found": len(opportunities),
            "opportunities": opportunities,
        }

    async def _adjust_strategy(self, feedback: dict[str, Any]) -> dict[str, Any]:
        """Adjust sales strategy based on feedback."""
        sentiment = feedback.get("sentiment", "neutral")
        if sentiment == "negative":
            self._logger.warning("negative_feedback_received", feedback=feedback)
            return {"adjustment": "review_approach", "feedback": feedback}
        return {"adjustment": "maintain", "feedback": feedback}

    def _score_criterion(self, criterion: str, lead_data: dict[str, Any]) -> float:
        """Score a single ICP criterion (0.0 - 1.0)."""
        scoring_rules = {
            "sector_fit": lambda d: 1.0 if d.get("sector") in ("mfi", "sacco", "mobile_money", "fmcg") else 0.3,
            "size_fit": lambda d: min(1.0, (d.get("user_count", 0) or d.get("client_count", 0)) / 10000),
            "tech_readiness": lambda d: 0.8 if d.get("has_api") else 0.4 if d.get("has_website") else 0.2,
            "budget_fit": lambda d: 0.8 if d.get("annual_revenue", 0) > 100000 else 0.4,
            "geography": lambda d: 1.0 if d.get("country") in ("KE", "UG", "TZ", "RW", "ET") else 0.3,
            "urgency": lambda d: 0.9 if d.get("active_pain_point") else 0.3,
        }
        scorer = scoring_rules.get(criterion, lambda d: 0.5)
        try:
            return scorer(lead_data)
        except Exception:
            return 0.5

    def _get_due_follow_ups(self) -> list[dict[str, Any]]:
        """Get leads with due follow-ups."""
        now = time.time()
        due = []
        for lead_id, scheduled_at in list(self._follow_up_schedule.items()):
            if now >= scheduled_at:
                lead = self._leads.get(lead_id, {"lead_id": lead_id})
                due.append(lead)
                del self._follow_up_schedule[lead_id]
        return due
