"""
Evolution Module — Self-Improvement Engine

Wraps the existing SelfEvolution service into the superagent architecture.
Provides continuous learning, feedback integration, and strategy adaptation.

Existing service wrapped:
- app.services.self_evolution — Worker-driven feature evolution
"""

from __future__ import annotations

from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)


class EvolutionModule:
    """
    Evolution module for the superagent.

    Wraps the SelfEvolution service and provides a unified interface
    for self-improvement and adaptation operations.
    """

    def __init__(self):
        self._evolution_service = None
        self._outcomes: list[dict] = []
        self._initialized = False

    async def _ensure_initialized(self):
        """Lazily initialize service connections."""
        if self._initialized:
            return

        try:
            from app.services.self_evolution import SelfEvolutionService
            self._evolution_service = SelfEvolutionService()
        except (ImportError, Exception) as e:
            logger.warning("evolution_service_load_failed", error=str(e))

        self._initialized = True

    async def observe(self, data: dict) -> dict:
        """
        Observe: Gather performance and feedback signals.

        Monitors outcomes and user feedback for improvement opportunities.
        """
        await self._ensure_initialized()

        enrichment = {
            "module": "evolution",
            "signals": [],
        }

        if "feedback" in data:
            enrichment["signals"].append({
                "type": "user_feedback",
                "data": data["feedback"],
            })

        return enrichment

    async def orient(self, observation: dict) -> dict:
        """
        Orient: Assess improvement opportunities.

        Analyzes recent outcomes to identify patterns and areas for improvement.
        """
        success_count = sum(1 for o in self._outcomes[-20:] if o.get("status") == "completed")
        total = min(len(self._outcomes), 20)

        return {
            "success_rate": success_count / max(total, 1),
            "total_outcomes": len(self._outcomes),
            "improvement_areas": [],
        }

    async def execute(self, decision: dict) -> dict:
        """
        Execute evolution operations.

        Records outcomes and triggers adaptation if needed.
        """
        await self._ensure_initialized()

        result = {
            "module": "evolution",
            "status": "completed",
        }

        if self._evolution_service:
            result["evolution_service_available"] = True
        else:
            result["evolution_service_available"] = False

        return result

    async def record_outcome(self, outcome: dict) -> None:
        """
        Record an outcome for learning.

        Stores the outcome and triggers adaptation if patterns are detected.
        """
        self._outcomes.append(outcome)

        # Trim history
        if len(self._outcomes) > 1000:
            self._outcomes = self._outcomes[-500:]

        # Check for adaptation triggers
        if len(self._outcomes) >= 10:
            recent = self._outcomes[-10:]
            success_rate = sum(1 for o in recent if o.get("status") == "completed") / len(recent)

            if success_rate < 0.5:
                logger.warning(
                    "low_success_rate_detected",
                    rate=success_rate,
                    recent_count=len(recent),
                )
