"""
Evolution Module — Self-Improvement Engine

Wraps the existing SelfEvolution service into the superagent architecture.
Provides continuous learning, feedback integration, and strategy adaptation.
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
            logger.info("evolution_service_loaded")
        except (ImportError, Exception) as e:
            logger.warning("evolution_service_load_failed", error=str(e))

        self._initialized = True

    async def observe(self, data: dict) -> dict:
        """Gather performance and feedback signals."""
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
        """Assess improvement opportunities."""
        success_count = sum(1 for o in self._outcomes[-20:] if o.get("status") == "completed")
        total = min(len(self._outcomes), 20)

        orientation = {
            "success_rate": success_count / max(total, 1),
            "total_outcomes": len(self._outcomes),
            "improvement_areas": [],
        }

        if self._evolution_service:
            try:
                report = await self._evolution_service.get_evolution_report()
                orientation["evolution_report"] = {
                    "total_feedback": getattr(report, "total_feedback", 0),
                    "features_generated": getattr(report, "features_generated", 0),
                }
            except (ValueError, ConnectionError) as e:
                orientation["evolution_report_error"] = str(e)

        return orientation

    async def execute(self, decision: dict) -> dict:
        """Execute evolution operations."""
        await self._ensure_initialized()

        result = {
            "module": "evolution",
            "status": "completed",
        }

        if self._evolution_service:
            try:
                report = await self._evolution_service.get_evolution_report()
                result["evolution_service_available"] = True
                result["report"] = {
                    "total_feedback": getattr(report, "total_feedback", 0),
                    "features_generated": getattr(report, "features_generated", 0),
                }
            except (ValueError, ConnectionError) as e:
                result["evolution_service_available"] = True
                result["report_error"] = str(e)
        else:
            result["evolution_service_available"] = False

        return result

    async def record_outcome(self, outcome: dict) -> None:
        """Record an outcome for learning."""
        self._outcomes.append(outcome)

        if len(self._outcomes) > 1000:
            self._outcomes = self._outcomes[-500:]

        if len(self._outcomes) >= 10:
            recent = self._outcomes[-10:]
            success_rate = sum(1 for o in recent if o.get("status") == "completed") / len(recent)

            if success_rate < 0.5:
                logger.warning(
                    "low_success_rate_detected",
                    rate=success_rate,
                    recent_count=len(recent),
                )

        # Feed to evolution service if available
        if self._evolution_service:
            try:
                from app.services.self_evolution import WorkerFeedback, FeedbackType
                feedback = WorkerFeedback(
                    worker_id=outcome.get("worker_id", "system"),
                    feedback_type=FeedbackType.FEATURE_REQUEST,
                    text=str(outcome.get("error", "outcome recorded")),
                    sentiment=1.0 if outcome.get("status") == "completed" else -1.0,
                )
                await self._evolution_service.collect_feedback(feedback)
            except (ImportError, ValueError, AttributeError) as e:
                logger.debug("evolution_feedback_failed", error=str(e))
