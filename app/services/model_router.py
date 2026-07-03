"""
Model Router — OmniRoute-inspired AI gateway for Angavu Intelligence.

Routes inference requests across multiple providers with:
- Smart provider selection based on task, cost, latency
- Token compression for cost optimization
- Automatic fallback on provider failure
- Usage tracking and analytics

This is the main entry point for all inference requests.

Usage:
    router = ModelRouter()
    response = await router.infer(messages=[...], task_complexity="medium")
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import structlog

from .fallback_handler import (
    FallbackHandler,
    InferenceRequest,
    InferenceResponse,
    get_fallback_handler,
)
from .provider_registry import (
    ProviderCapability,
    ProviderRegistry,
    ProviderType,
    get_provider_registry,
)
from .token_compressor import TokenCompressor, estimate_messages_tokens, get_token_compressor

logger = structlog.get_logger(__name__)


class ModelRouter:
    """
    Central inference router inspired by OmniRoute.

    Orchestrates:
    - Provider selection (via ProviderRegistry)
    - Token compression (via TokenCompressor)
    - Fallback handling (via FallbackHandler)
    - Usage tracking and cost optimization
    """

    def __init__(
        self,
        provider_registry: Optional[ProviderRegistry] = None,
        token_compressor: Optional[TokenCompressor] = None,
        fallback_handler: Optional[FallbackHandler] = None,
        enable_compression: bool = True,
        compression_threshold_tokens: int = 2000,
        default_max_tokens: int = 1024,
        default_temperature: float = 0.7,
    ):
        self.registry = provider_registry or get_provider_registry()
        self.compressor = token_compressor or get_token_compressor()
        self.fallback = fallback_handler or get_fallback_handler(self.registry)
        self.enable_compression = enable_compression
        self.compression_threshold_tokens = compression_threshold_tokens
        self.default_max_tokens = default_max_tokens
        self.default_temperature = default_temperature

        # Usage tracking
        self._usage_log: List[Dict[str, Any]] = []
        self._max_log = 500
        self._total_tokens_in: int = 0
        self._total_tokens_out: int = 0
        self._total_cost: float = 0.0
        self._requests_by_provider: Dict[str, int] = defaultdict(int)
        self._requests_by_model: Dict[str, int] = defaultdict(int)

    async def infer(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        task_complexity: str = "medium",
        preferred_providers: Optional[List[str]] = None,
        enable_compression: Optional[bool] = None,
        request_id: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> InferenceResponse:
        """
        Route an inference request to the optimal provider.

        Args:
            messages: Conversation messages [{role, content}, ...]
            model: Preferred model name (optional)
            max_tokens: Max output tokens
            temperature: Sampling temperature
            task_complexity: "low", "medium", "high"
            preferred_providers: Ordered list of preferred provider IDs
            enable_compression: Override compression setting
            request_id: Optional request ID for tracking
            user_id: Optional user ID for tracking
            metadata: Additional metadata

        Returns:
            InferenceResponse with the model's output
        """
        request_id = request_id or f"req-{uuid.uuid4().hex[:12]}"
        max_tokens = max_tokens or self.default_max_tokens
        temperature = temperature or self.default_temperature
        do_compress = enable_compression if enable_compression is not None else self.enable_compression

        # Step 1: Compress if needed
        compression_info = {}
        if do_compress:
            input_tokens = estimate_messages_tokens(messages)
            if input_tokens > self.compression_threshold_tokens:
                messages, compression_info = self.compressor.compress(
                    messages,
                    max_tokens=self.compression_threshold_tokens,
                )
                logger.info(
                    "prompt_compressed",
                    request_id=request_id,
                    strategy=compression_info.get("strategy"),
                    input_tokens=compression_info.get("input_tokens"),
                    output_tokens=compression_info.get("output_tokens"),
                )

        # Step 2: Build inference request
        request = InferenceRequest(
            request_id=request_id,
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            task_complexity=task_complexity,
            metadata=metadata,
        )

        # Step 3: Execute with fallback
        start_time = time.time()

        async def _execute(provider_id: str, req: InferenceRequest) -> InferenceResponse:
            return await self._call_provider(provider_id, req)

        response = await self.fallback.execute_with_fallback(
            request=request,
            inference_func=_execute,
            preferred_providers=preferred_providers,
        )

        # Step 4: Attach compression info
        response.compression_info = compression_info

        # Step 5: Track usage
        self._track_usage(response, user_id)

        return response

    async def _call_provider(
        self,
        provider_id: str,
        request: InferenceRequest,
    ) -> InferenceResponse:
        """
        Call a specific provider. Override this method to add actual
        API integration (Groq, DeepSeek, etc.).

        This base implementation simulates the call for testing.
        """
        provider = self.registry.get(provider_id)
        if not provider:
            raise ValueError(f"Provider {provider_id} not found")

        # Simulate provider call (replace with actual API calls)
        # In production, this would call the provider's API
        model = request.model or (provider.models[0] if provider.models else "default")

        # For now, return a mock response indicating the routing decision
        # Real implementation would call the actual provider API
        logger.info(
            "calling_provider",
            provider=provider_id,
            model=model,
            messages_count=len(request.messages),
            max_tokens=request.max_tokens,
        )

        # Simulate latency and response
        # This is where actual API integration goes:
        # - Groq: httpx POST to https://api.groq.com/openai/v1/chat/completions
        # - DeepSeek: httpx POST to https://api.deepseek.com/v1/chat/completions
        # - On-device: forward to device via WebSocket/HTTP
        # - Self-hosted: httpx POST to internal endpoint

        import asyncio
        await asyncio.sleep(0.01)  # Minimal delay for simulation

        # Build a placeholder response
        return InferenceResponse(
            request_id=request.request_id,
            provider_id=provider_id,
            model_used=model,
            content="",  # Would contain actual model output
            input_tokens=estimate_messages_tokens(request.messages),
            output_tokens=0,
            latency_ms=0,
            fallback_count=0,
            metadata={
                "cost_per_1k_input": provider.cost_per_1k_input,
                "cost_per_1k_output": provider.cost_per_1k_output,
            },
        )

    def _track_usage(self, response: InferenceResponse, user_id: Optional[str] = None):
        """Track usage statistics."""
        self._total_tokens_in += response.input_tokens
        self._total_tokens_out += response.output_tokens
        self._requests_by_provider[response.provider_id] += 1
        self._requests_by_model[response.model_used] += 1

        # Estimate cost
        provider = self.registry.get(response.provider_id)
        if provider:
            cost = (
                response.input_tokens * provider.cost_per_1k_input / 1000
                + response.output_tokens * provider.cost_per_1k_output / 1000
            )
            self._total_cost += cost
            response.metadata["cost_estimate"] = cost

        # Log entry
        entry = {
            "request_id": response.request_id,
            "provider_id": response.provider_id,
            "model": response.model_used,
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
            "latency_ms": response.latency_ms,
            "fallback_count": response.fallback_count,
            "user_id": user_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._usage_log.append(entry)
        if len(self._usage_log) > self._max_log:
            self._usage_log = self._usage_log[-self._max_log:]

    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive routing and usage statistics."""
        return {
            "total_requests": len(self._usage_log),
            "total_tokens_input": self._total_tokens_in,
            "total_tokens_output": self._total_tokens_out,
            "total_cost_estimate": round(self._total_cost, 6),
            "requests_by_provider": dict(self._requests_by_provider),
            "requests_by_model": dict(self._requests_by_model),
            "compression_stats": self.compressor.get_stats(),
            "fallback_stats": self.fallback.get_stats(),
            "provider_health": self.registry.get_health_summary(),
        }

    def get_recent_requests(self, limit: int = 20) -> List[Dict[str, Any]]:
        return self._usage_log[-limit:]

    def list_providers(self) -> List[Dict[str, Any]]:
        return [p.to_dict() for p in self.registry.list_providers()]

    def get_provider_health(self) -> Dict[str, Any]:
        return self.registry.get_health_summary()

    def get_cost_summary(self) -> Dict[str, Any]:
        return {
            "total_cost_estimate": round(self._total_cost, 6),
            "total_tokens_input": self._total_tokens_in,
            "total_tokens_output": self._total_tokens_out,
            "by_provider": self.registry.get_cost_summary(),
        }


# Singleton
_router: Optional[ModelRouter] = None


def get_model_router() -> ModelRouter:
    global _router
    if _router is None:
        _router = ModelRouter()
    return _router
