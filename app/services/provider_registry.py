"""
Provider Registry — AI provider health, latency, and cost tracking.

Manages the lifecycle of inference providers (on-device, cloud, API),
tracks their health status and performance metrics, and auto-selects
the optimal provider based on cost, latency, and reliability.

ZERO-COST STRATEGY:
    Only on-device (llama.cpp) and Angavu Cloud (future) providers are
    registered. No paid APIs (Groq, DeepSeek, NVIDIA NIM) are included.
    All inference runs locally or on self-hosted infrastructure.

Usage:
    registry = ProviderRegistry()
    registry.register("on-device", ProviderType.ON_DEVICE, ...)
    registry.register("angavu-cloud", ProviderType.SELF_HOSTED, ...)
    best = registry.select_optimal(task_complexity="low")
"""

from __future__ import annotations

import statistics
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Deque, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


class ProviderType(str, Enum):
    ON_DEVICE = "on_device"          # llama.cpp NDK on Android
    SELF_HOSTED = "self_hosted"      # Angavu Cloud inference servers
    EDGE = "edge"                    # Edge inference nodes


class ProviderStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


class ProviderCapability(str, Enum):
    CHAT = "chat"
    COMPLETION = "completion"
    EMBEDDING = "embedding"
    VISION = "vision"
    FUNCTION_CALLING = "function_calling"
    STREAMING = "streaming"


class ProviderRecord:
    """Tracks a single provider's configuration and runtime metrics."""

    def __init__(
        self,
        provider_id: str,
        provider_type: ProviderType,
        display_name: str,
        base_url: str = "",
        models: Optional[List[str]] = None,
        capabilities: Optional[List[ProviderCapability]] = None,
        cost_per_1k_input: float = 0.0,
        cost_per_1k_output: float = 0.0,
        max_context_tokens: int = 4096,
        priority: int = 100,  # lower = higher priority
        max_concurrent: int = 10,
        timeout_seconds: float = 30.0,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.provider_id = provider_id
        self.provider_type = provider_type
        self.display_name = display_name
        self.base_url = base_url
        self.models = models or []
        self.capabilities = capabilities or [ProviderCapability.CHAT]
        self.cost_per_1k_input = cost_per_1k_input
        self.cost_per_1k_output = cost_per_1k_output
        self.max_context_tokens = max_context_tokens
        self.priority = priority
        self.max_concurrent = max_concurrent
        self.timeout_seconds = timeout_seconds
        self.metadata = metadata or {}

        # Runtime state
        self.status: ProviderStatus = ProviderStatus.UNKNOWN
        self.active_requests: int = 0
        self.total_requests: int = 0
        self.total_failures: int = 0
        self.consecutive_failures: int = 0
        self.last_success_at: Optional[datetime] = None
        self.last_failure_at: Optional[datetime] = None
        self.registered_at: datetime = datetime.now(timezone.utc)

        # Rolling window for latency (last 100 requests)
        self._latency_window: Deque[float] = deque(maxlen=100)
        # Rolling window for error rate (last 200 requests)
        self._request_window: Deque[bool] = deque(maxlen=200)

    @property
    def avg_latency_ms(self) -> Optional[float]:
        if not self._latency_window:
            return None
        return statistics.mean(self._latency_window)

    @property
    def p95_latency_ms(self) -> Optional[float]:
        if len(self._latency_window) < 2:
            return self.avg_latency_ms
        sorted_lat = sorted(self._latency_window)
        idx = int(len(sorted_lat) * 0.95)
        return sorted_lat[min(idx, len(sorted_lat) - 1)]

    @property
    def error_rate(self) -> float:
        if not self._request_window:
            return 0.0
        failures = sum(1 for ok in self._request_window if not ok)
        return failures / len(self._request_window)

    @property
    def is_available(self) -> bool:
        return (
            self.status in (ProviderStatus.HEALTHY, ProviderStatus.DEGRADED)
            and self.active_requests < self.max_concurrent
        )

    def record_success(self, latency_ms: float):
        self.total_requests += 1
        self.active_requests = max(0, self.active_requests - 1)
        self._latency_window.append(latency_ms)
        self._request_window.append(True)
        self.consecutive_failures = 0
        self.last_success_at = datetime.now(timezone.utc)
        if self.status in (ProviderStatus.UNHEALTHY, ProviderStatus.UNKNOWN):
            self.status = ProviderStatus.DEGRADED
        if self.error_rate < 0.05 and self.status == ProviderStatus.DEGRADED:
            self.status = ProviderStatus.HEALTHY

    def record_failure(self, error: str = ""):
        self.total_requests += 1
        self.total_failures += 1
        self.active_requests = max(0, self.active_requests - 1)
        self._request_window.append(False)
        self.consecutive_failures += 1
        self.last_failure_at = datetime.now(timezone.utc)
        if self.consecutive_failures >= 5:
            self.status = ProviderStatus.UNHEALTHY
            logger.warning("provider_unhealthy", provider=self.provider_id, consecutive=self.consecutive_failures)
        elif self.consecutive_failures >= 2:
            self.status = ProviderStatus.DEGRADED

    def record_request_start(self):
        self.active_requests += 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "type": self.provider_type.value,
            "display_name": self.display_name,
            "status": self.status.value,
            "models": self.models,
            "capabilities": [c.value for c in self.capabilities],
            "cost_per_1k_input": self.cost_per_1k_input,
            "cost_per_1k_output": self.cost_per_1k_output,
            "max_context_tokens": self.max_context_tokens,
            "priority": self.priority,
            "active_requests": self.active_requests,
            "total_requests": self.total_requests,
            "total_failures": self.total_failures,
            "consecutive_failures": self.consecutive_failures,
            "error_rate": round(self.error_rate, 4),
            "avg_latency_ms": round(self.avg_latency_ms, 2) if self.avg_latency_ms else None,
            "p95_latency_ms": round(self.p95_latency_ms, 2) if self.p95_latency_ms else None,
            "is_available": self.is_available,
            "registered_at": self.registered_at.isoformat(),
            "last_success_at": self.last_success_at.isoformat() if self.last_success_at else None,
            "last_failure_at": self.last_failure_at.isoformat() if self.last_failure_at else None,
        }


class ProviderRegistry:
    """
    Central registry for all AI inference providers.

    ZERO-COST STRATEGY: Only free providers are registered.
    No paid APIs (Groq, DeepSeek, NVIDIA NIM) are included.
    """

    def __init__(self):
        self._providers: Dict[str, ProviderRecord] = {}

    def register(
        self,
        provider_id: str,
        provider_type: ProviderType,
        display_name: str,
        **kwargs,
    ) -> ProviderRecord:
        """Register a new provider."""
        if provider_id in self._providers:
            logger.warning("provider_already_registered", provider=provider_id)
            return self._providers[provider_id]

        record = ProviderRecord(
            provider_id=provider_id,
            provider_type=provider_type,
            display_name=display_name,
            **kwargs,
        )
        self._providers[provider_id] = record
        logger.info("provider_registered", provider=provider_id, type=provider_type.value)
        return record

    def unregister(self, provider_id: str) -> bool:
        if provider_id in self._providers:
            del self._providers[provider_id]
            return True
        return False

    def get(self, provider_id: str) -> Optional[ProviderRecord]:
        return self._providers.get(provider_id)

    def list_providers(
        self,
        provider_type: Optional[ProviderType] = None,
        status: Optional[ProviderStatus] = None,
        capability: Optional[ProviderCapability] = None,
        available_only: bool = False,
    ) -> List[ProviderRecord]:
        """List providers with optional filters."""
        results = list(self._providers.values())
        if provider_type:
            results = [p for p in results if p.provider_type == provider_type]
        if status:
            results = [p for p in results if p.status == status]
        if capability:
            results = [p for p in results if capability in p.capabilities]
        if available_only:
            results = [p for p in results if p.is_available]
        return sorted(results, key=lambda p: p.priority)

    def select_optimal(
        self,
        model: Optional[str] = None,
        capability: ProviderCapability = ProviderCapability.CHAT,
        task_complexity: str = "medium",
        max_latency_ms: Optional[float] = None,
        max_cost_per_1k: Optional[float] = None,
        prefer_type: Optional[ProviderType] = None,
        exclude: Optional[List[str]] = None,
    ) -> Optional[ProviderRecord]:
        """
        Select the optimal provider for a given task.

        Scoring factors:
        1. Availability (must be available)
        2. Capability match
        3. Model match (if specified)
        4. Cost (lower is better — always $0 for our providers)
        5. Latency (lower is better)
        6. Error rate (lower is better)
        7. Priority (lower is better)
        8. Type preference bonus
        """
        exclude = set(exclude or [])
        candidates = [
            p for p in self._providers.values()
            if p.is_available
            and p.provider_id not in exclude
            and capability in p.capabilities
        ]

        if not candidates:
            return None

        if model:
            model_matches = [p for p in candidates if model in p.models]
            if model_matches:
                candidates = model_matches

        if max_latency_ms:
            filtered = [p for p in candidates if p.avg_latency_ms is None or p.avg_latency_ms <= max_latency_ms]
            if filtered:
                candidates = filtered

        if max_cost_per_1k is not None:
            filtered = [p for p in candidates if p.cost_per_1k_input <= max_cost_per_1k]
            if filtered:
                candidates = filtered

        def score(p: ProviderRecord) -> float:
            s = 0.0
            s -= p.priority * 0.3
            s -= p.cost_per_1k_input * 1000 * 0.25
            lat = p.avg_latency_ms or 5000.0
            s -= (lat / 1000.0) * 0.2
            s -= p.error_rate * 5.0 * 0.15
            if prefer_type and p.provider_type == prefer_type:
                s += 5.0
            if task_complexity == "low" and p.provider_type == ProviderType.ON_DEVICE:
                s += 3.0
            if task_complexity == "high" and p.provider_type == ProviderType.SELF_HOSTED:
                s += 2.0
            return s

        candidates.sort(key=score, reverse=True)
        return candidates[0]

    def record_success(self, provider_id: str, latency_ms: float):
        p = self._providers.get(provider_id)
        if p:
            p.record_success(latency_ms)

    def record_failure(self, provider_id: str, error: str = ""):
        p = self._providers.get(provider_id)
        if p:
            p.record_failure(error)

    def record_request_start(self, provider_id: str):
        p = self._providers.get(provider_id)
        if p:
            p.record_request_start()

    def set_status(self, provider_id: str, status: ProviderStatus):
        p = self._providers.get(provider_id)
        if p:
            p.status = status

    def get_health_summary(self) -> Dict[str, Any]:
        providers = list(self._providers.values())
        return {
            "total_providers": len(providers),
            "healthy": sum(1 for p in providers if p.status == ProviderStatus.HEALTHY),
            "degraded": sum(1 for p in providers if p.status == ProviderStatus.DEGRADED),
            "unhealthy": sum(1 for p in providers if p.status == ProviderStatus.UNHEALTHY),
            "offline": sum(1 for p in providers if p.status == ProviderStatus.OFFLINE),
            "available": sum(1 for p in providers if p.is_available),
            "providers": [p.to_dict() for p in providers],
        }

    def get_cost_summary(self) -> Dict[str, Any]:
        providers = list(self._providers.values())
        total_requests = sum(p.total_requests for p in providers)
        by_type = defaultdict(lambda: {"requests": 0, "cost_estimate": 0.0})
        for p in providers:
            t = p.provider_type.value
            by_type[t]["requests"] += p.total_requests
            by_type[t]["cost_estimate"] += p.total_requests * 0.5 * (p.cost_per_1k_input + p.cost_per_1k_output) / 1000
        return {
            "total_requests": total_requests,
            "by_type": dict(by_type),
        }


# Singleton
_registry: Optional[ProviderRegistry] = None


def get_provider_registry() -> ProviderRegistry:
    global _registry
    if _registry is None:
        _registry = ProviderRegistry()
        _register_defaults(_registry)
    return _registry


def _register_defaults(registry: ProviderRegistry):
    """
    Register default Angavu Intelligence providers.

    ZERO-COST STRATEGY — only free providers:
    - On-device (Android llama.cpp) — primary, always available
    - Angavu Cloud (future) — self-hosted inference servers
    """
    # On-device (Android llama.cpp) — PRIMARY, highest priority
    registry.register(
        provider_id="on-device",
        provider_type=ProviderType.ON_DEVICE,
        display_name="On-Device llama.cpp",
        models=["qwen-0.5b-fl-sw", "qwen-1.7b", "qwen-2b", "phi-2", "tinyllama"],
        capabilities=[
            ProviderCapability.CHAT,
            ProviderCapability.COMPLETION,
            ProviderCapability.EMBEDDING,
            ProviderCapability.FUNCTION_CALLING,
            ProviderCapability.STREAMING,
        ],
        cost_per_1k_input=0.0,
        cost_per_1k_output=0.0,
        max_context_tokens=4096,
        priority=10,  # Highest priority — free, fast, offline
        timeout_seconds=15.0,
    )

    # Angavu Cloud (future — self-hosted inference on Oracle Cloud)
    # Currently a placeholder — will be enabled when self-hosted
    # inference servers are deployed on Oracle Cloud free tier.
    registry.register(
        provider_id="angavu-cloud",
        provider_type=ProviderType.SELF_HOSTED,
        display_name="Angavu Cloud (Self-Hosted)",
        models=["qwen-0.5b-fl-sw", "qwen-1.7b", "qwen-2b"],
        capabilities=[
            ProviderCapability.CHAT,
            ProviderCapability.COMPLETION,
            ProviderCapability.EMBEDDING,
            ProviderCapability.FUNCTION_CALLING,
            ProviderCapability.STREAMING,
        ],
        cost_per_1k_input=0.0,
        cost_per_1k_output=0.0,
        max_context_tokens=8192,
        priority=20,  # Lower priority than on-device
        timeout_seconds=30.0,
        metadata={"status": "future", "note": "Will be enabled when self-hosted servers are deployed"},
    )

    logger.info("default_providers_registered", count=2, strategy="zero_cost")
