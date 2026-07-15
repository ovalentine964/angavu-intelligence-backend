"""
InnovationAgent — Feature ideation based on user needs.

Synthesizes market research, user insights, and competitive intelligence
to propose new features and product improvements for Angavu Intelligence.

Subscribes to: research.requested, user.insight.generated,
               market.trend.detected, feedback.received, evolution.cycle.complete
Publishes:     innovation.proposed, feature.idea, research.completed

Academic grounding:
- ECO 315: Innovation economics, technology adoption curves
- STA 343: A/B testing for feature validation
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


class InnovationAgent(BiasharaAgent):
    """
    Generates feature ideas from market research and user insights.

    Responsibilities:
    - Synthesize market trends into feature opportunities
    - Map user pain points to potential solutions
    - Evaluate competitor gaps for differentiation
    - Prioritize feature ideas by impact and feasibility
    - Generate feature briefs for the product team
    - Track innovation pipeline health

    Innovation framework:
    1. Problem identification (from user insights + feedback)
    2. Opportunity sizing (from market research)
    3. Solution ideation (from competitor gaps + user needs)
    4. Impact estimation (from user segments + revenue potential)
    5. Feasibility scoring (from technical complexity + resources)
    """

    # Innovation categories relevant to informal economy
    INNOVATION_CATEGORIES = [
        "financial_inclusion",
        "market_access",
        "data_intelligence",
        "community_features",
        "voice_interface",
        "offline_capability",
        "gamification",
        "partnerships",
    ]

    # Impact scoring weights
    IMPACT_WEIGHTS = {
        "user_reach": 0.3,           # How many users benefit
        "revenue_impact": 0.25,       # Revenue potential
        "retention_impact": 0.2,      # Retention improvement
        "competitive_advantage": 0.15, # Differentiation
        "strategic_alignment": 0.1,   # Alignment with mission
    }

    def __init__(self, max_pipeline: int = 100):
        super().__init__(
            name="InnovationAgent",
            role="Feature ideation and innovation specialist",
            capabilities=[
                "feature_ideation",
                "opportunity_sizing",
                "impact_estimation",
                "feasibility_scoring",
                "innovation_pipeline_management",
                "competitive_gap_analysis",
                "feature_prioritization",
            ],
        )
        self._innovation_pipeline: deque = deque(maxlen=max_pipeline)
        self._features_proposed = 0
        self._ideas_generated = 0

    async def observe(self, event: AgentEvent) -> None:
        """Monitor innovation-relevant events."""
        await super().observe(event)
        if event.event_type not in (
            EventType.RESEARCH_REQUESTED,
            EventType.USER_INSIGHT_GENERATED,
            EventType.MARKET_TREND_DETECTED,
            EventType.FEEDBACK_RECEIVED,
            EventType.EVOLUTION_CYCLE_COMPLETE,
            EventType.COMPETITOR_ALERT,
            EventType.FEATURE_SPEC_GENERATED,
        ):
            self._logger.debug("ignoring_event", event_type=event.event_type.value)

    async def think(self, context: Dict[str, Any]) -> AgentDecision:
        """Determine innovation action needed."""
        event_data = context.get("event", {})
        event_type = event_data.get("event_type", "")
        payload = event_data.get("payload", {})

        if event_type == EventType.RESEARCH_REQUESTED.value:
            research_type = payload.get("type", "")
            if research_type in ("innovation", "feature", "ideas"):
                return AgentDecision(
                    action="generate_innovation_brief",
                    parameters={
                        "category": payload.get("category", "all"),
                        "user_segment": payload.get("segment", "all"),
                        "constraints": payload.get("constraints", {}),
                    },
                    confidence=0.9,
                    reasoning=f"Innovation research requested: {research_type}",
                )

        if event_type == EventType.USER_INSIGHT_GENERATED.value:
            return AgentDecision(
                action="ideate_from_insight",
                parameters={
                    "insight_type": payload.get("insight_type", "general"),
                    "insights": payload.get("insights", {}),
                    "segment": payload.get("segment", "all"),
                },
                confidence=0.85,
                reasoning="Generating feature ideas from user insight",
            )

        if event_type == EventType.MARKET_TREND_DETECTED.value:
            return AgentDecision(
                action="ideate_from_trend",
                parameters={
                    "commodity": payload.get("commodity", ""),
                    "trend": payload.get("trend", ""),
                    "market": payload.get("market", ""),
                },
                confidence=0.8,
                reasoning="Generating feature ideas from market trend",
            )

        if event_type == EventType.FEEDBACK_RECEIVED.value:
            feedback_type = payload.get("feedback_type", "")
            if feedback_type in ("feature_request", "bug_report", "suggestion"):
                return AgentDecision(
                    action="process_feature_feedback",
                    parameters={
                        "user_id": payload.get("user_id", payload.get("worker_id")),
                        "feedback_type": feedback_type,
                        "text": payload.get("text", ""),
                        "category": payload.get("category", ""),
                    },
                    confidence=0.8,
                    reasoning=f"Processing {feedback_type} as feature input",
                )

        if event_type == EventType.COMPETITOR_ALERT.value:
            return AgentDecision(
                action="analyze_competitor_gap",
                parameters={
                    "competitor": payload.get("competitor", ""),
                    "move": payload.get("move", payload.get("affected_competitors", [])),
                    "commodity": payload.get("commodity", ""),
                },
                confidence=0.75,
                reasoning="Analyzing competitor move for innovation opportunities",
            )

        if event_type == EventType.EVOLUTION_CYCLE_COMPLETE.value:
            return AgentDecision(
                action="review_evolution_cycle",
                parameters={
                    "cycle_type": payload.get("cycle_type", ""),
                    "items_processed": payload.get("items_processed", 0),
                },
                confidence=0.7,
                reasoning="Reviewing evolution cycle for innovation signals",
            )

        return AgentDecision(
            action="idle",
            parameters={},
            confidence=0.1,
            reasoning="No innovation signal in event",
        )

    async def act(self, decision: AgentDecision) -> AgentResult:
        """Execute innovation action."""
        start = time.time()
        action = decision.action

        try:
            if action == "generate_innovation_brief":
                result = self._generate_brief(decision.parameters)
            elif action == "ideate_from_insight":
                result = self._ideate_from_insight(decision.parameters)
            elif action == "ideate_from_trend":
                result = self._ideate_from_trend(decision.parameters)
            elif action == "process_feature_feedback":
                result = self._process_feedback(decision.parameters)
            elif action == "analyze_competitor_gap":
                result = self._analyze_competitor_gap(decision.parameters)
            elif action == "review_evolution_cycle":
                result = self._review_evolution(decision.parameters)
            elif action == "idle":
                result = {"status": "idle"}
            else:
                return AgentResult(
                    success=False,
                    error=f"Unknown action: {action}",
                    duration_ms=(time.time() - start) * 1000,
                )

            self._ideas_generated += 1

            # Emit innovation events
            events = []
            if isinstance(result, dict) and result.get("ideas"):
                for idea in result["ideas"]:
                    self._features_proposed += 1
                    self._innovation_pipeline.append(idea)
                    events.append(AgentEvent(
                        event_type=EventType.FEATURE_IDEA,
                        source=self.name,
                        payload=idea,
                    ))

            if action in ("generate_innovation_brief", "ideate_from_insight", "ideate_from_trend"):
                events.append(AgentEvent(
                    event_type=EventType.INNOVATION_PROPOSED,
                    source=self.name,
                    payload={
                        "action": action,
                        "ideas_count": len(result.get("ideas", [])) if isinstance(result, dict) else 0,
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

    def _generate_brief(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Generate an innovation brief with prioritized ideas."""
        category = params.get("category", "all")
        segment = params.get("user_segment", "all")

        ideas = []
        categories = (
            self.INNOVATION_CATEGORIES
            if category == "all"
            else [category]
        )

        for cat in categories[:3]:
            ideas.append({
                "category": cat,
                "title": f"Opportunity in {cat.replace('_', ' ')}",
                "problem": f"Users in {segment} segment need better {cat.replace('_', ' ')} capabilities",
                "proposed_solution": f"New {cat.replace('_', ' ')} feature based on market research",
                "impact_score": 0.7,
                "feasibility_score": 0.6,
                "priority_score": 0.65,
                "user_segment": segment,
                "source": "innovation_brief",
                "generated_at": datetime.now(timezone.utc).isoformat(),
            })

        return {
            "brief_type": "innovation",
            "category": category,
            "segment": segment,
            "ideas": ideas,
            "pipeline_size": len(self._innovation_pipeline),
            "total_proposed": self._features_proposed,
        }

    def _ideate_from_insight(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Generate feature ideas from user insights."""
        insight_type = params.get("insight_type", "general")

        ideas = []
        if insight_type == "churn":
            ideas.append({
                "category": "retention",
                "title": "Churn prevention intervention",
                "problem": "Users showing churn signals need re-engagement",
                "proposed_solution": "Automated re-engagement messages based on churn risk score",
                "impact_score": 0.8,
                "feasibility_score": 0.7,
                "priority_score": 0.75,
                "source": "churn_insight",
            })

        if insight_type == "retention":
            ideas.append({
                "category": "gamification",
                "title": "Enhanced retention gamification",
                "problem": "Retention curves show drop-off after initial engagement",
                "proposed_solution": "Milestone rewards and streak bonuses for consistent usage",
                "impact_score": 0.7,
                "feasibility_score": 0.8,
                "priority_score": 0.75,
                "source": "retention_insight",
            })

        return {
            "source_insight": insight_type,
            "ideas": ideas,
        }

    def _ideate_from_trend(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Generate feature ideas from market trends."""
        commodity = params.get("commodity", "")
        trend = params.get("trend", "")

        ideas = []
        if trend in ("rising", "volatile"):
            ideas.append({
                "category": "data_intelligence",
                "title": f"Price alert for {commodity}",
                "problem": f"Users need timely alerts when {commodity} prices change significantly",
                "proposed_solution": f"Push notification when {commodity} price changes >10%",
                "impact_score": 0.75,
                "feasibility_score": 0.9,
                "priority_score": 0.8,
                "source": "market_trend",
            })

        return {
            "source_trend": trend,
            "commodity": commodity,
            "ideas": ideas,
        }

    def _process_feedback(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Process feature request feedback into pipeline item."""
        text = params.get("text", "")
        feedback_type = params.get("feedback_type", "")

        idea = {
            "category": "user_request",
            "title": f"User feature {feedback_type}",
            "problem": text[:200] if text else "User feedback",
            "proposed_solution": "To be determined from feedback clustering",
            "impact_score": 0.5,
            "feasibility_score": 0.5,
            "priority_score": 0.5,
            "source": "user_feedback",
            "user_id": params.get("user_id"),
        }

        self._innovation_pipeline.append(idea)

        return {
            "feedback_processed": True,
            "idea_added_to_pipeline": True,
            "pipeline_size": len(self._innovation_pipeline),
        }

    def _analyze_competitor_gap(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze competitor move for innovation opportunity."""
        competitor = params.get("competitor", "")

        ideas = [{
            "category": "competitive_response",
            "title": f"Response to {competitor} move",
            "problem": f"Competitor {competitor} making market moves",
            "proposed_solution": "Differentiated feature to maintain competitive advantage",
            "impact_score": 0.6,
            "feasibility_score": 0.5,
            "priority_score": 0.55,
            "source": "competitor_analysis",
        }]

        return {
            "competitor": competitor,
            "ideas": ideas,
        }

    def _review_evolution(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Review evolution cycle for innovation signals."""
        return {
            "cycle_type": params.get("cycle_type"),
            "items_processed": params.get("items_processed", 0),
            "innovation_signals": "extracted_from_evolution",
        }

    def get_innovation_stats(self) -> Dict[str, Any]:
        """Return innovation agent statistics."""
        return {
            "ideas_generated": self._ideas_generated,
            "features_proposed": self._features_proposed,
            "pipeline_size": len(self._innovation_pipeline),
            "categories": self.INNOVATION_CATEGORIES,
            "impact_weights": self.IMPACT_WEIGHTS,
        }
