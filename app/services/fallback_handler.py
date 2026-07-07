"""
Fallback Handler — Graceful failure handling for multi-provider inference.

When a provider fails, the fallback handler:
1. Retries with the same provider (with backoff)
2. Falls back to alternative providers
3. Degrades to simpler/cheaper models
4. Logs all failures for analysis

ZERO-COST STRATEGY: Only on-device and Angavu Cloud providers.
No paid APIs (Groq, DeepSeek, NVIDIA NIM) are used.

Inspired by OmniRoute's smart fallback pattern.

Usage:
    handler = FallbackHandler(provider_registry)
    result = await handler.execute_with_fallback(request, providers=["on-device", "angavu-cloud"])
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

import structlog

from .provider_registry import ProviderRecord, ProviderRegistry, ProviderType

logger = structlog.get_logger(__name__)


class FallbackStrategy(str, Enum):
    """Strategy for handling provider failures."""
    RETRY_SAME = "retry_same"           # Retry with same provider
    FALLBACK_NEXT = "fallback_next"     # Try next provider in list
    DEGRADE_MODEL = "degrade_model"     # Use simpler model
    DEGRADE_TO_DEVICE = "degrade_to_device"  # Fall back to on-device
    FAIL = "fail"                       # Give up


class FailureRecord:
    """Record of a single failure event."""

    def __init__(
        self,
        provider_id: str,
        error_type: str,
        error_message: str,
        attempt: int,
        strategy_used: FallbackStrategy,
        timestamp: Optional[datetime] = None,
    ):
        self.provider_id = provider_id
        self.error_type = error_type
        self.error_message = error_message
        self.attempt = attempt
        self.strategy_used = strategy_used
        self.timestamp = timestamp or datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "error_type": self.error_type,
            "error_message": self.error_message[:200],
            "attempt": self.attempt,
            "strategy": self.strategy_used.value,
            "timestamp": self.timestamp.isoformat(),
        }


class InferenceRequest:
    """Represents an inference request that can be routed to any provider."""

    def __init__(
        self,
        request_id: str,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        task_complexity: str = "medium",
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.request_id = request_id
        self.messages = messages
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.task_complexity = task_complexity
        self.metadata = metadata or {}


class InferenceResponse:
    """Response from an inference request."""

    def __init__(
        self,
        request_id: str,
        provider_id: str,
        model_used: str,
        content: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: float,
        fallback_count: int = 0,
        compression_info: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.request_id = request_id
        self.provider_id = provider_id
        self.model_used = model_used
        self.content = content
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.latency_ms = latency_ms
        self.fallback_count = fallback_count
        self.compression_info = compression_info or {}
        self.metadata = metadata or {}

    @property
    def cost_estimate(self) -> float:
        """Estimate cost based on token counts (set externally if needed)."""
        return self.metadata.get("cost_estimate", 0.0)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "provider_id": self.provider_id,
            "model_used": self.model_used,
            "content": self.content,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "latency_ms": round(self.latency_ms, 2),
            "fallback_count": self.fallback_count,
            "compression_info": self.compression_info,
            "cost_estimate": self.cost_estimate,
        }


# Type for the actual inference function
InferenceFunc = Callable[..., Any]


class FallbackHandler:
    """
    Handles inference execution with graceful fallback across providers.

    When the primary provider fails, automatically:
    1. Retries with exponential backoff (up to max_retries)
    2. Falls back to next provider in the priority list
    3. Degrades to simpler/cheaper models
    4. Falls back to on-device as last resort
    """

    def __init__(
        self,
        provider_registry: ProviderRegistry,
        max_retries: int = 2,
        retry_base_delay_ms: float = 500.0,
        retry_max_delay_ms: float = 5000.0,
        circuit_breaker_threshold: int = 5,
        circuit_breaker_reset_seconds: float = 60.0,
    ):
        self.registry = provider_registry
        self.max_retries = max_retries
        self.retry_base_delay_ms = retry_base_delay_ms
        self.retry_max_delay_ms = retry_max_delay_ms
        self.circuit_breaker_threshold = circuit_breaker_threshold
        self.circuit_breaker_reset_seconds = circuit_breaker_reset_seconds

        # Failure history (ring buffer)
        self._failure_history: List[FailureRecord] = []
        self._max_history = 1000

        # Circuit breaker state per provider
        self._circuit_open_until: Dict[str, float] = {}  # provider_id -> timestamp

        # Stats
        self._total_requests: int = 0
        self._total_fallbacks: int = 0
        self._total_failures: int = 0

    def is_circuit_open(self, provider_id: str) -> bool:
        """Check if the circuit breaker is open for a provider."""
        open_until = self._circuit_open_until.get(provider_id, 0)
        if time.time() < open_until:
            return True
        # Reset if time has passed
        if provider_id in self._circuit_open_until:
            del self._circuit_open_until[provider_id]
        return False

    def open_circuit(self, provider_id: str):
        """Trip the circuit breaker for a provider."""
        self._circuit_open_until[provider_id] = time.time() + self.circuit_breaker_reset_seconds
        logger.warning("circuit_breaker_opened", provider=provider_id, reset_in=self.circuit_breaker_reset_seconds)

    def record_failure(self, failure: FailureRecord):
        """Record a failure event."""
        self._failure_history.append(failure)
        if len(self._failure_history) > self._max_history:
            self._failure_history = self._failure_history[-self._max_history:]

    def get_fallback_chain(
        self,
        preferred_providers: Optional[List[str]] = None,
        task_complexity: str = "medium",
        exclude: Optional[List[str]] = None,
    ) -> List[ProviderRecord]:
        """
        Build an ordered fallback chain of providers.

        Order: preferred providers first, then by optimal selection,
        with on-device as final fallback.
        """
        exclude = set(exclude or [])
        chain: List[ProviderRecord] = []
        seen = set()

        # Add preferred providers first
        if preferred_providers:
            for pid in preferred_providers:
                if pid in seen or pid in exclude:
                    continue
                p = self.registry.get(pid)
                if p and p.is_available and not self.is_circuit_open(pid):
                    chain.append(p)
                    seen.add(pid)

        # Add remaining providers by optimal selection
        for _ in range(10):  # Safety limit
            optimal = self.registry.select_optimal(
                task_complexity=task_complexity,
                exclude=list(seen | exclude),
            )
            if optimal is None or optimal.provider_id in seen:
                break
            if self.is_circuit_open(optimal.provider_id):
                seen.add(optimal.provider_id)
                continue
            chain.append(optimal)
            seen.add(optimal.provider_id)

        # Ensure on-device is in the chain as last resort (if not excluded)
        if "on-device" not in seen and "on-device" not in exclude:
            on_device = self.registry.get("on-device")
            if on_device and on_device.is_available:
                chain.append(on_device)

        return chain

    async def execute_with_fallback(
        self,
        request: InferenceRequest,
        inference_func: InferenceFunc,
        preferred_providers: Optional[List[str]] = None,
    ) -> InferenceResponse:
        """
        Execute an inference request with automatic fallback.

        Args:
            request: The inference request
            inference_func: Async function(provider_id, request) -> InferenceResponse
            preferred_providers: Ordered list of preferred provider IDs

        Returns:
            InferenceResponse from the first successful provider

        Raises:
            RuntimeError: If all providers fail
        """
        self._total_requests += 1
        chain = self.get_fallback_chain(
            preferred_providers=preferred_providers,
            task_complexity=request.task_complexity,
        )

        if not chain:
            self._total_failures += 1
            raise RuntimeError("No available providers for inference")

        errors: List[FailureRecord] = []
        attempt = 0

        for provider in chain:
            for retry in range(self.max_retries + 1):
                attempt += 1

                # Exponential backoff for retries
                if retry > 0:
                    delay_s = min(
                        self.retry_base_delay_ms * (2 ** (retry - 1)),
                        self.retry_max_delay_ms,
                    ) / 1000.0
                    await asyncio.sleep(delay_s)

                try:
                    self.registry.record_request_start(provider.provider_id)
                    start_time = time.time()

                    result = await inference_func(provider.provider_id, request)

                    latency_ms = (time.time() - start_time) * 1000
                    self.registry.record_success(provider.provider_id, latency_ms)

                    if attempt > 1:
                        self._total_fallbacks += 1

                    logger.info(
                        "inference_success",
                        provider=provider.provider_id,
                        attempt=attempt,
                        latency_ms=round(latency_ms, 2),
                        fallback_count=len(errors),
                    )

                    return result

                except Exception as e:
                    error_type = type(e).__name__
                    error_msg = str(e)[:500]

                    self.registry.record_failure(provider.provider_id, error_msg)

                    failure = FailureRecord(
                        provider_id=provider.provider_id,
                        error_type=error_type,
                        error_message=error_msg,
                        attempt=attempt,
                        strategy_used=FallbackStrategy.RETRY_SAME if retry < self.max_retries else FallbackStrategy.FALLBACK_NEXT,
                    )
                    errors.append(failure)
                    self.record_failure(failure)

                    # Check if circuit breaker should trip
                    if self.registry.get(provider.provider_id):
                        p = self.registry.get(provider.provider_id)
                        if p and p.consecutive_failures >= self.circuit_breaker_threshold:
                            self.open_circuit(provider.provider_id)

                    logger.warning(
                        "inference_failed",
                        provider=provider.provider_id,
                        error_type=error_type,
                        attempt=attempt,
                        retry=retry,
                    )

            # All retries exhausted for this provider, move to next

        # All providers exhausted
        self._total_failures += 1
        error_summary = "; ".join(f"{e.provider_id}: {e.error_type}" for e in errors[-5:])
        raise RuntimeError(f"All providers failed after {attempt} attempts: {error_summary}")

    def get_stats(self) -> Dict[str, Any]:
        failure_by_provider = defaultdict(int)
        for f in self._failure_history:
            failure_by_provider[f.provider_id] += 1

        return {
            "total_requests": self._total_requests,
            "total_fallbacks": self._total_fallbacks,
            "total_failures": self._total_failures,
            "success_rate": round(
                1 - (self._total_failures / max(1, self._total_requests)), 4
            ),
            "circuit_breakers_open": {
                pid: round(until - time.time(), 1)
                for pid, until in self._circuit_open_until.items()
                if time.time() < until
            },
            "recent_failures_by_provider": dict(failure_by_provider),
            "recent_failure_count": len(self._failure_history),
        }

    def get_failure_history(
        self,
        provider_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        failures = self._failure_history
        if provider_id:
            failures = [f for f in failures if f.provider_id == provider_id]
        return [f.to_dict() for f in failures[-limit:]]


# Singleton
_handler: Optional[FallbackHandler] = None


def get_fallback_handler(registry: Optional[ProviderRegistry] = None) -> FallbackHandler:
    global _handler
    if _handler is None:
        from .provider_registry import get_provider_registry
        _handler = FallbackHandler(registry or get_provider_registry())
    return _handler
