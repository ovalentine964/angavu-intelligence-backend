"""
Federated Learning Module

Wraps the existing FederatedLearning service into the superagent architecture.
Provides privacy-preserving distributed learning capabilities.
"""

from __future__ import annotations

from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)


class LearningModule:
    """
    Federated learning module for the superagent.

    Wraps the FederatedLearningService and provides a unified
    interface for distributed learning operations.
    """

    def __init__(self):
        self._fl_service = None
        self._initialized = False

    async def _ensure_initialized(self):
        """Lazily initialize service connections."""
        if self._initialized:
            return

        try:
            from app.services.federated_learning import FederatedLearningService
            self._fl_service = FederatedLearningService()
            logger.info("fl_service_loaded")
        except (ImportError, Exception) as e:
            logger.warning("fl_service_load_failed", error=str(e))

        self._initialized = True

    async def observe(self, data: dict) -> dict:
        """Gather learning-relevant signals."""
        await self._ensure_initialized()

        enrichment = {
            "module": "learning",
            "signals": [],
        }

        if "model_updates" in data:
            enrichment["signals"].append({
                "type": "model_updates",
                "count": len(data["model_updates"]),
            })

        return enrichment

    async def orient(self, observation: dict) -> dict:
        """Assess learning state."""
        status_info = {"training_status": "stable", "model_health": "good"}

        if self._fl_service:
            try:
                fl_status = await self._fl_service.get_status()
                status_info["fl_status"] = fl_status
            except (ValueError, ConnectionError) as e:
                status_info["fl_status_error"] = str(e)

        return status_info

    async def execute(self, decision: dict) -> dict:
        """Execute federated learning operations."""
        await self._ensure_initialized()

        result = {
            "module": "learning",
            "status": "completed",
        }

        if self._fl_service:
            try:
                fl_status = await self._fl_service.get_status()
                result["fl_service_available"] = True
                result["fl_status"] = fl_status
            except (ValueError, ConnectionError) as e:
                result["fl_service_available"] = True
                result["fl_status_error"] = str(e)
        else:
            result["fl_service_available"] = False
            result["note"] = "FederatedLearning service not loaded"

        return result
