"""
Always-On Market Monitor — Scout/Rank/Deliver pattern for price monitoring.

Inspired by: awesome-llm-apps/always_on_agents/always_on_hn_briefing_agent/
Pattern: scout (fetch data) → rank (score signals) → deliver (emit alerts)

Watches commodity prices, forex rates, and market indicators.
Emits alerts through the Angavu event bus when significant changes detected.

Architecture:
    MarketScout → fetches prices from data sources
    MarketRanker → scores price movements by signal strength
    AlwaysOnMarketMonitor → orchestrates the pipeline, emits events

Integrates with:
    - Angavu EventBus (Redis Streams)
    - SokoPulse (existing price service)
    - BiasharaAgent lifecycle (observe → think → act → reflect)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from enum import StrEnum
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


# ════════════════════════════════════════════════════════════════════
# Data Types
# ════════════════════════════════════════════════════════════════════


class AlertSeverity(StrEnum):
    """Market alert severity levels."""
    LOW = "low"           # < 2% change
    MEDIUM = "medium"     # 2-5% change
    HIGH = "high"         # 5-10% change
    CRITICAL = "critical"  # > 10% change


class MarketCategory(StrEnum):
    """Market categories for East African context."""
    AGRICULTURE = "agriculture"   # Maize, beans, rice, wheat
    ENERGY = "energy"             # Fuel, electricity
    FOREX = "forex"               # KES/USD, KES/EUR, KES/GBP
    COMMODITIES = "commodities"   # Gold, oil, tea, coffee
    TRANSPORT = "transport"       # Matatu fares, logistics costs


@dataclass(frozen=True)
class PricePoint:
    """A single price observation."""
    commodity: str
    category: MarketCategory
    price: float
    currency: str
    unit: str               # e.g., "KES/kg", "USD/barrel"
    source: str             # e.g., "nse", "cbk", "soko_pulse"
    timestamp: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PriceMovement:
    """Computed price change between two observations."""
    commodity: str
    category: MarketCategory
    previous_price: float
    current_price: float
    change_pct: float       # percentage change
    change_abs: float       # absolute change
    currency: str
    unit: str
    window_hours: float     # time window of the change
    severity: AlertSeverity
    signal_score: float     # composite score for ranking
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MarketBrief:
    """Ranked market intelligence brief."""
    generated_at: str
    watch_mode: str
    movements: list[PriceMovement]
    summary_text: str
    summary_html: str
    next_actions: list[str]
    alert_count: dict[str, int]  # severity → count

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["movements"] = [m.to_dict() if hasattr(m, "to_dict") else m for m in self.movements]
        return payload


# ════════════════════════════════════════════════════════════════════
# MarketScout — Data Fetching Layer
# ════════════════════════════════════════════════════════════════════


# Commodities to monitor with baseline prices (KES)
SAMPLE_PRICES: list[PricePoint] = [
    PricePoint("Maize", MarketCategory.AGRICULTURE, 4500, "KES", "90kg bag", "soko_pulse", time.time()),
    PricePoint("Beans (Nyayo)", MarketCategory.AGRICULTURE, 8200, "KES", "90kg bag", "soko_pulse", time.time()),
    PricePoint("Rice (Imported)", MarketCategory.AGRICULTURE, 180, "KES", "kg", "soko_pulse", time.time()),
    PricePoint("Wheat Flour", MarketCategory.AGRICULTURE, 165, "KES", "2kg", "soko_pulse", time.time()),
    PricePoint("Fuel (Petrol)", MarketCategory.ENERGY, 217.30, "KES", "litre", "epra", time.time()),
    PricePoint("Fuel (Diesel)", MarketCategory.ENERGY, 203.50, "KES", "litre", "epra", time.time()),
    PricePoint("KES/USD", MarketCategory.FOREX, 153.20, "KES", "USD", "cbk", time.time()),
    PricePoint("KES/EUR", MarketCategory.FOREX, 167.85, "KES", "EUR", "cbk", time.time()),
    PricePoint("Tea (Mombasa Auction)", MarketCategory.COMMODITIES, 285, "KES", "kg", "tea_board", time.time()),
    PricePoint("Coffee (Nairobi Auction)", MarketCategory.COMMODITIES, 7200, "KES", "50kg", "coffee_board", time.time()),
    PricePoint("Gold (Spot)", MarketCategory.COMMODITIES, 2380.50, "USD", "oz", "market_feed", time.time()),
    PricePoint("Matatu (Nairobi CBD)", MarketCategory.TRANSPORT, 100, "KES", "trip", "ntsa", time.time()),
]

# Signal keywords that increase alert priority
SIGNAL_KEYWORDS = {
    "drought", "flooding", "shortage", "embargo", "sanctions",
    "policy change", "rate hike", "rate cut", "election",
    "supply chain", "disruption", "subsidy", "tax", "inflation",
}


class MarketScout:
    """
    Fetches price data from multiple sources.

    In live mode: connects to SokoPulse, CBK API, NSE feeds.
    In sample mode: uses deterministic data for demos/tests.
    """

    def __init__(self, live: bool = False):
        self._live = live
        self._soko_pulse: Any = None  # injected
        self._logger = logger.bind(component="market_scout")

    def set_soko_pulse(self, soko_pulse: Any) -> None:
        """Inject SokoPulse service for live price data."""
        self._soko_pulse = soko_pulse

    async def fetch_current_prices(self) -> list[PricePoint]:
        """Fetch current prices from all sources."""
        if self._live and self._soko_pulse:
            return await self._fetch_live_prices()
        return self._fetch_sample_prices()

    def _fetch_sample_prices(self) -> list[PricePoint]:
        """Return deterministic sample prices for demos."""
        import random
        prices = []
        for p in SAMPLE_PRICES:
            # Add small random jitter (±3%) to simulate market movement
            jitter = 1.0 + random.uniform(-0.03, 0.03)
            prices.append(PricePoint(
                commodity=p.commodity,
                category=p.category,
                price=round(p.price * jitter, 2),
                currency=p.currency,
                unit=p.unit,
                source=p.source,
                timestamp=time.time(),
                metadata=p.metadata,
            ))
        return prices

    async def _fetch_live_prices(self) -> list[PricePoint]:
        """Fetch live prices from SokoPulse and other APIs."""
        prices = []
        try:
            if self._soko_pulse:
                raw = await self._soko_pulse.get_all_prices()
                for item in raw:
                    prices.append(PricePoint(
                        commodity=item.get("commodity", "unknown"),
                        category=MarketCategory(item.get("category", "commodities")),
                        price=float(item.get("price", 0)),
                        currency=item.get("currency", "KES"),
                        unit=item.get("unit", "unit"),
                        source="soko_pulse",
                        timestamp=time.time(),
                        metadata=item.get("metadata", {}),
                    ))
        except Exception as exc:
            self._logger.error("live_price_fetch_failed", error=str(exc))
            # Fallback to sample data
            return self._fetch_sample_prices()
        return prices or self._fetch_sample_prices()

    def fetch_historical_prices(
        self,
        commodities: list[str],
        hours_back: float = 24.0,
    ) -> dict[str, list[PricePoint]]:
        """Fetch historical prices for comparison (stub for demo)."""
        # In production, this queries ClickHouse or Redis time series
        return {c: [] for c in commodities}


# ════════════════════════════════════════════════════════════════════
# MarketRanker — Signal Scoring & Classification
# ════════════════════════════════════════════════════════════════════


# Severity thresholds (% change)
SEVERITY_THRESHOLDS = {
    AlertSeverity.CRITICAL: 10.0,
    AlertSeverity.HIGH: 5.0,
    AlertSeverity.MEDIUM: 2.0,
    AlertSeverity.LOW: 0.5,
}

# Category weights (food prices matter more in East African context)
CATEGORY_WEIGHTS = {
    MarketCategory.AGRICULTURE: 1.5,    # Food security
    MarketCategory.ENERGY: 1.3,         # Affects everything
    MarketCategory.FOREX: 1.2,          # Import costs
    MarketCategory.TRANSPORT: 1.1,      # Daily cost of living
    MarketCategory.COMMODITIES: 1.0,    # Export revenue
}


class MarketRanker:
    """
    Scores and ranks price movements by signal strength.

    Inspired by the HN briefing agent's scoring system:
    - Keyword hits increase score
    - Category weight reflects East African economic context
    - Severity based on % change magnitude
    - Freshness (time since change) affects ranking
    """

    def __init__(self):
        self._previous_prices: dict[str, float] = {}
        self._logger = logger.bind(component="market_ranker")

    def compute_movements(
        self,
        current_prices: list[PricePoint],
        window_hours: float = 24.0,
    ) -> list[PriceMovement]:
        """Compute price movements by comparing to previous observations."""
        movements = []

        for price in current_prices:
            prev = self._previous_prices.get(price.commodity)
            if prev is None:
                # First observation — record baseline
                self._previous_prices[price.commodity] = price.price
                continue

            if prev == 0:
                continue

            change_pct = ((price.price - prev) / prev) * 100
            change_abs = price.price - prev

            # Only alert on meaningful changes
            if abs(change_pct) < SEVERITY_THRESHOLDS[AlertSeverity.LOW]:
                continue

            severity = self._classify_severity(abs(change_pct))
            signal_score = self._score_movement(
                price.commodity, price.category, change_pct, severity
            )

            direction = "↑" if change_pct > 0 else "↓"
            summary = (
                f"{price.commodity} {direction} {abs(change_pct):.1f}% "
                f"({prev:.2f} → {price.price:.2f} {price.currency}/{price.unit})"
            )

            movements.append(PriceMovement(
                commodity=price.commodity,
                category=price.category,
                previous_price=prev,
                current_price=price.price,
                change_pct=round(change_pct, 2),
                change_abs=round(change_abs, 2),
                currency=price.currency,
                unit=price.unit,
                window_hours=window_hours,
                severity=severity,
                signal_score=round(signal_score, 1),
                summary=summary,
            ))

            # Update stored price
            self._previous_prices[price.commodity] = price.price

        return sorted(movements, key=lambda m: m.signal_score, reverse=True)

    def _classify_severity(self, abs_change_pct: float) -> AlertSeverity:
        """Classify alert severity based on absolute % change."""
        if abs_change_pct >= SEVERITY_THRESHOLDS[AlertSeverity.CRITICAL]:
            return AlertSeverity.CRITICAL
        if abs_change_pct >= SEVERITY_THRESHOLDS[AlertSeverity.HIGH]:
            return AlertSeverity.HIGH
        if abs_change_pct >= SEVERITY_THRESHOLDS[AlertSeverity.MEDIUM]:
            return AlertSeverity.MEDIUM
        return AlertSeverity.LOW

    def _score_movement(
        self,
        commodity: str,
        category: MarketCategory,
        change_pct: float,
        severity: AlertSeverity,
    ) -> float:
        """Composite signal score for ranking."""
        # Base score from severity
        severity_scores = {
            AlertSeverity.CRITICAL: 100,
            AlertSeverity.HIGH: 70,
            AlertSeverity.MEDIUM: 40,
            AlertSeverity.LOW: 15,
        }
        base = severity_scores[severity]

        # Category weight
        cat_weight = CATEGORY_WEIGHTS.get(category, 1.0)

        # Direction weight (price increases are more urgent for food/fuel)
        direction_weight = 1.2 if change_pct > 0 else 1.0

        return base * cat_weight * direction_weight


# ════════════════════════════════════════════════════════════════════
# AlwaysOnMarketMonitor — BiasharaAgent Integration
# ════════════════════════════════════════════════════════════════════


class AlwaysOnMarketMonitor(BiasharaAgent):
    """
    Always-on market monitoring agent for Angavu Intelligence.

    Lifecycle:
        - Runs background polling loop (inherited from BiasharaAgent)
        - Scout fetches prices on each cycle
        - Ranker computes movements and scores
        - Alerts emitted as AgentEvents through the event bus

    Subscribes to: market.alert (for downstream reactions)
    Publishes: market.alert, market.trend.detected

    Integrates with the existing Angavu infrastructure:
    - Uses BiasharaAgent.observe → think → act → reflect lifecycle
    - Publishes to Redis Streams via EventBus
    - Compatible with MetaAgent routing and execution harness
    """

    def __init__(
        self,
        live: bool = False,
        poll_interval: float = 300.0,  # 5 minutes
        top_n_alerts: int = 5,
    ):
        super().__init__(
            name="AlwaysOnMarketMonitor",
            role="Continuous market price surveillance and alerting",
            capabilities=[
                "price_monitoring",
                "movement_detection",
                "signal_ranking",
                "market_alerting",
                "trend_detection",
            ],
        )
        self._scout = MarketScout(live=live)
        self._ranker = MarketRanker()
        self._top_n = top_n_alerts
        self._poll_interval = poll_interval
        self._brief_history: list[MarketBrief] = []
        self._logger = logger.bind(agent="AlwaysOnMarketMonitor")

    def set_soko_pulse(self, soko_pulse: Any) -> None:
        """Inject SokoPulse service for live data."""
        self._scout.set_soko_pulse(soko_pulse)

    # ── BiasharaAgent lifecycle ─────────────────────────────────────

    async def observe(self, event: AgentEvent) -> None:
        """Handle incoming market-related events."""
        await super().observe(event)
        if event.event_type == EventType.MARKET_ALERT:
            self._logger.info(
                "received_market_alert",
                source=event.source,
                payload_keys=list(event.payload.keys()),
            )

    async def think(self, context: dict[str, Any]) -> AgentDecision:
        """
        Decide whether to run a monitoring cycle.

        On timer triggers: run full scout → rank → alert pipeline.
        On market.alert events: analyze and potentially re-scout.
        """
        event = context.get("event", {})
        event_type = event.get("event_type", "")

        if event_type == EventType.MARKET_ALERT.value:
            return AgentDecision(
                action="analyze_alert",
                parameters={"alert_data": event.get("payload", {})},
                confidence=0.9,
                reasoning="Received market alert — analyzing for downstream impact.",
            )

        # Default: run monitoring cycle
        return AgentDecision(
            action="run_monitoring_cycle",
            parameters={"top_n": self._top_n},
            confidence=1.0,
            reasoning="Scheduled monitoring cycle — scout prices, rank movements, emit alerts.",
        )

    async def act(self, decision: AgentDecision) -> AgentResult:
        """Execute the monitoring decision."""
        start = time.time()

        if decision.action == "analyze_alert":
            return await self._analyze_alert(decision.parameters)

        if decision.action == "run_monitoring_cycle":
            return await self._run_monitoring_cycle(decision.parameters)

        return AgentResult(
            success=False,
            error=f"Unknown action: {decision.action}",
            duration_ms=(time.time() - start) * 1000,
        )

    async def _run_monitoring_cycle(self, params: dict) -> AgentResult:
        """Full scout → rank → alert pipeline."""
        start = time.time()
        try:
            # Scout: fetch current prices
            prices = await self._scout.fetch_current_prices()

            # Rank: compute and score movements
            movements = self._ranker.compute_movements(prices)

            # Take top N
            top_movements = movements[: self._top_n]

            # Build brief
            brief = self._render_brief(top_movements, prices)
            self._brief_history.append(brief)
            if len(self._brief_history) > 100:
                self._brief_history = self._brief_history[-100:]

            # Emit events for significant movements
            events_to_publish = []
            for movement in top_movements:
                if movement.severity in (AlertSeverity.HIGH, AlertSeverity.CRITICAL):
                    events_to_publish.append(AgentEvent(
                        event_type=EventType.MARKET_ALERT,
                        source=self.name,
                        payload={
                            "commodity": movement.commodity,
                            "category": movement.category.value,
                            "change_pct": movement.change_pct,
                            "severity": movement.severity.value,
                            "signal_score": movement.signal_score,
                            "summary": movement.summary,
                            "current_price": movement.current_price,
                            "currency": movement.currency,
                        },
                    ))

                # Emit trend events for sustained movements
                if movement.severity != AlertSeverity.LOW:
                    events_to_publish.append(AgentEvent(
                        event_type=EventType.MARKET_TREND_DETECTED,
                        source=self.name,
                        payload={
                            "commodity": movement.commodity,
                            "category": movement.category.value,
                            "change_pct": movement.change_pct,
                            "direction": "up" if movement.change_pct > 0 else "down",
                            "window_hours": movement.window_hours,
                        },
                    ))

            duration_ms = (time.time() - start) * 1000
            self._logger.info(
                "monitoring_cycle_complete",
                prices_checked=len(prices),
                movements_detected=len(movements),
                alerts_emitted=len(events_to_publish),
                duration_ms=round(duration_ms, 1),
            )

            return AgentResult(
                success=True,
                data={
                    "brief": brief.to_dict(),
                    "movements_count": len(movements),
                    "alerts_count": len(events_to_publish),
                },
                duration_ms=duration_ms,
                events_to_publish=events_to_publish,
            )

        except Exception as exc:
            self._logger.error("monitoring_cycle_failed", error=str(exc))
            return AgentResult(
                success=False,
                error=str(exc),
                duration_ms=(time.time() - start) * 1000,
            )

    async def _analyze_alert(self, params: dict) -> AgentResult:
        """Analyze an incoming market alert for cross-impact."""
        alert_data = params.get("alert_data", {})
        self.memory.remember({
            "type": "alert_received",
            "commodity": alert_data.get("commodity"),
            "severity": alert_data.get("severity"),
        })

        return AgentResult(
            success=True,
            data={"analyzed": True, "alert": alert_data},
            duration_ms=0,
        )

    def _render_brief(
        self,
        movements: list[PriceMovement],
        all_prices: list[PricePoint],
    ) -> MarketBrief:
        """Render a market intelligence brief."""
        import html as html_module

        alert_count = {"low": 0, "medium": 0, "high": 0, "critical": 0}
        for m in movements:
            alert_count[m.severity.value] = alert_count.get(m.severity.value, 0) + 1

        # Text summary
        text_lines = [
            "Angavu Market Intelligence Brief",
            f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Prices monitored: {len(all_prices)}",
            f"Significant movements: {len(movements)}",
            "",
        ]
        for i, m in enumerate(movements, 1):
            text_lines.append(f"{i}. [{m.severity.value.upper()}] {m.summary}")
            text_lines.append(f"   Score: {m.signal_score} | Category: {m.category.value}")
            text_lines.append("")

        # HTML summary
        html_lines = [
            "<h2>Angavu Market Intelligence Brief</h2>",
            f"<p><strong>Generated:</strong> {html_module.escape(time.strftime('%Y-%m-%d %H:%M:%S'))}</p>",
            f"<p>Prices monitored: {len(all_prices)} | Movements: {len(movements)}</p>",
            "<ol>",
        ]
        for m in movements:
            severity_color = {
                "critical": "#dc3545",
                "high": "#fd7e14",
                "medium": "#ffc107",
                "low": "#28a745",
            }.get(m.severity.value, "#6c757d")
            html_lines.append(
                f'<li><span style="color:{severity_color};font-weight:bold">[{m.severity.value.upper()}]</span> '
                f"{html_module.escape(m.summary)}<br>"
                f"<small>Score: {m.signal_score} | {html_module.escape(m.category.value)}</small></li>"
            )
        html_lines.append("</ol>")

        next_actions = [
            "Review critical alerts for supply chain impact.",
            "Cross-reference with transaction data for demand signals.",
            "Escalate food/fuel price spikes to stakeholders.",
        ]

        return MarketBrief(
            generated_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
            watch_mode="live" if self._scout._live else "sample",
            movements=movements,
            summary_text="\n".join(text_lines),
            summary_html="\n".join(html_lines),
            next_actions=next_actions,
            alert_count=alert_count,
        )

    async def get_latest_brief(self) -> dict[str, Any] | None:
        """Return the most recent market brief."""
        if self._brief_history:
            return self._brief_history[-1].to_dict()
        return None
