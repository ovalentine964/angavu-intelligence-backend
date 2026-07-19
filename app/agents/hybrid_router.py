"""
Hybrid LLM Router — routes queries between on-device and cloud reasoning.

Decision cascade:
1. Cloud disabled? → on-device
2. User exceeded budget? → on-device
3. Simple query? → on-device (faster, free)
4. Complex query + connected? → cloud (better quality)
5. Cloud fails? → on-device (graceful fallback)
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import StrEnum

import structlog

from app.services.cloud_reasoning import (
    CloudReasoningService,
    CloudResponse,
    QueryComplexity,
    classify_complexity,
)
from app.services.gemini_config import get_gemini_config

logger = structlog.get_logger(__name__)


class RoutingDecision(StrEnum):
    """Where the query was routed."""

    ON_DEVICE = "on_device"
    CLOUD = "cloud"
    CACHED = "cached"
    FALLBACK = "fallback"  # Tried cloud, failed, used on-device


@dataclass
class HybridResponse:
    """Response from the hybrid router."""

    text: str
    decision: RoutingDecision
    complexity: QueryComplexity
    cloud_response: CloudResponse | None = None
    latency_ms: float = 0.0
    cost_usd: float = 0.0


class HybridLLMRouter:
    """
    Routes queries between on-device (Qwen) and cloud (Gemini) reasoning.

    Design principles:
    - Simple queries → on-device (fast, free, works offline)
    - Complex queries → cloud (better reasoning, worth the cost)
    - Always fallback to on-device if cloud fails
    - Respect per-user budgets
    """

    def __init__(
        self,
        cloud_service: CloudReasoningService,
        on_device_generate=None,  # Callable[[str, str], Awaitable[str]]
    ) -> None:
        self._cloud = cloud_service
        self._on_device = on_device_generate
        self._config = get_gemini_config()

    async def route(
        self,
        query: str,
        user_id: str,
        transaction_context: str = "",
        is_connected: bool = True,
        battery_level: int = 100,
        system_prompt: str = "",
    ) -> HybridResponse:
        """
        Route a query to the best available backend.

        Args:
            query: User's natural language query
            user_id: User identifier for budget tracking
            transaction_context: Recent transactions for context
            is_connected: Whether device has internet
            battery_level: Device battery percentage (0-100)
            system_prompt: System prompt for the LLM
        """
        start_time = time.monotonic()
        complexity = classify_complexity(query)

        # Decision cascade
        decision = self._decide(complexity, is_connected, battery_level, user_id)

        if decision == RoutingDecision.CLOUD:
            cloud_response = await self._cloud.reason(
                query=query,
                user_id=user_id,
                transaction_context=transaction_context,
                system_prompt=system_prompt,
            )

            if cloud_response:
                return HybridResponse(
                    text=cloud_response.text,
                    decision=RoutingDecision.CLOUD,
                    complexity=complexity,
                    cloud_response=cloud_response,
                    latency_ms=(time.monotonic() - start_time) * 1000,
                    cost_usd=cloud_response.cost_usd,
                )

            # Cloud failed → fallback to on-device
            logger.info("hybrid_router.cloud_failed_fallback", user_id=user_id)
            decision = RoutingDecision.FALLBACK

        # On-device path
        text = await self._generate_on_device(query, transaction_context)

        return HybridResponse(
            text=text,
            decision=decision,
            complexity=complexity,
            latency_ms=(time.monotonic() - start_time) * 1000,
            cost_usd=0.0,
        )

    def _decide(
        self,
        complexity: QueryComplexity,
        is_connected: bool,
        battery_level: int,
        user_id: str,
    ) -> RoutingDecision:
        """Make routing decision."""
        # Cloud disabled?
        if not self._cloud.enabled:
            return RoutingDecision.ON_DEVICE

        # No connection?
        if not is_connected:
            return RoutingDecision.ON_DEVICE

        # Battery critical?
        if battery_level < 15:
            return RoutingDecision.ON_DEVICE

        # Simple query → on-device (faster, free)
        if complexity == QueryComplexity.SIMPLE:
            return RoutingDecision.ON_DEVICE

        # Moderate query → on-device (cost savings)
        if complexity == QueryComplexity.MODERATE:
            return RoutingDecision.ON_DEVICE

        # Complex query + connected → cloud
        if complexity == QueryComplexity.COMPLEX and is_connected:
            return RoutingDecision.CLOUD

        return RoutingDecision.ON_DEVICE

    async def _generate_on_device(self, query: str, context: str) -> str:
        """Generate response using on-device model."""
        if self._on_device:
            return await self._on_device(query, context)
        return (
            "I'm currently offline and can't process complex queries. "
            "Please try again when you have internet connection, or ask a simpler question."
        )
