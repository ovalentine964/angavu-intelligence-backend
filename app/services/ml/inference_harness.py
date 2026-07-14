"""
Model Inference Harness — Unified control plane for all LLM/ML calls.

Wraps every model inference call with:
- Fallback chains (on-device → cloud cheap → cloud premium)
- Cost tracking per user ($0.013/user/month budget)
- Quality validation (output format, coherence, safety)
- Latency tracking per model tier
- Token counting and budget enforcement

Design Principle: The harness is the SINGLE entry point for all model calls.
No agent or service should call models directly — always through the harness.

Usage:
    harness = InferenceHarness()
    result = await harness.infer(
        prompt="Analyze this transaction...",
        user_id="worker_123",
        task_type="credit_scoring",
    )
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger(__name__)


# ════════════════════════════════════════════════════════════════════
# Model Tier Definitions
# ════════════════════════════════════════════════════════════════════


class ModelTier(str, Enum):
    """Model tiers ordered by cost (cheapest first)."""
    ON_DEVICE = "on_device"        # Local GGUF (llama.cpp) — $0.00
    CLOUD_CHEAP = "cloud_cheap"    # Groq/DeepSeek free tier — ~$0.0001/1K tokens
    CLOUD_PREMIUM = "cloud_premium"  # GPT-4/Claude — ~$0.01/1K tokens


@dataclass
class ModelConfig:
    """Configuration for a single model endpoint."""
    tier: ModelTier
    name: str
    endpoint: str
    api_key: str = ""
    max_tokens: int = 512
    temperature: float = 0.7
    timeout_s: float = 30.0
    cost_per_1k_input: float = 0.0    # USD per 1K input tokens
    cost_per_1k_output: float = 0.0   # USD per 1K output tokens
    enabled: bool = True
    priority: int = 0                 # Lower = tried first within tier


@dataclass
class InferenceResult:
    """Result of a model inference call."""
    inference_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    success: bool = False
    output: str = ""
    model_used: str = ""
    tier_used: ModelTier = ModelTier.ON_DEVICE
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    quality_score: float = 0.0       # 0.0–1.0
    quality_issues: List[str] = field(default_factory=list)
    fallback_count: int = 0          # How many models were tried
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "inference_id": self.inference_id,
            "success": self.success,
            "output_length": len(self.output),
            "model_used": self.model_used,
            "tier_used": self.tier_used.value,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": round(self.cost_usd, 8),
            "latency_ms": round(self.latency_ms, 2),
            "quality_score": round(self.quality_score, 4),
            "quality_issues": self.quality_issues,
            "fallback_count": self.fallback_count,
            "error": self.error,
        }


# ════════════════════════════════════════════════════════════════════
# Cost Budget Manager
# ════════════════════════════════════════════════════════════════════


@dataclass
class UserBudget:
    """Per-user monthly cost budget tracking."""
    user_id: str
    monthly_budget_usd: float = 0.013   # $0.013/user/month
    spent_this_month_usd: float = 0.0
    month_start: float = field(default_factory=time.time)
    total_calls: int = 0
    total_tokens: int = 0


class CostBudgetManager:
    """
    Tracks and enforces per-user monthly cost budgets.

    Budget: $0.013/user/month (Angavu's target cost)
    - On-device calls: $0.00 (unlimited)
    - Cloud cheap: ~$0.0001/1K tokens → ~130K tokens/month free
    - Cloud premium: ~$0.01/1K tokens → ~1.3K tokens/month

    When budget is exhausted, falls back to on-device only.
    """

    def __init__(self, default_budget_usd: float = 0.013):
        self._default_budget = default_budget_usd
        self._users: Dict[str, UserBudget] = {}
        self._logger = logger.bind(component="cost_budget")

    def get_user_budget(self, user_id: str) -> UserBudget:
        """Get or create user budget tracker."""
        if user_id not in self._users:
            self._users[user_id] = UserBudget(
                user_id=user_id,
                monthly_budget_usd=self._default_budget,
            )
        return self._users[user_id]

    def check_budget(self, user_id: str, estimated_cost: float = 0.0) -> bool:
        """Check if user has budget remaining for a call."""
        budget = self.get_user_budget(user_id)
        self._maybe_reset_month(budget)
        return (budget.spent_this_month_usd + estimated_cost) <= budget.monthly_budget_usd

    def record_cost(self, user_id: str, cost_usd: float, tokens: int = 0) -> None:
        """Record cost incurred by a user."""
        budget = self.get_user_budget(user_id)
        self._maybe_reset_month(budget)
        budget.spent_this_month_usd += cost_usd
        budget.total_calls += 1
        budget.total_tokens += tokens

    def get_budget_status(self, user_id: str) -> Dict[str, Any]:
        """Get budget status for a user."""
        budget = self.get_user_budget(user_id)
        self._maybe_reset_month(budget)
        remaining = max(0, budget.monthly_budget_usd - budget.spent_this_month_usd)
        pct_used = (
            budget.spent_this_month_usd / budget.monthly_budget_usd * 100
            if budget.monthly_budget_usd > 0
            else 0
        )
        return {
            "user_id": user_id,
            "monthly_budget_usd": budget.monthly_budget_usd,
            "spent_usd": round(budget.spent_this_month_usd, 8),
            "remaining_usd": round(remaining, 8),
            "pct_used": round(pct_used, 2),
            "total_calls": budget.total_calls,
            "total_tokens": budget.total_tokens,
            "budget_exhausted": remaining <= 0,
        }

    def get_all_budgets(self) -> Dict[str, Any]:
        """Get summary of all user budgets."""
        return {
            "total_users": len(self._users),
            "total_spent_usd": round(sum(u.spent_this_month_usd for u in self._users.values()), 6),
            "users_over_80pct": sum(
                1 for u in self._users.values()
                if u.spent_this_month_usd > u.monthly_budget_usd * 0.8
            ),
            "budgets": {uid: self.get_budget_status(uid) for uid in self._users},
        }

    def _maybe_reset_month(self, budget: UserBudget) -> None:
        """Reset budget if a new month has started."""
        now = time.time()
        # Simple: reset every 30 days
        if now - budget.month_start > 30 * 24 * 3600:
            budget.spent_this_month_usd = 0.0
            budget.total_calls = 0
            budget.total_tokens = 0
            budget.month_start = now


# ════════════════════════════════════════════════════════════════════
# Quality Validator
# ════════════════════════════════════════════════════════════════════


class OutputQualityValidator:
    """
    Validates LLM output quality for Angavu Intelligence.

    Checks:
    - Non-empty output
    - Minimum length (not just "I don't know")
    - No hallucinated confidence scores outside 0-1
    - No toxic/harmful content (basic pattern matching)
    - JSON validity when expected
    - Swahili language quality (if applicable)
    """

    def __init__(self):
        self._toxic_patterns = [
            "kill", "suicide", "bomb", "terrorist",
            # Add more as needed
        ]

    def validate(
        self,
        output: str,
        task_type: str = "general",
        expect_json: bool = False,
    ) -> Tuple[float, List[str]]:
        """
        Validate output quality.

        Returns:
            (quality_score, issues_list) where score is 0.0–1.0
        """
        issues = []
        score = 1.0

        # 1. Non-empty check
        if not output or not output.strip():
            return 0.0, ["empty_output"]

        # 2. Minimum length
        if len(output.strip()) < 10:
            issues.append("output_too_short")
            score -= 0.3

        # 3. "I don't know" detection
        lower = output.lower()
        if any(phrase in lower for phrase in ["i don't know", "i do not know", "no information"]):
            issues.append("no_information_response")
            score -= 0.2

        # 4. Confidence score validation
        import re
        conf_matches = re.findall(r'confidence["\s:]+([0-9.]+)', lower)
        for conf_str in conf_matches:
            try:
                conf = float(conf_str)
                if conf < 0 or conf > 1:
                    issues.append(f"invalid_confidence_{conf}")
                    score -= 0.1
            except ValueError:
                pass

        # 5. JSON validity
        if expect_json:
            import json
            try:
                # Try to extract JSON from output
                json_start = output.find('{')
                json_end = output.rfind('}') + 1
                if json_start >= 0 and json_end > json_start:
                    json.loads(output[json_start:json_end])
                else:
                    issues.append("no_json_found")
                    score -= 0.3
            except json.JSONDecodeError:
                issues.append("invalid_json")
                score -= 0.3

        # 6. Toxicity check
        for pattern in self._toxic_patterns:
            if pattern in lower:
                issues.append(f"toxic_content_{pattern}")
                score -= 0.5
                break

        # 7. Task-specific validation
        if task_type == "credit_scoring":
            if "credit" not in lower and "score" not in lower and "alama" not in lower:
                issues.append("off_topic_credit")
                score -= 0.2
        elif task_type == "market_analysis":
            if "market" not in lower and "price" not in lower and "soko" not in lower:
                issues.append("off_topic_market")
                score -= 0.1

        return max(0.0, min(1.0, score)), issues


# ════════════════════════════════════════════════════════════════════
# Model Provider Abstraction
# ════════════════════════════════════════════════════════════════════


class ModelProvider:
    """
    Abstract interface for calling a model endpoint.

    Concrete implementations wrap llama.cpp, Groq, OpenAI, etc.
    """

    def __init__(self, config: ModelConfig):
        self.config = config

    async def generate(
        self,
        prompt: str,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> Tuple[str, int, int]:
        """
        Generate a response from the model.

        Returns:
            (output_text, input_tokens, output_tokens)

        Raises:
            Exception on failure (timeout, network error, etc.)
        """
        raise NotImplementedError


class LocalGGUFProvider(ModelProvider):
    """Provider for local llama.cpp server."""

    async def generate(
        self,
        prompt: str,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> Tuple[str, int, int]:
        """Call local llama.cpp HTTP server."""
        import aiohttp

        url = f"http://{self.config.endpoint}/completion"
        payload = {
            "prompt": prompt,
            "n_predict": max_tokens or self.config.max_tokens,
            "temperature": temperature if temperature is not None else self.config.temperature,
            "stream": False,
        }

        timeout = aiohttp.ClientTimeout(total=self.config.timeout_s)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"llama.cpp returned {resp.status}")
                data = await resp.json()
                output = data.get("content", "")
                # llama.cpp may not return token counts — estimate
                input_tokens = data.get("tokens_evaluated", len(prompt) // 4)
                output_tokens = data.get("tokens_predicted", len(output) // 4)
                return output, input_tokens, output_tokens


class HTTPModelProvider(ModelProvider):
    """Generic HTTP model provider (Groq, OpenAI-compatible)."""

    async def generate(
        self,
        prompt: str,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> Tuple[str, int, int]:
        """Call an OpenAI-compatible HTTP endpoint."""
        import aiohttp

        url = self.config.endpoint
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        payload = {
            "model": self.config.name,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens or self.config.max_tokens,
            "temperature": temperature if temperature is not None else self.config.temperature,
        }

        timeout = aiohttp.ClientTimeout(total=self.config.timeout_s)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise RuntimeError(f"Model API returned {resp.status}: {body[:200]}")
                data = await resp.json()

                output = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})
                input_tokens = usage.get("prompt_tokens", len(prompt) // 4)
                output_tokens = usage.get("completion_tokens", len(output) // 4)
                return output, input_tokens, output_tokens


# ════════════════════════════════════════════════════════════════════
# Inference Harness
# ════════════════════════════════════════════════════════════════════


@dataclass
class InferenceHarnessConfig:
    """Configuration for the inference harness."""
    max_fallback_attempts: int = 3
    quality_threshold: float = 0.3        # Minimum quality score to accept
    enable_cost_tracking: bool = True
    enable_quality_validation: bool = True
    default_budget_per_user_usd: float = 0.013
    # When budget exhausted, only allow on-device
    budget_exhausted_tier: ModelTier = ModelTier.ON_DEVICE


class InferenceHarness:
    """
    Unified inference harness for all LLM/ML model calls.

    Wraps every model call with:
    1. Fallback chain: on-device → cloud cheap → cloud premium
    2. Cost tracking and budget enforcement ($0.013/user/month)
    3. Quality validation (output format, coherence, safety)
    4. Latency tracking per model tier
    5. Token counting

    Usage:
        harness = InferenceHarness()
        harness.register_provider(LocalGGUFProvider(config))
        harness.register_provider(HTTPModelProvider(config))

        result = await harness.infer(
            prompt="Analyze this transaction data...",
            user_id="worker_123",
            task_type="credit_scoring",
        )
    """

    def __init__(self, config: Optional[InferenceHarnessConfig] = None):
        self._config = config or InferenceHarnessConfig()
        self._providers: Dict[ModelTier, List[ModelProvider]] = {
            ModelTier.ON_DEVICE: [],
            ModelTier.CLOUD_CHEAP: [],
            ModelTier.CLOUD_PREMIUM: [],
        }
        self._cost_manager = CostBudgetManager(
            default_budget_usd=self._config.default_budget_per_user_usd,
        )
        self._quality_validator = OutputQualityValidator()
        self._logger = logger.bind(component="inference_harness")

        # Metrics
        self._total_calls: int = 0
        self._total_cost_usd: float = 0.0
        self._tier_latencies: Dict[str, List[float]] = defaultdict(list)
        self._tier_counts: Dict[str, int] = defaultdict(int)
        self._fallback_counts: Dict[str, int] = defaultdict(int)

        # Pre/post hooks
        self._pre_hooks: List[Callable] = []
        self._post_hooks: List[Callable] = []

    # ── Provider Registration ───────────────────────────────────────

    def register_provider(self, provider: ModelProvider) -> None:
        """Register a model provider for its tier."""
        tier = provider.config.tier
        self._providers[tier].append(provider)
        # Sort by priority within tier
        self._providers[tier].sort(key=lambda p: p.config.priority)
        self._logger.info(
            "provider_registered",
            tier=tier.value,
            name=provider.config.name,
            priority=provider.config.priority,
        )

    # ── Core Inference ──────────────────────────────────────────────

    async def infer(
        self,
        prompt: str,
        user_id: Optional[str] = None,
        task_type: str = "general",
        expect_json: bool = False,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        preferred_tier: Optional[ModelTier] = None,
        timeout_override: Optional[float] = None,
    ) -> InferenceResult:
        """
        Run inference through the fallback chain.

        Steps:
        1. Check user budget → determine allowed tiers
        2. Build fallback chain (preferred tier first, then cheaper)
        3. For each provider in chain:
           a. Call the model
           b. Validate output quality
           c. If quality >= threshold, return result
           d. Otherwise, try next provider
        4. Record cost and metrics
        """
        self._total_calls += 1
        inference_id = uuid.uuid4().hex[:12]
        start_time = time.time()

        # 1. Determine allowed tiers based on budget
        allowed_tiers = self._get_allowed_tiers(user_id, preferred_tier)

        if not allowed_tiers:
            self._logger.warning("no_tiers_available", user_id=user_id)
            return InferenceResult(
                inference_id=inference_id,
                success=False,
                error="No model tiers available (budget exhausted or no providers registered)",
            )

        # 2. Build fallback chain
        chain = self._build_fallback_chain(allowed_tiers)

        # 3. Execute through chain
        last_error = None
        for attempt, provider in enumerate(chain):
            try:
                call_start = time.time()

                # Run pre-hooks
                for hook in self._pre_hooks:
                    try:
                        await hook(prompt, user_id, task_type, provider.config)
                    except Exception as hook_err:
                        self._logger.debug("pre_hook_error", error=str(hook_err))

                output, input_tokens, output_tokens = await provider.generate(
                    prompt, max_tokens=max_tokens, temperature=temperature,
                )

                latency_ms = (time.time() - call_start) * 1000

                # 4. Calculate cost
                cost_usd = self._calculate_cost(provider.config, input_tokens, output_tokens)

                # 5. Check budget
                if user_id and self._config.enable_cost_tracking:
                    if not self._cost_manager.check_budget(user_id, cost_usd):
                        self._logger.warning(
                            "budget_exhausted",
                            user_id=user_id,
                            cost_usd=cost_usd,
                        )
                        # If this is on-device, still allow (free)
                        if provider.config.tier != ModelTier.ON_DEVICE:
                            last_error = "User budget exhausted"
                            continue

                # 6. Validate quality
                quality_score = 1.0
                quality_issues: List[str] = []
                if self._config.enable_quality_validation:
                    quality_score, quality_issues = self._quality_validator.validate(
                        output, task_type=task_type, expect_json=expect_json,
                    )

                if quality_score < self._config.quality_threshold:
                    self._logger.info(
                        "quality_below_threshold",
                        inference_id=inference_id,
                        quality_score=quality_score,
                        issues=quality_issues,
                        model=provider.config.name,
                    )
                    last_error = f"Quality {quality_score:.2f} below threshold"
                    continue

                # 7. Success — record cost and metrics
                if user_id and self._config.enable_cost_tracking:
                    self._cost_manager.record_cost(user_id, cost_usd, input_tokens + output_tokens)

                self._total_cost_usd += cost_usd
                tier_key = provider.config.tier.value
                self._tier_latencies[tier_key].append(latency_ms)
                if len(self._tier_latencies[tier_key]) > 1000:
                    self._tier_latencies[tier_key] = self._tier_latencies[tier_key][-1000:]
                self._tier_counts[tier_key] += 1

                result = InferenceResult(
                    inference_id=inference_id,
                    success=True,
                    output=output,
                    model_used=provider.config.name,
                    tier_used=provider.config.tier,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=cost_usd,
                    latency_ms=latency_ms,
                    quality_score=quality_score,
                    quality_issues=quality_issues,
                    fallback_count=attempt,
                )

                # Run post-hooks
                for hook in self._post_hooks:
                    try:
                        await hook(result, provider.config)
                    except Exception as hook_err:
                        self._logger.debug("post_hook_error", error=str(hook_err))

                self._logger.info(
                    "inference_complete",
                    inference_id=inference_id,
                    model=provider.config.name,
                    tier=tier_key,
                    latency_ms=round(latency_ms, 2),
                    cost_usd=round(cost_usd, 8),
                    quality_score=round(quality_score, 4),
                    fallback_count=attempt,
                )

                return result

            except asyncio.TimeoutError:
                latency_ms = (time.time() - call_start) * 1000
                last_error = f"Timeout after {provider.config.timeout_s}s"
                self._logger.warning(
                    "inference_timeout",
                    model=provider.config.name,
                    latency_ms=round(latency_ms, 2),
                )
                continue

            except Exception as exc:
                latency_ms = (time.time() - call_start) * 1000
                last_error = str(exc)
                self._logger.warning(
                    "inference_error",
                    model=provider.config.name,
                    error=str(exc),
                    latency_ms=round(latency_ms, 2),
                )
                continue

        # All providers exhausted
        self._fallback_counts["exhausted"] += 1
        total_latency = (time.time() - start_time) * 1000
        self._logger.error(
            "inference_all_providers_failed",
            inference_id=inference_id,
            attempts=len(chain),
            last_error=last_error,
        )

        return InferenceResult(
            inference_id=inference_id,
            success=False,
            latency_ms=total_latency,
            fallback_count=len(chain),
            error=f"All {len(chain)} providers failed. Last: {last_error}",
        )

    # ── Fallback Chain ──────────────────────────────────────────────

    def _get_allowed_tiers(
        self,
        user_id: Optional[str],
        preferred_tier: Optional[ModelTier],
    ) -> List[ModelTier]:
        """Determine which tiers are allowed based on budget."""
        all_tiers = [ModelTier.ON_DEVICE, ModelTier.CLOUD_CHEAP, ModelTier.CLOUD_PREMIUM]

        if not user_id:
            # No user tracking — allow all
            return [t for t in all_tiers if self._providers[t]]

        # Check budget
        if not self._cost_manager.check_budget(user_id):
            # Budget exhausted — only on-device
            self._logger.info("budget_exhausted_on_device_only", user_id=user_id)
            return [ModelTier.ON_DEVICE] if self._providers[ModelTier.ON_DEVICE] else []

        return [t for t in all_tiers if self._providers[t]]

    def _build_fallback_chain(self, allowed_tiers: List[ModelTier]) -> List[ModelProvider]:
        """Build ordered list of providers to try."""
        chain = []
        for tier in allowed_tiers:
            for provider in self._providers[tier]:
                if provider.config.enabled:
                    chain.append(provider)
        return chain

    # ── Cost Calculation ────────────────────────────────────────────

    @staticmethod
    def _calculate_cost(
        config: ModelConfig,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        """Calculate cost in USD for a model call."""
        input_cost = (input_tokens / 1000.0) * config.cost_per_1k_input
        output_cost = (output_tokens / 1000.0) * config.cost_per_1k_output
        return input_cost + output_cost

    # ── Hooks ───────────────────────────────────────────────────────

    def add_pre_hook(self, hook: Callable) -> None:
        """Add pre-inference hook (called before each model call)."""
        self._pre_hooks.append(hook)

    def add_post_hook(self, hook: Callable) -> None:
        """Add post-inference hook (called after each successful call)."""
        self._post_hooks.append(hook)

    # ── Monitoring API ──────────────────────────────────────────────

    def get_metrics(self) -> Dict[str, Any]:
        """Get overall inference metrics."""
        tier_stats = {}
        for tier, latencies in self._tier_latencies.items():
            if latencies:
                sorted_lat = sorted(latencies)
                n = len(sorted_lat)
                tier_stats[tier] = {
                    "calls": self._tier_counts[tier],
                    "avg_latency_ms": round(sum(latencies) / n, 2),
                    "p50_latency_ms": round(sorted_lat[n // 2], 2),
                    "p95_latency_ms": round(sorted_lat[int(n * 0.95)], 2),
                    "p99_latency_ms": round(sorted_lat[int(n * 0.99)], 2),
                }

        return {
            "total_calls": self._total_calls,
            "total_cost_usd": round(self._total_cost_usd, 6),
            "tier_stats": tier_stats,
            "fallback_exhausted": self._fallback_counts.get("exhausted", 0),
        }

    def get_user_budget(self, user_id: str) -> Dict[str, Any]:
        """Get budget status for a user."""
        return self._cost_manager.get_budget_status(user_id)

    def get_all_budgets(self) -> Dict[str, Any]:
        """Get all user budget summary."""
        return self._cost_manager.get_all_budgets()

    def get_health(self) -> Dict[str, Any]:
        """Get harness health status."""
        providers_healthy = {}
        for tier, providers in self._providers.items():
            providers_healthy[tier.value] = [
                {"name": p.config.name, "enabled": p.config.enabled}
                for p in providers
            ]

        return {
            "status": "healthy",
            "providers": providers_healthy,
            "total_calls": self._total_calls,
            "total_cost_usd": round(self._total_cost_usd, 6),
            "config": {
                "quality_threshold": self._config.quality_threshold,
                "default_budget_usd": self._config.default_budget_per_user_usd,
                "max_fallback_attempts": self._config.max_fallback_attempts,
            },
        }


# ════════════════════════════════════════════════════════════════════
# Factory & Singleton
# ════════════════════════════════════════════════════════════════════


_global_inference_harness: Optional[InferenceHarness] = None


def get_inference_harness() -> InferenceHarness:
    """Get or create the global inference harness."""
    global _global_inference_harness
    if _global_inference_harness is None:
        _global_inference_harness = create_default_inference_harness()
    return _global_inference_harness


def create_default_inference_harness() -> InferenceHarness:
    """Create an inference harness with default Angavu configuration."""
    harness = InferenceHarness()

    # Register on-device provider (llama.cpp)
    try:
        from app.config import get_settings
        settings = get_settings()

        local_config = ModelConfig(
            tier=ModelTier.ON_DEVICE,
            name=settings.LLM_MODEL_PATH,
            endpoint=f"{settings.LLM_HOST}:{settings.LLM_PORT}",
            max_tokens=settings.LLM_MAX_TOKENS,
            temperature=settings.LLM_TEMPERATURE,
            timeout_s=settings.LLM_TIMEOUT,
            cost_per_1k_input=0.0,
            cost_per_1k_output=0.0,
            priority=0,
        )
        harness.register_provider(LocalGGUFProvider(local_config))

        # Register cloud cheap provider if configured
        # (Currently disabled per Angavu's zero-cost policy)
        # cloud_cheap_config = ModelConfig(
        #     tier=ModelTier.CLOUD_CHEAP,
        #     name="deepseek-chat",
        #     endpoint="https://api.deepseek.com/v1/chat/completions",
        #     api_key=settings.DEEPSEEK_API_KEY,
        #     cost_per_1k_input=0.0001,
        #     cost_per_1k_output=0.0002,
        #     priority=0,
        # )
        # harness.register_provider(HTTPModelProvider(cloud_cheap_config))

        logger.info(
            "inference_harness_created",
            providers=["on_device"],
            budget_per_user="$0.013/month",
        )
    except Exception as exc:
        logger.warning("inference_harness_setup_partial", error=str(exc))

    return harness


def create_inference_harness(
    providers: Optional[List[ModelProvider]] = None,
    budget_per_user_usd: float = 0.013,
    quality_threshold: float = 0.3,
) -> InferenceHarness:
    """Create an inference harness with custom configuration."""
    config = InferenceHarnessConfig(
        default_budget_per_user_usd=budget_per_user_usd,
        quality_threshold=quality_threshold,
    )
    harness = InferenceHarness(config)
    if providers:
        for provider in providers:
            harness.register_provider(provider)
    return harness
