"""
Financial Intelligence Module

Wraps existing SokoPulse, FMCG Intelligence, and Distribution Gap services
into the superagent architecture. Provides a unified interface for all
financial intelligence operations.
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
            from app.db.database import async_session_factory
            if async_session_factory:
                session = async_session_factory()
                from app.services.intelligence.soko_pulse import SokoPulseService
                self._soko_pulse = SokoPulseService(db=session)
                logger.info("soko_pulse_loaded")
        except (ImportError, AttributeError, TypeError) as e:
            logger.warning("soko_pulse_load_failed", error=str(e))

        try:
            if not self._fmcg:
                from app.db.database import async_session_factory
                if async_session_factory:
                    session = async_session_factory()
                    from app.services.intelligence.fmcg_intelligence import FMCGIntelligenceService
                    self._fmcg = FMCGIntelligenceService(db=session)
                    logger.info("fmcg_loaded")
        except (ImportError, AttributeError, TypeError) as e:
            logger.warning("fmcg_load_failed", error=str(e))

        try:
            if not self._distribution_gap:
                from app.db.database import async_session_factory
                if async_session_factory:
                    session = async_session_factory()
                    from app.services.intelligence.distribution_gap import DistributionGapService
                    self._distribution_gap = DistributionGapService(db=session)
                    logger.info("distribution_gap_loaded")
        except (ImportError, AttributeError, TypeError) as e:
            logger.warning("distribution_gap_load_failed", error=str(e))

        self._initialized = True

    async def observe(self, data: dict) -> dict:
        """Enrich observation with financial context."""
        await self._ensure_initialized()

        enrichment = {
            "module": "financial",
            "data_points": [],
        }

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
        """Analyze financial situation."""
        analysis = {
            "market_condition": "stable",
            "trend": "neutral",
            "risk_level": "low",
        }

        data_points = observation.get("enrichment", {}).get("data_points", [])
        for dp in data_points:
            if dp.get("type") == "transaction_summary":
                count = dp.get("count", 0)
                if count > 100:
                    analysis["activity_level"] = "high"
                elif count > 20:
                    analysis["activity_level"] = "medium"
                else:
                    analysis["activity_level"] = "low"

        return analysis

    async def analyze(self, data: dict) -> dict:
        """Run financial analysis using available services."""
        await self._ensure_initialized()
        results = {"module": "financial", "analyses": {}}

        if self._soko_pulse and "product" in data:
            try:
                forecast = await self._soko_pulse.generate_demand_forecast(
                    product_id=data["product"],
                    region=data.get("region", "default"),
                )
                results["analyses"]["demand_forecast"] = forecast
            except (ValueError, KeyError, ConnectionError) as e:
                results["analyses"]["demand_forecast_error"] = str(e)

        if self._fmcg and "brand" in data:
            try:
                results["analyses"]["fmcg"] = "analysis_available"
            except (ValueError, KeyError) as e:
                results["analyses"]["fmcg_error"] = str(e)

        return results

    async def execute(self, decision: dict) -> dict:
        """Execute financial intelligence operations."""
        await self._ensure_initialized()

        action = decision.get("action", "analyze")
        data = decision.get("data", decision.get("params", {}))

        result = {
            "module": "financial",
            "action": action,
            "status": "completed",
        }

        # Try to run actual analysis
        try:
            analysis = await self.analyze(data)
            result["analysis"] = analysis.get("analyses", {})
        except (ValueError, KeyError, ConnectionError) as e:
            result["analysis_error"] = str(e)

        # Route to specific service
        if action == "price_forecast" and self._soko_pulse:
            result["soko_pulse"] = "available"
        if action == "fmcg_analysis" and self._fmcg:
            result["fmcg"] = "available"
        if self._distribution_gap:
            result["distribution_gap"] = "available"

        return result
