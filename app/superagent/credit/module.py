"""
Credit Intelligence Module

Wraps the existing AlamaScore service into the superagent architecture.
Provides credit scoring, risk profiling, and creditworthiness assessment.
"""

from __future__ import annotations

from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)


class CreditModule:
    """
    Credit intelligence module for the superagent.

    Wraps AlamaScore (transaction-based credit scoring) and
    provides a unified interface for credit operations.
    """

    def __init__(self):
        self._alama_score = None
        self._initialized = False

    async def _ensure_initialized(self):
        """Lazily initialize service connections."""
        if self._initialized:
            return

        try:
            from app.db.database import async_session_factory
            if async_session_factory:
                session = async_session_factory()
                from app.services.intelligence.alama_score import AlamaScoreService
                self._alama_score = AlamaScoreService(db=session)
                logger.info("alama_score_loaded")
        except (ImportError, AttributeError, TypeError) as e:
            logger.warning("alama_score_load_failed", error=str(e))

        self._initialized = True

    async def observe(self, data: dict) -> dict:
        """Gather credit-relevant data."""
        await self._ensure_initialized()

        enrichment = {
            "module": "credit",
            "indicators": [],
        }

        if "transactions" in data:
            txns = data["transactions"]
            amounts = [t.get("amount", 0) for t in txns if t.get("amount")]
            if amounts:
                total = sum(amounts)
                enrichment["indicators"].append({
                    "type": "transaction_volume",
                    "value": total,
                    "count": len(amounts),
                })

                if len(amounts) >= 10:
                    avg = total / len(amounts)
                    variance = sum((a - avg) ** 2 for a in amounts) / len(amounts)
                    enrichment["indicators"].append({
                        "type": "consistency",
                        "coefficient_of_variation": (variance ** 0.5) / max(avg, 1),
                    })

        return enrichment

    async def orient(self, observation: dict) -> dict:
        """Assess credit situation."""
        analysis = {
            "risk_profile": "moderate",
            "creditworthiness": "assessing",
        }

        indicators = observation.get("enrichment", {}).get("indicators", [])
        for ind in indicators:
            if ind.get("type") == "transaction_volume":
                value = ind.get("value", 0)
                if value > 100000:
                    analysis["volume_tier"] = "high"
                elif value > 30000:
                    analysis["volume_tier"] = "medium"
                else:
                    analysis["volume_tier"] = "low"

        return analysis

    async def execute(self, decision: dict) -> dict:
        """Execute credit intelligence operations."""
        await self._ensure_initialized()

        data = decision.get("data", decision.get("params", {}))
        result = {
            "module": "credit",
            "status": "completed",
        }

        if self._alama_score and "worker_id" in data:
            try:
                score = await self._alama_score.compute_score(
                    worker_id=data["worker_id"],
                )
                result["alama_score"] = score
            except (ValueError, KeyError, ConnectionError) as e:
                result["alama_score_error"] = str(e)
        elif self._alama_score:
            result["alama_score_available"] = True
        else:
            result["alama_score_available"] = False
            result["note"] = "AlamaScore service not loaded"

        return result
