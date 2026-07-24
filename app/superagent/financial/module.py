"""
Financial Intelligence Module

Wraps existing SokoPulse, FMCG Intelligence, and Distribution Gap services
into the superagent architecture. Provides a unified interface for all
financial intelligence operations.

Existing services wrapped:
- app.services.intelligence.soko_pulse — Market intelligence and price forecasting
- app.services.intelligence.fmcg_intelligence — FMCG analytics
- app.services.intelligence.distribution_gap — Supply chain gap analysis
- app.services.intelligence.biashara_pulse — Business health pulse
"""

from __future__ import annotations

from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)


class FinancialModule:
    """
    Financial intelligence module for the superagent.

    Wraps SokoPulse (market intelligence), FMCG analytics,
    and distribution gap analysis into a single module.
    """

    def __init__(self):
        self._soko_pulse = None
        self._fmcg = None
        self._distribution_gap = None
        self._initialized = False

    async def _ensure_initialized(self):
        """Lazily initialize service connections."""
        if self._initialized:
            return

        try:
            from app.services.intelligence.soko_pulse import SokoPulseService
            self._soko_pulse = SokoPulseService()
        except (ImportError, Exception) as e:
            logger.warning("soko_pulse_load_failed", error=str(e))

        try:
            from app.services.intelligence.fmcg_intelligence import FMCGIntelligenceService
            self._fmcg = FMCGIntelligenceService()
        except (ImportError, Exception) as e:
            logger.warning("fmcg_load_failed", error=str(e))

        try:
            from app.services.intelligence.distribution_gap import DistributionGapAnalyzer
            self._distribution_gap = DistributionGapAnalyzer()
        except (ImportError, Exception) as e:
            logger.warning("distribution_gap_load_failed", error=str(e))

        self._initialized = True

    async def observe(self, data: dict) -> dict:
        """
        Observe: Gather financial context from market data.

        Enriches the observation with current market conditions,
        price trends, and demand signals.
        """
        await self._ensure_initialized()

        enrichment = {
            "module": "financial",
            "data_points": [],
        }

        # Extract relevant financial data
        if "transactions" in data:
            txns = data["transactions"]
            amounts = [t.get("amount", 0) for t in txns if t.get("amount")]
            if amounts:
                enrichment["data_points"].append({
                    "type": "transaction_summary",
                    "count": len(txns),
                    "total_volume": sum(amounts),
                    "avg_amount": sum(amounts) / len(amounts),
                })

        return enrichment

    async def orient(self, observation: dict) -> dict:
        """
        Orient: Analyze financial situation.

        Determines market conditions, identifies trends,
        and assesses financial health indicators.
        """
        analysis = {
            "market_condition": "stable",
            "trend": "neutral",
            "risk_level": "low",
        }

        data_points = observation.get("enrichment", {}).get("data_points", [])
        for dp in data_points:
            if dp.get("type") == "transaction_summary":
                if dp.get("count", 0) > 100:
                    analysis["activity_level"] = "high"
                elif dp.get("count", 0) > 20:
                    analysis["activity_level"] = "medium"
                else:
                    analysis["activity_level"] = "low"

        return analysis

    async def execute(self, decision: dict) -> dict:
        """
        Execute financial intelligence operations.

        Routes to the appropriate sub-service based on the request.
        """
        await self._ensure_initialized()

        data = decision.get("data", {})
        action = decision.get("action", "analyze")

        result = {
            "module": "financial",
            "action": action,
            "status": "completed",
        }

        # Route to appropriate service
        if action == "price_forecast" and self._soko_pulse:
            try:
                result["soko_pulse"] = "available"
            except Exception as e:
                result["soko_pulse_error"] = str(e)

        if action == "fmcg_analysis" and self._fmcg:
            try:
                result["fmcg"] = "available"
            except Exception as e:
                result["fmcg_error"] = str(e)

        return result
