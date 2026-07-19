"""
Revenue Operations Feedback Loops.

Three feedback channels that drive continuous improvement:

1. Agent Performance → Prompt Refinement
   - Track agent success rates, latency, error patterns
   - Auto-adjust confidence thresholds and decision parameters
   - Generate performance reports for human review

2. Customer Feedback → Product Improvement
   - Collect CSAT, NPS, and feature requests from onboarding
   - Cluster similar feedback into actionable themes
   - Feed into SelfEvolutionService for feature prioritization

3. Revenue Metrics → Strategy Adjustment
   - Track MRR, churn, pipeline velocity, conversion rates
   - Identify underperforming segments or pricing tiers
   - Auto-adjust lead scoring weights and content strategy

These loops are wired into the EventBus so feedback flows
automatically between agents without manual intervention.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import structlog

from app.agents.base import AgentEvent, EventType

logger = structlog.get_logger(__name__)


# ════════════════════════════════════════════════════════════════════
# Data Models
# ════════════════════════════════════════════════════════════════════


@dataclass
class AgentPerformanceMetric:
    """Performance snapshot for a single agent."""
    agent_name: str = ""
    total_actions: int = 0
    successful_actions: int = 0
    failed_actions: int = 0
    avg_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    error_rate: float = 0.0
    confidence_avg: float = 0.0
    measured_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def success_rate(self) -> float:
        if self.total_actions == 0:
            return 0.0
        return self.successful_actions / self.total_actions

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "total_actions": self.total_actions,
            "success_rate": round(self.success_rate, 4),
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "p95_latency_ms": round(self.p95_latency_ms, 2),
            "error_rate": round(self.error_rate, 4),
            "confidence_avg": round(self.confidence_avg, 3),
        }


@dataclass
class CustomerFeedbackSignal:
    """A structured customer feedback signal."""
    signal_id: str = ""
    client_id: str = ""
    source: str = ""          # onboarding, support, survey, nps
    category: str = ""        # feature_request, bug, praise, complaint
    text: str = ""
    score: float = 0.0        # CSAT (1-5) or NPS (-100 to 100)
    sentiment: float = 0.0    # -1 to 1
    collected_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "client_id": self.client_id,
            "source": self.source,
            "category": self.category,
            "text": self.text[:200],
            "score": self.score,
            "sentiment": self.sentiment,
        }


@dataclass
class RevenueMetric:
    """A point-in-time revenue metric snapshot."""
    metric_name: str = ""
    value: float = 0.0
    period: str = ""          # daily, weekly, monthly
    segment: str = ""         # tier, industry, region
    measured_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric_name": self.metric_name,
            "value": round(self.value, 2),
            "period": self.period,
            "segment": self.segment,
        }


# ════════════════════════════════════════════════════════════════════
# Feedback Loop Manager
# ════════════════════════════════════════════════════════════════════


class FeedbackLoopManager:
    """
    Manages three feedback loops for revenue operations.

    Usage:
        manager = FeedbackLoopManager()

        # Loop 1: Agent performance
        manager.record_agent_performance("LeadQualifier", success=True, latency_ms=45)
        recommendations = manager.get_agent_recommendations("LeadQualifier")

        # Loop 2: Customer feedback
        manager.record_customer_feedback(client_id="abc", text="Great product!", score=5)
        themes = manager.get_feedback_themes()

        # Loop 3: Revenue metrics
        manager.record_revenue_metric("mrr", 150000, "monthly")
        adjustments = manager.get_strategy_adjustments()
    """

    def __init__(self):
        # Loop 1: Agent performance tracking
        self._agent_metrics: dict[str, list[dict[str, Any]]] = defaultdict(list)
        # agent_name → [{success, latency_ms, timestamp}, ...]

        # Loop 2: Customer feedback
        self._customer_feedback: list[CustomerFeedbackSignal] = []

        # Loop 3: Revenue metrics
        self._revenue_metrics: list[RevenueMetric] = []
        self._metric_history: dict[str, list[float]] = defaultdict(list)
        # metric_name → [values over time]

        self._logger = logger.bind(component="feedback_loops")

    # ── Loop 1: Agent Performance ───────────────────────────────────

    def record_agent_performance(
        self,
        agent_name: str,
        success: bool,
        latency_ms: float = 0.0,
        confidence: float = 0.0,
        error: str | None = None,
    ) -> None:
        """Record an agent action outcome."""
        self._agent_metrics[agent_name].append({
            "success": success,
            "latency_ms": latency_ms,
            "confidence": confidence,
            "error": error,
            "timestamp": time.time(),
        })

        # Keep last 1000 per agent
        if len(self._agent_metrics[agent_name]) > 1000:
            self._agent_metrics[agent_name] = self._agent_metrics[agent_name][-1000:]

    def get_agent_performance(self, agent_name: str) -> AgentPerformanceMetric:
        """Get performance metrics for an agent."""
        records = self._agent_metrics.get(agent_name, [])
        if not records:
            return AgentPerformanceMetric(agent_name=agent_name)

        successes = [r for r in records if r["success"]]
        failures = [r for r in records if not r["success"]]
        latencies = [r["latency_ms"] for r in records if r["latency_ms"] > 0]
        confidences = [r["confidence"] for r in records if r["confidence"] > 0]

        sorted_latencies = sorted(latencies)
        p95_idx = int(len(sorted_latencies) * 0.95) if sorted_latencies else 0

        return AgentPerformanceMetric(
            agent_name=agent_name,
            total_actions=len(records),
            successful_actions=len(successes),
            failed_actions=len(failures),
            avg_latency_ms=sum(latencies) / len(latencies) if latencies else 0.0,
            p95_latency_ms=sorted_latencies[p95_idx] if sorted_latencies else 0.0,
            error_rate=len(failures) / len(records) if records else 0.0,
            confidence_avg=sum(confidences) / len(confidences) if confidences else 0.0,
        )

    def get_agent_recommendations(self, agent_name: str) -> dict[str, Any]:
        """
        Generate recommendations for an agent based on performance.

        Returns suggested adjustments to confidence thresholds,
        timeouts, and other parameters.
        """
        metrics = self.get_agent_performance(agent_name)
        recommendations = {
            "agent_name": agent_name,
            "adjustments": [],
            "alerts": [],
        }

        # High error rate → lower confidence threshold
        if metrics.error_rate > 0.2:
            recommendations["adjustments"].append({
                "param": "confidence_threshold",
                "action": "decrease",
                "reason": f"Error rate {metrics.error_rate:.1%} is above 20%",
                "suggested_value": max(0.3, 0.7 - metrics.error_rate),
            })
            recommendations["alerts"].append("high_error_rate")

        # Low latency variance → might be caching or skipping
        if metrics.avg_latency_ms < 10 and metrics.total_actions > 10:
            recommendations["alerts"].append("suspiciously_low_latency")

        # High confidence but low success → recalibrate
        if metrics.confidence_avg > 0.8 and metrics.success_rate < 0.7:
            recommendations["adjustments"].append({
                "param": "confidence_threshold",
                "action": "recalibrate",
                "reason": "Overconfident — high confidence but low success rate",
                "suggested_value": metrics.success_rate,
            })
            recommendations["alerts"].append("overconfident")

        return recommendations

    # ── Loop 2: Customer Feedback ───────────────────────────────────

    def record_customer_feedback(
        self,
        client_id: str,
        text: str,
        score: float = 0.0,
        source: str = "general",
        category: str = "",
    ) -> CustomerFeedbackSignal:
        """Record customer feedback signal."""
        import uuid

        # Auto-classify if no category
        if not category:
            category = self._classify_feedback(text)

        # Simple sentiment scoring
        sentiment = self._score_sentiment(text)

        signal = CustomerFeedbackSignal(
            signal_id=uuid.uuid4().hex[:12],
            client_id=client_id,
            source=source,
            category=category,
            text=text,
            score=score,
            sentiment=sentiment,
        )

        self._customer_feedback.append(signal)

        # Keep last 5000
        if len(self._customer_feedback) > 5000:
            self._customer_feedback = self._customer_feedback[-5000:]

        self._logger.info(
            "customer_feedback_recorded",
            client_id=client_id,
            category=category,
            score=score,
            sentiment=round(sentiment, 2),
        )

        return signal

    def get_feedback_themes(self, min_count: int = 2) -> list[dict[str, Any]]:
        """
        Cluster customer feedback into themes.

        Returns the most common feedback categories with
        representative examples and average sentiment.
        """
        if not self._customer_feedback:
            return []

        # Group by category
        by_category: dict[str, list[CustomerFeedbackSignal]] = defaultdict(list)
        for signal in self._customer_feedback:
            by_category[signal.category].append(signal)

        themes = []
        for category, signals in sorted(
            by_category.items(),
            key=lambda x: len(x[1]),
            reverse=True,
        ):
            if len(signals) < min_count:
                continue

            avg_sentiment = sum(s.sentiment for s in signals) / len(signals)
            avg_score = sum(s.score for s in signals if s.score > 0)
            scored_count = sum(1 for s in signals if s.score > 0)

            themes.append({
                "category": category,
                "count": len(signals),
                "avg_sentiment": round(avg_sentiment, 3),
                "avg_csat": round(avg_score / scored_count, 2) if scored_count else 0,
                "sample_texts": [s.text[:100] for s in signals[:3]],
                "recent_count_7d": sum(
                    1 for s in signals
                    if (datetime.now(UTC) - s.collected_at).days <= 7
                ),
            })

        return themes

    def get_nps_score(self) -> dict[str, Any]:
        """Calculate Net Promoter Score from feedback."""
        scored = [s for s in self._customer_feedback if s.score > 0]
        if not scored:
            return {"nps": 0, "promoters": 0, "detractors": 0, "total": 0}

        # NPS: score 9-10 = promoter, 0-6 = detractor, 7-8 = passive
        promoters = sum(1 for s in scored if s.score >= 9)
        detractors = sum(1 for s in scored if s.score <= 6)
        total = len(scored)
        nps = ((promoters - detractors) / total) * 100

        return {
            "nps": round(nps, 1),
            "promoters": promoters,
            "detractors": detractors,
            "passives": total - promoters - detractors,
            "total": total,
        }

    # ── Loop 3: Revenue Metrics ─────────────────────────────────────

    def record_revenue_metric(
        self,
        metric_name: str,
        value: float,
        period: str = "monthly",
        segment: str = "",
    ) -> RevenueMetric:
        """Record a revenue metric data point."""
        metric = RevenueMetric(
            metric_name=metric_name,
            value=value,
            period=period,
            segment=segment,
        )
        self._revenue_metrics.append(metric)
        self._metric_history[metric_name].append(value)

        # Keep last 1000 per metric
        if len(self._metric_history[metric_name]) > 1000:
            self._metric_history[metric_name] = self._metric_history[metric_name][-1000:]

        return metric

    def get_revenue_dashboard(self) -> dict[str, Any]:
        """
        Generate a revenue operations dashboard.

        Shows key metrics, trends, and alerts.
        """
        dashboard = {
            "generated_at": datetime.now(UTC).isoformat(),
            "metrics": {},
            "trends": {},
            "alerts": [],
        }

        # Latest values for each metric
        latest_by_name: dict[str, RevenueMetric] = {}
        for metric in reversed(self._revenue_metrics):
            if metric.metric_name not in latest_by_name:
                latest_by_name[metric.metric_name] = metric

        for name, metric in latest_by_name.items():
            dashboard["metrics"][name] = metric.to_dict()

        # Trends (compare last 2 values)
        for name, values in self._metric_history.items():
            if len(values) >= 2:
                current = values[-1]
                previous = values[-2]
                change_pct = ((current - previous) / previous * 100) if previous else 0
                dashboard["trends"][name] = {
                    "current": round(current, 2),
                    "previous": round(previous, 2),
                    "change_pct": round(change_pct, 1),
                    "direction": "up" if change_pct > 0 else "down" if change_pct < 0 else "flat",
                }

                # Alerts
                if change_pct < -10:
                    dashboard["alerts"].append({
                        "metric": name,
                        "type": "decline",
                        "message": f"{name} declined {abs(change_pct):.1f}%",
                    })

        return dashboard

    def get_strategy_adjustments(self) -> dict[str, Any]:
        """
        Generate strategy adjustment recommendations from revenue data.

        Returns suggested changes to:
        - Lead scoring weights
        - Content strategy
        - Pricing
        - Target segments
        """
        adjustments = {
            "lead_scoring": {},
            "content_strategy": {},
            "pricing": {},
            "segments": [],
        }

        # Analyze MRR trend
        mrr_history = self._metric_history.get("mrr", [])
        if len(mrr_history) >= 2:
            mrr_change = (mrr_history[-1] - mrr_history[-2]) / mrr_history[-2] if mrr_history[-2] else 0
            if mrr_change < -0.05:
                adjustments["lead_scoring"]["action"] = "lower_thresholds"
                adjustments["lead_scoring"]["reason"] = "MRR declining — widen the funnel"
            elif mrr_change > 0.1:
                adjustments["lead_scoring"]["action"] = "raise_thresholds"
                adjustments["lead_scoring"]["reason"] = "MRR growing — focus on quality"

        # Analyze conversion rate
        conv_history = self._metric_history.get("conversion_rate", [])
        if conv_history and conv_history[-1] < 0.1:
            adjustments["content_strategy"]["action"] = "increase_education"
            adjustments["content_strategy"]["reason"] = "Low conversion — need more nurturing content"

        # Analyze churn
        churn_history = self._metric_history.get("churn_rate", [])
        if churn_history and churn_history[-1] > 0.1:
            adjustments["segments"].append({
                "action": "investigate_high_churn",
                "reason": f"Churn rate {churn_history[-1]:.1%} is above 10%",
            })

        return adjustments

    # ── EventBus integration ────────────────────────────────────────

    def create_performance_event(
        self,
        agent_name: str,
        success: bool,
        latency_ms: float,
        confidence: float = 0.0,
    ) -> AgentEvent:
        """Create an EventBus event for agent performance."""
        return AgentEvent(
            event_type=EventType.AGENT_PERFORMANCE_RECORDED,
            source="FeedbackLoopManager",
            payload={
                "agent_name": agent_name,
                "success": success,
                "latency_ms": latency_ms,
                "confidence": confidence,
            },
        )

    def create_feedback_event(self, signal: CustomerFeedbackSignal) -> AgentEvent:
        """Create an EventBus event for customer feedback."""
        return AgentEvent(
            event_type=EventType.CUSTOMER_FEEDBACK_RECEIVED,
            source="FeedbackLoopManager",
            payload=signal.to_dict(),
        )

    def create_revenue_event(self, metric: RevenueMetric) -> AgentEvent:
        """Create an EventBus event for revenue metrics."""
        return AgentEvent(
            event_type=EventType.REVENUE_METRIC_RECORDED,
            source="FeedbackLoopManager",
            payload=metric.to_dict(),
        )

    # ── Internal helpers ────────────────────────────────────────────

    @staticmethod
    def _classify_feedback(text: str) -> str:
        """Auto-classify feedback text."""
        text_lower = text.lower()
        if any(w in text_lower for w in ["feature", "wish", "add", "want", "need"]):
            return "feature_request"
        if any(w in text_lower for w in ["bug", "broken", "error", "doesn't work"]):
            return "bug"
        if any(w in text_lower for w in ["great", "love", "amazing", "thank", "excellent"]):
            return "praise"
        if any(w in text_lower for w in ["slow", "bad", "terrible", "frustrating", "hate"]):
            return "complaint"
        if any(w in text_lower for w in ["price", "cost", "expensive", "cheap", "value"]):
            return "pricing_feedback"
        return "general"

    @staticmethod
    def _score_sentiment(text: str) -> float:
        """Score sentiment from -1 (negative) to 1 (positive)."""
        text_lower = text.lower()
        positive = ["good", "great", "love", "amazing", "helpful", "thank", "perfect", "excellent"]
        negative = ["bad", "hate", "terrible", "slow", "broken", "wrong", "frustrating", "poor"]
        pos = sum(1 for w in positive if w in text_lower)
        neg = sum(1 for w in negative if w in text_lower)
        if pos + neg == 0:
            return 0.0
        return round((pos - neg) / (pos + neg), 3)
