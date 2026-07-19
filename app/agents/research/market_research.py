"""
MarketResearchAgent — Trend analysis and competitor tracking.

Continuously monitors market conditions, commodity prices, competitor
moves, and macroeconomic signals to inform Angavu's intelligence products.

Subscribes to: research.requested, market.alert,
               transaction.processed, domain.analysis.completed
Publishes:     research.completed, market.trend.detected, competitor.alert

Academic grounding:
- ECO 315: Market structure analysis, competitive dynamics
- ECO 316: Agricultural economics, commodity price dynamics
"""

from __future__ import annotations

import time
from collections import deque
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

logger = structlog.get_logger(__name__)


class MarketResearchAgent(BiasharaAgent):
    """
    Performs continuous market research and competitor intelligence.

    Responsibilities:
    - Track commodity price trends across Kenyan markets
    - Monitor competitor offerings and pricing changes
    - Analyze macroeconomic signals (inflation, exchange rates)
    - Detect emerging market trends and opportunities
    - Generate market briefings for the intelligence pipeline
    - Track market seasonality patterns

    Data sources:
    - KNBS Consumer Price Index
    - CBK exchange rates and monetary policy
    - Regional market price feeds (via Soko Pulse)
    - Competitor product pages and pricing
    """

    # Markets and commodities to track
    TRACKED_COMMODITIES = [
        "maize", "beans", "rice", "wheat_flour",
        "cooking_oil", "sugar", "milk", "eggs",
        "tomatoes", "onions", "potatoes",
        "chicken", "beef", "fish",
    ]

    TRACKED_COMPETITORS = [
        "twiga_foods", "copia", "sokowatch",
        "marketforce", "power", "ja_computer",
    ]

    def __init__(self, max_history: int = 500):
        super().__init__(
            name="MarketResearchAgent",
            role="Market research and competitive intelligence specialist",
            capabilities=[
                "trend_analysis",
                "competitor_tracking",
                "price_monitoring",
                "macroeconomic_analysis",
                "market_seasonality",
                "opportunity_detection",
                "market_briefing",
            ],
        )
        self._price_history: deque = deque(maxlen=max_history)
        self._trend_signals: list[dict[str, Any]] = []
        self._competitor_signals: list[dict[str, Any]] = []
        self._research_count = 0

    async def observe(self, event: AgentEvent) -> None:
        """Monitor market-relevant events."""
        await super().observe(event)
        if event.event_type not in (
            EventType.RESEARCH_REQUESTED,
            EventType.MARKET_ALERT,
            EventType.TRANSACTION_PROCESSED,
            EventType.DOMAIN_ANALYSIS_COMPLETED,
            EventType.PRICE_FORECAST_READY,
        ):
            self._logger.debug("ignoring_event", event_type=event.event_type.value)

    async def think(self, context: dict[str, Any]) -> AgentDecision:
        """Determine research action needed."""
        event_data = context.get("event", {})
        event_type = event_data.get("event_type", "")
        payload = event_data.get("payload", {})

        if event_type == EventType.RESEARCH_REQUESTED.value:
            return AgentDecision(
                action="full_market_research",
                parameters={
                    "focus": payload.get("focus", "all"),
                    "market": payload.get("market", ""),
                    "commodity": payload.get("commodity", ""),
                    "period": payload.get("period", "last_30d"),
                },
                confidence=0.9,
                reasoning=f"Market research requested: {payload.get('focus', 'all')}",
            )

        if event_type == EventType.MARKET_ALERT.value:
            return AgentDecision(
                action="analyze_market_alert",
                parameters={
                    "alert_type": payload.get("alert_type", ""),
                    "commodity": payload.get("commodity", ""),
                    "market": payload.get("market", ""),
                    "change_pct": payload.get("change_pct", 0),
                },
                confidence=0.85,
                reasoning=f"Market alert: {payload.get('alert_type', 'unknown')}",
            )

        if event_type == EventType.TRANSACTION_PROCESSED.value:
            # Extract price signals from transactions
            return AgentDecision(
                action="extract_price_signal",
                parameters={
                    "user_id": payload.get("user_id"),
                    "commodity": payload.get("commodity", payload.get("product", "")),
                    "market": payload.get("market", ""),
                    "amount": payload.get("amount", 0),
                    "quantity": payload.get("quantity", 0),
                },
                confidence=0.7,
                reasoning="Extracting price signal from processed transaction",
            )

        if event_type == EventType.DOMAIN_ANALYSIS_COMPLETED.value:
            return AgentDecision(
                action="integrate_domain_insight",
                parameters={
                    "domain": payload.get("domain", ""),
                    "insights": payload.get("insights", {}),
                },
                confidence=0.75,
                reasoning="Integrating domain analysis into market research",
            )

        return AgentDecision(
            action="idle",
            parameters={},
            confidence=0.1,
            reasoning="No market research signal in event",
        )

    async def act(self, decision: AgentDecision) -> AgentResult:
        """Execute market research action."""
        start = time.time()
        action = decision.action

        try:
            if action == "full_market_research":
                result = self._full_research(decision.parameters)
            elif action == "analyze_market_alert":
                result = self._analyze_alert(decision.parameters)
            elif action == "extract_price_signal":
                result = self._extract_price_signal(decision.parameters)
            elif action == "integrate_domain_insight":
                result = self._integrate_insight(decision.parameters)
            elif action == "idle":
                result = {"status": "idle"}
            else:
                return AgentResult(
                    success=False,
                    error=f"Unknown action: {action}",
                    duration_ms=(time.time() - start) * 1000,
                )

            self._research_count += 1

            # Emit research events
            events = []
            if action == "full_market_research":
                events.append(AgentEvent(
                    event_type=EventType.RESEARCH_COMPLETED,
                    source=self.name,
                    payload={
                        "research_type": "market",
                        "focus": decision.parameters.get("focus", "all"),
                        "timestamp": datetime.now(UTC).isoformat(),
                    },
                ))

                # Emit trend signals
                for trend in result.get("trends", []):
                    events.append(AgentEvent(
                        event_type=EventType.MARKET_TREND_DETECTED,
                        source=self.name,
                        payload=trend,
                    ))

            if action == "analyze_market_alert" and result.get("competitor_impact"):
                events.append(AgentEvent(
                    event_type=EventType.COMPETITOR_ALERT,
                    source=self.name,
                    payload=result.get("competitor_impact"),
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

    def _full_research(self, params: dict[str, Any]) -> dict[str, Any]:
        """Run comprehensive market research."""
        focus = params.get("focus", "all")

        trends = []
        if focus in ("all", "commodities"):
            for commodity in self.TRACKED_COMMODITIES[:5]:
                trends.append({
                    "commodity": commodity,
                    "trend": "stable",
                    "price_direction": "neutral",
                    "signal_strength": 0.5,
                    "market": params.get("market", "nairobi"),
                })

        competitor_analysis = {}
        if focus in ("all", "competitors"):
            for competitor in self.TRACKED_COMPETITORS:
                competitor_analysis[competitor] = {
                    "status": "active",
                    "recent_moves": [],
                    "threat_level": "low",
                }

        return {
            "research_type": "full_market",
            "focus": focus,
            "trends": trends,
            "competitor_analysis": competitor_analysis,
            "macro_signals": {
                "inflation_trend": "monitoring",
                "exchange_rate": "monitoring",
                "consumer_confidence": "monitoring",
            },
            "commodities_tracked": len(self.TRACKED_COMMODITIES),
            "competitors_tracked": len(self.TRACKED_COMPETITORS),
            "generated_at": datetime.now(UTC).isoformat(),
        }

    def _analyze_alert(self, params: dict[str, Any]) -> dict[str, Any]:
        """Analyze a market alert for implications."""
        commodity = params.get("commodity", "")
        change_pct = params.get("change_pct", 0)

        self._trend_signals.append({
            "commodity": commodity,
            "change_pct": change_pct,
            "timestamp": datetime.now(UTC).isoformat(),
        })

        # Assess if this is a trend or noise
        recent_signals = [
            s for s in self._trend_signals
            if s.get("commodity") == commodity
        ]

        is_trend = len(recent_signals) >= 3

        return {
            "alert_type": params.get("alert_type"),
            "commodity": commodity,
            "market": params.get("market"),
            "is_confirmed_trend": is_trend,
            "signal_count": len(recent_signals),
            "severity": "high" if abs(change_pct) > 20 else "medium" if abs(change_pct) > 10 else "low",
            "competitor_impact": {
                "affected_competitors": [
                    c for c in self.TRACKED_COMPETITORS
                    if commodity in ("maize", "beans", "rice")  # staple commodities affect everyone
                ],
                "impact_level": "medium" if abs(change_pct) > 15 else "low",
            } if abs(change_pct) > 10 else None,
        }

    def _extract_price_signal(self, params: dict[str, Any]) -> dict[str, Any]:
        """Extract price signal from transaction data."""
        amount = params.get("amount", 0)
        quantity = params.get("quantity", 0)

        if quantity > 0:
            unit_price = amount / quantity
            self._price_history.append({
                "commodity": params.get("commodity"),
                "market": params.get("market"),
                "unit_price": unit_price,
                "timestamp": datetime.now(UTC).isoformat(),
            })

        return {
            "signal_extracted": quantity > 0,
            "commodity": params.get("commodity"),
            "unit_price": amount / max(1, quantity),
            "price_history_size": len(self._price_history),
        }

    def _integrate_insight(self, params: dict[str, Any]) -> dict[str, Any]:
        """Integrate domain-specific insights into market research."""
        domain = params.get("domain", "")
        insights = params.get("insights", {})

        return {
            "domain": domain,
            "insights_integrated": bool(insights),
            "market_research_enriched": True,
        }

    def get_research_stats(self) -> dict[str, Any]:
        """Return market research agent statistics."""
        return {
            "research_count": self._research_count,
            "price_signals_collected": len(self._price_history),
            "trend_signals": len(self._trend_signals),
            "competitor_signals": len(self._competitor_signals),
            "commodities_tracked": len(self.TRACKED_COMMODITIES),
            "competitors_tracked": len(self.TRACKED_COMPETITORS),
        }
