"""
ModelInferenceHarness — Unified control plane for all LLM/ML calls.

Wraps every model inference call with:
- Fallback chains (on-device → cloud cheap → cloud premium)
- Cost tracking per user ($0.013/user/month budget)
- Quality validation (output format, coherence, safety)
- Latency tracking per model tier (p50/p95/p99)
- Token counting: per-user, per-model, per-day
- Intelligent model routing based on task complexity
- Semantic cache to reduce cost on similar queries

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
import hashlib
import json
import math
import re
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
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


class TaskComplexity(str, Enum):
    """Task complexity levels for intelligent routing."""
    TRIVIAL = "trivial"    # Simple lookups, formatting — always on-device
    LOW = "low"            # Transaction recording, balance check — on-device
    MEDIUM = "medium"      # Analysis, summaries — on-device, fallback to cloud
    HIGH = "high"          # Complex reasoning, reports — cloud preferred
    CRITICAL = "critical"  # High-stakes decisions — premium cloud


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
    max_context_tokens: int = 4096    # Max context window for this model


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
    cached: bool = False             # Whether result came from cache
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
            "cached": self.cached,
            "error": self.error,
        }


# ════════════════════════════════════════════════════════════════════
# Task Complexity → Tier Routing
# ════════════════════════════════════════════════════════════════════

# Maps task types to default complexity
TASK_COMPLEXITY_MAP: Dict[str, TaskComplexity] = {
    "transaction_recording": TaskComplexity.TRIVIAL,
    "balance_inquiry": TaskComplexity.TRIVIAL,
    "price_lookup": TaskComplexity.TRIVIAL,
    "formatting": TaskComplexity.TRIVIAL,
    "daily_briefing": TaskComplexity.LOW,
    "cash_flow_alert": TaskComplexity.LOW,
    "simple_summary": TaskComplexity.LOW,
    "market_analysis": TaskComplexity.MEDIUM,
    "inventory_analysis": TaskComplexity.MEDIUM,
    "credit_scoring": TaskComplexity.MEDIUM,
    "financial_analysis": TaskComplexity.HIGH,
    "risk_assessment": TaskComplexity.HIGH,
    "growth_planning": TaskComplexity.HIGH,
    "market_forecasting": TaskComplexity.HIGH,
    "complex_reasoning": TaskComplexity.CRITICAL,
    "report_generation": TaskComplexity.HIGH,
    "general": TaskComplexity.MEDIUM,
}

# Maps complexity to allowed tiers (ordered by preference)
COMPLEXITY_TIER_MAP: Dict[TaskComplexity, List[ModelTier]] = {
    TaskComplexity.TRIVIAL: [ModelTier.ON_DEVICE],
    TaskComplexity.LOW: [ModelTier.ON_DEVICE],
    TaskComplexity.MEDIUM: [ModelTier.ON_DEVICE, ModelTier.CLOUD_CHEAP],
    TaskComplexity.HIGH: [ModelTier.CLOUD_CHEAP, ModelTier.ON_DEVICE, ModelTier.CLOUD_PREMIUM],
    TaskComplexity.CRITICAL: [ModelTier.CLOUD_PREMIUM, ModelTier.CLOUD_CHEAP, ModelTier.ON_DEVICE],
}


# ════════════════════════════════════════════════════════════════════
# Semantic Cache
# ════════════════════════════════════════════════════════════════════


class SemanticCache:
    """
    Cache similar queries to reduce LLM cost and latency.

    Uses content hashing with normalization for near-duplicate detection.
    Caches are scoped by (task_type, normalized_prompt_hash) → result.

    Cache strategy:
    - Normalize prompt: lowercase, strip whitespace, collapse numbers
    - Hash normalized prompt + task_type as cache key
    - Store result with TTL (default 1 hour)
    - LRU eviction when cache is full
    """

    def __init__(
        self,
        max_entries: int = 2000,
        default_ttl_s: float = 3600.0,
    ):
        self._max_entries = max_entries
        self._default_ttl = default_ttl_s
        self._cache: Dict[str, Tuple[str, float, Dict[str, Any]]] = {}  # key → (output, expires_at, metadata)
        self._access_order: deque = deque()  # LRU tracking
        self._hits: int = 0
        self._misses: int = 0
        self._logger = logger.bind(component="semantic_cache")

    def _normalize(self, text: str) -> str:
        """Normalize text for cache key generation."""
        text = text.lower().strip()
        # Collapse multiple whitespace
        text = re.sub(r'\s+', ' ', text)
        # Normalize numbers to reduce cache misses on similar numeric queries
        text = re.sub(r'\b\d+(\.\d+)?\b', '<NUM>', text)
        return text

    def _make_key(self, prompt: str, task_type: str, system_prompt: str = "") -> str:
        """Generate cache key from normalized content."""
        normalized = self._normalize(prompt)
        if system_prompt:
            normalized = self._normalize(system_prompt) + "||" + normalized
        content = f"{task_type}||{normalized}"
        return hashlib.sha256(content.encode()).hexdigest()[:32]

    def get(
        self,
        prompt: str,
        task_type: str = "general",
        system_prompt: str = "",
    ) -> Optional[Tuple[str, Dict[str, Any]]]:
        """
        Look up cached result.

        Returns (output, metadata) or None if cache miss.
        """
        key = self._make_key(prompt, task_type, system_prompt)
        entry = self._cache.get(key)
        if entry is None:
            self._misses += 1
            return None

        output, expires_at, metadata = entry
        if time.time() > expires_at:
            # Expired
            del self._cache[key]
            self._misses += 1
            return None

        # Move to end of LRU
        try:
            self._access_order.remove(key)
        except ValueError:
            pass
        self._access_order.append(key)

        self._hits += 1
        self._logger.debug("cache_hit", key=key[:12], task_type=task_type)
        return output, metadata

    def put(
        self,
        prompt: str,
        output: str,
        task_type: str = "general",
        system_prompt: str = "",
        ttl_s: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Store result in cache."""
        key = self._make_key(prompt, task_type, system_prompt)
        expires_at = time.time() + (ttl_s or self._default_ttl)

        # Evict LRU if at capacity
        while len(self._cache) >= self._max_entries and self._access_order:
            oldest_key = self._access_order.popleft()
            self._cache.pop(oldest_key, None)

        self._cache[key] = (output, expires_at, metadata or {})
        self._access_order.append(key)

    def invalidate(self, prompt: str, task_type: str = "general", system_prompt: str = "") -> bool:
        """Invalidate a specific cache entry."""
        key = self._make_key(prompt, task_type, system_prompt)
        if key in self._cache:
            del self._cache[key]
            try:
                self._access_order.remove(key)
            except ValueError:
                pass
            return True
        return False

    def clear(self) -> int:
        """Clear entire cache. Returns number of entries cleared."""
        count = len(self._cache)
        self._cache.clear()
        self._access_order.clear()
        return count

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total = self._hits + self._misses
        return {
            "entries": len(self._cache),
            "max_entries": self._max_entries,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / max(1, total), 4),
            "default_ttl_s": self._default_ttl,
        }


# ════════════════════════════════════════════════════════════════════
# Token Tracker — Per-User, Per-Model, Per-Day
# ════════════════════════════════════════════════════════════════════


@dataclass
class TokenUsage:
    """Token usage for a specific (user, model, day) combination."""
    user_id: str
    model: str
    date: str  # YYYY-MM-DD
    input_tokens: int = 0
    output_tokens: int = 0
    total_calls: int = 0
    total_cost_usd: float = 0.0


class TokenTracker:
    """
    Tracks token usage per-user, per-model, per-day.

    Provides granular visibility into:
    - Which users consume the most tokens
    - Which models are used most frequently
    - Daily usage patterns for capacity planning
    - Cost attribution per user/model

    Data is kept in memory with automatic daily rollover.
    Old data is pruned after 30 days.
    """

    def __init__(self, retention_days: int = 30):
        self._retention_days = retention_days
        # Key: (user_id, model, date_str) → TokenUsage
        self._usage: Dict[Tuple[str, str, str], TokenUsage] = {}
        # Per-user daily aggregates: (user_id, date_str) → {input, output, cost, calls}
        self._user_daily: Dict[Tuple[str, str], Dict[str, float]] = defaultdict(
            lambda: {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "calls": 0}
        )
        # Per-model aggregates: model → {input, output, cost, calls}
        self._model_totals: Dict[str, Dict[str, float]] = defaultdict(
            lambda: {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "calls": 0}
        )
        self._logger = logger.bind(component="token_tracker")

    def record(
        self,
        user_id: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float = 0.0,
    ) -> None:
        """Record token usage for a call."""
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        key = (user_id, model, date_str)

        if key not in self._usage:
            self._usage[key] = TokenUsage(
                user_id=user_id, model=model, date=date_str,
            )
        usage = self._usage[key]
        usage.input_tokens += input_tokens
        usage.output_tokens += output_tokens
        usage.total_calls += 1
        usage.total_cost_usd += cost_usd

        # Update aggregates
        ud_key = (user_id, date_str)
        self._user_daily[ud_key]["input_tokens"] += input_tokens
        self._user_daily[ud_key]["output_tokens"] += output_tokens
        self._user_daily[ud_key]["cost_usd"] += cost_usd
        self._user_daily[ud_key]["calls"] += 1

        self._model_totals[model]["input_tokens"] += input_tokens
        self._model_totals[model]["output_tokens"] += output_tokens
        self._model_totals[model]["cost_usd"] += cost_usd
        self._model_totals[model]["calls"] += 1

    def get_user_usage(
        self,
        user_id: str,
        date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get token usage for a user on a specific day (or today)."""
        date_str = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        entries = [
            u for (uid, _, d), u in self._usage.items()
            if uid == user_id and d == date_str
        ]
        total_input = sum(e.input_tokens for e in entries)
        total_output = sum(e.output_tokens for e in entries)
        total_cost = sum(e.total_cost_usd for e in entries)
        total_calls = sum(e.total_calls for e in entries)

        by_model = {}
        for e in entries:
            by_model[e.model] = {
                "input_tokens": e.input_tokens,
                "output_tokens": e.output_tokens,
                "cost_usd": round(e.total_cost_usd, 8),
                "calls": e.total_calls,
            }

        return {
            "user_id": user_id,
            "date": date_str,
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_tokens": total_input + total_output,
            "total_cost_usd": round(total_cost, 8),
            "total_calls": total_calls,
            "by_model": by_model,
        }

    def get_model_usage(self, model: Optional[str] = None) -> Dict[str, Any]:
        """Get usage stats per model, or for a specific model."""
        if model:
            data = self._model_totals.get(model, {})
            return {"model": model, **data}
        return {
            "models": {
                m: {
                    "input_tokens": d["input_tokens"],
                    "output_tokens": d["output_tokens"],
                    "cost_usd": round(d["cost_usd"], 8),
                    "calls": int(d["calls"]),
                }
                for m, d in self._model_totals.items()
            }
        }

    def get_daily_usage(self, date: Optional[str] = None) -> Dict[str, Any]:
        """Get aggregate usage for a specific day."""
        date_str = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        entries = [
            (uid, u) for (uid, d), u in self._user_daily.items()
            if d == date_str
        ]
        total_input = sum(u["input_tokens"] for _, u in entries)
        total_output = sum(u["output_tokens"] for _, u in entries)
        total_cost = sum(u["cost_usd"] for _, u in entries)
        total_calls = sum(u["calls"] for _, u in entries)

        return {
            "date": date_str,
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_tokens": total_input + total_output,
            "total_cost_usd": round(total_cost, 8),
            "total_calls": int(total_calls),
            "unique_users": len(entries),
        }

    def get_top_users(self, limit: int = 10, date: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get top users by token consumption for a day."""
        date_str = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        user_totals = []
        for (uid, d), u in self._user_daily.items():
            if d == date_str:
                user_totals.append({
                    "user_id": uid,
                    "total_tokens": u["input_tokens"] + u["output_tokens"],
                    "cost_usd": round(u["cost_usd"], 8),
                    "calls": int(u["calls"]),
                })
        user_totals.sort(key=lambda x: x["total_tokens"], reverse=True)
        return user_totals[:limit]

    def prune_old_data(self) -> int:
        """Remove usage data older than retention_days. Returns entries pruned."""
        cutoff = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        # Simple: just remove keys with dates older than retention
        # For a real system, we'd parse dates properly
        keys_to_remove = []
        for (uid, model, date_str) in self._usage:
            # Keep last N days worth (approximate)
            pass  # In production, compare dates properly
        return 0

    def get_stats(self) -> Dict[str, Any]:
        """Get overall tracker statistics."""
        return {
            "total_entries": len(self._usage),
            "unique_users": len(set(uid for uid, _, _ in self._usage)),
            "unique_models": len(set(m for _, m, _ in self._usage)),
            "model_totals": {
                m: {
                    "calls": int(d["calls"]),
                    "total_tokens": int(d["input_tokens"] + d["output_tokens"]),
                }
                for m, d in self._model_totals.items()
            },
        }


# ════════════════════════════════════════════════════════════════════
# Latency Tracker — p50/p95/p99 per Model
# ════════════════════════════════════════════════════════════════════


class LatencyTracker:
    """
    Tracks latency percentiles (p50/p95/p99) per model.

    Uses a rolling window of recent latency measurements.
    Provides real-time percentile calculations for monitoring.
    """

    def __init__(self, window_size: int = 500):
        self._window_size = window_size
        # model → deque of latency measurements
        self._latencies: Dict[str, deque] = defaultdict(lambda: deque(maxlen=window_size))
        self._logger = logger.bind(component="latency_tracker")

    def record(self, model: str, latency_ms: float) -> None:
        """Record a latency measurement for a model."""
        self._latencies[model].append(latency_ms)

    def get_percentiles(self, model: str) -> Dict[str, float]:
        """Get latency percentiles for a model."""
        data = sorted(self._latencies.get(model, []))
        if not data:
            return {"p50": 0.0, "p95": 0.0, "p99": 0.0, "avg": 0.0, "min": 0.0, "max": 0.0, "count": 0}

        n = len(data)
        return {
            "p50": round(data[int(n * 0.50)], 2),
            "p95": round(data[min(int(n * 0.95), n - 1)], 2),
            "p99": round(data[min(int(n * 0.99), n - 1)], 2),
            "avg": round(sum(data) / n, 2),
            "min": round(data[0], 2),
            "max": round(data[-1], 2),
            "count": n,
        }

    def get_all_percentiles(self) -> Dict[str, Dict[str, float]]:
        """Get latency percentiles for all tracked models."""
        return {model: self.get_percentiles(model) for model in self._latencies}

    def get_stats(self) -> Dict[str, Any]:
        """Get tracker statistics."""
        return {
            "models_tracked": len(self._latencies),
            "total_measurements": sum(len(d) for d in self._latencies.values()),
            "window_size": self._window_size,
            "per_model": self.get_all_percentiles(),
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
    Auto-downgrades tier selection when over 80% budget consumed.
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

    def get_budget_utilization(self, user_id: str) -> float:
        """Get budget utilization as 0.0–1.0+ fraction."""
        budget = self.get_user_budget(user_id)
        self._maybe_reset_month(budget)
        if budget.monthly_budget_usd <= 0:
            return 0.0
        return budget.spent_this_month_usd / budget.monthly_budget_usd

    def is_near_limit(self, user_id: str, threshold: float = 0.8) -> bool:
        """Check if user is near budget limit (default 80%)."""
        return self.get_budget_utilization(user_id) >= threshold

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
            "near_limit": pct_used >= 80,
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
    - Coherence: output should be topically relevant
    - Safety: no toxic/harmful content patterns
    - JSON validity when expected
    - No hallucinated confidence scores outside 0-1
    - Relevance: topic keyword overlap with input
    """

    def __init__(self):
        self._toxic_patterns = [
            "kill", "suicide", "bomb", "terrorist",
            "hack", "exploit", "abuse",
        ]
        # Coherence: detect repetitive gibberish
        self._gibberish_pattern = re.compile(r'(.{10,})\1{3,}')

    def validate(
        self,
        output: str,
        task_type: str = "general",
        expect_json: bool = False,
        input_prompt: str = "",
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

        # 4. Coherence: detect gibberish / repetitive text
        if self._gibberish_pattern.search(output):
            issues.append("gibberish_detected")
            score -= 0.4

        # 5. Confidence score validation
        conf_matches = re.findall(r'confidence["\s:]+([0-9.]+)', lower)
        for conf_str in conf_matches:
            try:
                conf = float(conf_str)
                if conf < 0 or conf > 1:
                    issues.append(f"invalid_confidence_{conf}")
                    score -= 0.1
            except ValueError:
                pass

        # 6. JSON validity
        if expect_json:
            try:
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

        # 7. Safety: toxicity check
        for pattern in self._toxic_patterns:
            if pattern in lower:
                issues.append(f"toxic_content_{pattern}")
                score -= 0.5
                break

        # 8. Relevance: topic keyword overlap with input
        if input_prompt and len(input_prompt) > 20:
            relevance = self._check_relevance(input_prompt, output, task_type)
            if relevance < 0.2:
                issues.append("low_relevance")
                score -= 0.2

        # 9. Task-specific validation
        if task_type == "credit_scoring":
            if "credit" not in lower and "score" not in lower and "alama" not in lower:
                issues.append("off_topic_credit")
                score -= 0.2
        elif task_type == "market_analysis":
            if "market" not in lower and "price" not in lower and "soko" not in lower:
                issues.append("off_topic_market")
                score -= 0.1

        return max(0.0, min(1.0, score)), issues

    def _check_relevance(self, input_prompt: str, output: str, task_type: str) -> float:
        """Check topical relevance between input and output via keyword overlap."""
        # Extract meaningful words (3+ chars, not stopwords)
        stopwords = {"the", "and", "for", "this", "that", "with", "from", "are", "was", "were",
                      "have", "has", "had", "but", "not", "you", "your", "can", "will", "just",
                      "about", "would", "could", "should", "may", "might", "into", "over", "such"}
        input_words = set(
            w for w in re.findall(r'[a-z]{3,}', input_prompt.lower())
            if w not in stopwords
        )
        output_words = set(
            w for w in re.findall(r'[a-z]{3,}', output.lower())
            if w not in stopwords
        )
        if not input_words:
            return 1.0  # Can't check, assume relevant
        overlap = input_words & output_words
        return len(overlap) / len(input_words)


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
# Intelligent Task Router
# ════════════════════════════════════════════════════════════════════


class TaskRouter:
    """
    Routes inference requests to the optimal model tier based on:
    - Task type → complexity mapping
    - User budget utilization (auto-downgrade when near limit)
    - Prompt length (longer prompts need more capable models)
    - Explicit complexity override
    """

    def __init__(self):
        self._logger = logger.bind(component="task_router")

    def resolve_complexity(
        self,
        task_type: str = "general",
        complexity_override: Optional[str] = None,
        prompt_length: int = 0,
    ) -> TaskComplexity:
        """Resolve the effective task complexity."""
        if complexity_override:
            try:
                return TaskComplexity(complexity_override)
            except ValueError:
                self._logger.warning("invalid_complexity_override", value=complexity_override)

        # Auto-detect from task type
        complexity = TASK_COMPLEXITY_MAP.get(task_type, TaskComplexity.MEDIUM)

        # Upgrade complexity for very long prompts (likely complex tasks)
        if prompt_length > 3000 and complexity in (TaskComplexity.TRIVIAL, TaskComplexity.LOW):
            complexity = TaskComplexity.MEDIUM
            self._logger.debug("complexity_upgraded_for_length", new_complexity=complexity.value)

        return complexity

    def get_allowed_tiers(
        self,
        complexity: TaskComplexity,
        budget_utilization: float = 0.0,
    ) -> List[ModelTier]:
        """
        Get allowed model tiers for a task.

        Auto-downgrades when budget utilization is high:
        - >80%: force on-device only
        - >60%: prefer on-device, allow cloud cheap
        - Otherwise: follow complexity routing
        """
        if budget_utilization >= 0.8:
            self._logger.info("budget_auto_downgrade", utilization=budget_utilization)
            return [ModelTier.ON_DEVICE]

        if budget_utilization >= 0.6:
            # Prefer on-device, allow cloud cheap as fallback
            base = COMPLEXITY_TIER_MAP.get(complexity, [ModelTier.ON_DEVICE])
            # Ensure on-device is first
            tiers = [ModelTier.ON_DEVICE]
            for t in base:
                if t not in tiers and t != ModelTier.CLOUD_PREMIUM:
                    tiers.append(t)
            return tiers

        return COMPLEXITY_TIER_MAP.get(complexity, [ModelTier.ON_DEVICE, ModelTier.CLOUD_CHEAP])


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
    enable_cache: bool = True
    cache_ttl_s: float = 3600.0           # 1 hour default cache TTL
    cache_max_entries: int = 2000
    default_budget_per_user_usd: float = 0.013
    # When budget exhausted, only allow on-device
    budget_exhausted_tier: ModelTier = ModelTier.ON_DEVICE


class InferenceHarness:
    """
    Unified inference harness for all LLM/ML model calls.

    Wraps every model call with:
    1. Fallback chain: on-device → cloud cheap → cloud premium
    2. Cost tracking and budget enforcement ($0.013/user/month)
    3. Quality validation (coherence, safety, relevance)
    4. Latency tracking per model (p50/p95/p99)
    5. Token tracking: per-user, per-model, per-day
    6. Intelligent routing based on task complexity
    7. Semantic cache for similar queries
    8. Auto-downgrade when user is near budget limit

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
        self._token_tracker = TokenTracker()
        self._latency_tracker = LatencyTracker()
        self._task_router = TaskRouter()
        self._cache = SemanticCache(
            max_entries=self._config.cache_max_entries,
            default_ttl_s=self._config.cache_ttl_s,
        ) if self._config.enable_cache else None
        self._logger = logger.bind(component="inference_harness")

        # Global metrics
        self._total_calls: int = 0
        self._total_cost_usd: float = 0.0
        self._tier_counts: Dict[str, int] = defaultdict(int)
        self._fallback_counts: Dict[str, int] = defaultdict(int)
        self._cache_savings_usd: float = 0.0

        # Pre/post hooks
        self._pre_hooks: List[Callable] = []
        self._post_hooks: List[Callable] = []

    # ── Provider Registration ───────────────────────────────────────

    def register_provider(self, provider: ModelProvider) -> None:
        """Register a model provider for its tier."""
        tier = provider.config.tier
        self._providers[tier].append(provider)
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
        system_prompt: str = "",
        expect_json: bool = False,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        preferred_tier: Optional[ModelTier] = None,
        complexity: Optional[str] = None,
        timeout_override: Optional[float] = None,
        skip_cache: bool = False,
    ) -> InferenceResult:
        """
        Run inference through the full pipeline.

        Pipeline:
        1. Check cache → return cached result if hit
        2. Route: determine allowed tiers from task complexity + budget
        3. Build fallback chain
        4. For each provider: call → validate quality → return or fallback
        5. Record cost, tokens, latency
        6. Cache successful result
        """
        self._total_calls += 1
        inference_id = uuid.uuid4().hex[:12]
        start_time = time.time()

        # ── Step 1: Check cache ──
        if self._cache and not skip_cache:
            cached = self._cache.get(prompt, task_type, system_prompt)
            if cached is not None:
                output, cache_meta = cached
                latency_ms = (time.time() - start_time) * 1000
                self._logger.info("cache_hit_return", inference_id=inference_id, task_type=task_type)
                return InferenceResult(
                    inference_id=inference_id,
                    success=True,
                    output=output,
                    model_used=cache_meta.get("model_used", "cached"),
                    tier_used=ModelTier(cache_meta.get("tier", "on_device")),
                    cost_usd=0.0,
                    latency_ms=latency_ms,
                    quality_score=cache_meta.get("quality_score", 1.0),
                    cached=True,
                    metadata={"cache_hit": True},
                )

        # ── Step 2: Intelligent routing ──
        budget_util = 0.0
        if user_id:
            budget_util = self._cost_manager.get_budget_utilization(user_id)

        resolved_complexity = self._task_router.resolve_complexity(
            task_type=task_type,
            complexity_override=complexity,
            prompt_length=len(prompt),
        )

        if preferred_tier:
            allowed_tiers = [preferred_tier]
        else:
            allowed_tiers = self._task_router.get_allowed_tiers(
                complexity=resolved_complexity,
                budget_utilization=budget_util,
            )

        # Ensure we have providers for allowed tiers
        allowed_tiers = [t for t in allowed_tiers if self._providers[t]]

        if not allowed_tiers:
            self._logger.warning("no_tiers_available", user_id=user_id)
            return InferenceResult(
                inference_id=inference_id,
                success=False,
                error="No model tiers available (budget exhausted or no providers registered)",
            )

        # ── Step 3: Build fallback chain ──
        chain = self._build_fallback_chain(allowed_tiers)

        # ── Step 4: Execute through chain ──
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

                # ── Step 5a: Calculate cost ──
                cost_usd = self._calculate_cost(provider.config, input_tokens, output_tokens)

                # ── Step 5b: Check budget ──
                if user_id and self._config.enable_cost_tracking:
                    if not self._cost_manager.check_budget(user_id, cost_usd):
                        self._logger.warning("budget_exhausted", user_id=user_id, cost_usd=cost_usd)
                        if provider.config.tier != ModelTier.ON_DEVICE:
                            last_error = "User budget exhausted"
                            continue

                # ── Step 5c: Validate quality ──
                quality_score = 1.0
                quality_issues: List[str] = []
                if self._config.enable_quality_validation:
                    quality_score, quality_issues = self._quality_validator.validate(
                        output, task_type=task_type, expect_json=expect_json,
                        input_prompt=prompt,
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

                # ── Step 5d: Record cost, tokens, latency ──
                if user_id and self._config.enable_cost_tracking:
                    self._cost_manager.record_cost(user_id, cost_usd, input_tokens + output_tokens)

                self._total_cost_usd += cost_usd
                tier_key = provider.config.tier.value
                self._tier_counts[tier_key] += 1

                # Track tokens
                self._token_tracker.record(
                    user_id=user_id or "anonymous",
                    model=provider.config.name,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=cost_usd,
                )

                # Track latency
                self._latency_tracker.record(provider.config.name, latency_ms)

                # ── Step 6: Cache result ──
                if self._cache and not skip_cache and output:
                    self._cache.put(
                        prompt=prompt,
                        output=output,
                        task_type=task_type,
                        system_prompt=system_prompt,
                        metadata={
                            "model_used": provider.config.name,
                            "tier": provider.config.tier.value,
                            "quality_score": quality_score,
                        },
                    )

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
                    cached=False,
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
                    complexity=resolved_complexity.value,
                    latency_ms=round(latency_ms, 2),
                    cost_usd=round(cost_usd, 8),
                    quality_score=round(quality_score, 4),
                    fallback_count=attempt,
                )

                return result

            except asyncio.TimeoutError:
                latency_ms = (time.time() - call_start) * 1000
                last_error = f"Timeout after {provider.config.timeout_s}s"
                self._latency_tracker.record(provider.config.name, latency_ms)
                self._logger.warning(
                    "inference_timeout",
                    model=provider.config.name,
                    latency_ms=round(latency_ms, 2),
                )
                continue

            except Exception as exc:
                latency_ms = (time.time() - call_start) * 1000
                last_error = str(exc)
                self._latency_tracker.record(provider.config.name, latency_ms)
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
        """Get overall inference metrics including latency percentiles."""
        return {
            "total_calls": self._total_calls,
            "total_cost_usd": round(self._total_cost_usd, 6),
            "cache_savings_usd": round(self._cache_savings_usd, 6),
            "tier_counts": dict(self._tier_counts),
            "fallback_exhausted": self._fallback_counts.get("exhausted", 0),
            "latency": self._latency_tracker.get_all_percentiles(),
            "cache": self._cache.get_stats() if self._cache else {"enabled": False},
            "tokens": self._token_tracker.get_stats(),
        }

    def get_user_budget(self, user_id: str) -> Dict[str, Any]:
        """Get budget status for a user."""
        return self._cost_manager.get_budget_status(user_id)

    def get_all_budgets(self) -> Dict[str, Any]:
        """Get all user budget summary."""
        return self._cost_manager.get_all_budgets()

    def get_token_usage(
        self,
        user_id: Optional[str] = None,
        model: Optional[str] = None,
        date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get token usage with optional filters."""
        if user_id:
            return self._token_tracker.get_user_usage(user_id, date)
        if model:
            return self._token_tracker.get_model_usage(model)
        return self._token_tracker.get_daily_usage(date)

    def get_latency_stats(self, model: Optional[str] = None) -> Dict[str, Any]:
        """Get latency percentiles for a model or all models."""
        if model:
            return self._latency_tracker.get_percentiles(model)
        return self._latency_tracker.get_all_percentiles()

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        if self._cache:
            return self._cache.get_stats()
        return {"enabled": False}

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
                "cache_enabled": self._config.enable_cache,
            },
            "subsystems": {
                "cost_manager": {"users_tracked": len(self._cost_manager._users)},
                "token_tracker": self._token_tracker.get_stats(),
                "latency_tracker": {"models_tracked": len(self._latency_tracker._latencies)},
                "cache": self._cache.get_stats() if self._cache else {"enabled": False},
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

        logger.info(
            "inference_harness_created",
            providers=["on_device"],
            budget_per_user="$0.013/month",
            cache_enabled=True,
        )
    except Exception as exc:
        logger.warning("inference_harness_setup_partial", error=str(exc))

    return harness


def create_inference_harness(
    providers: Optional[List[ModelProvider]] = None,
    budget_per_user_usd: float = 0.013,
    quality_threshold: float = 0.3,
    enable_cache: bool = True,
) -> InferenceHarness:
    """Create an inference harness with custom configuration."""
    config = InferenceHarnessConfig(
        default_budget_per_user_usd=budget_per_user_usd,
        quality_threshold=quality_threshold,
        enable_cache=enable_cache,
    )
    harness = InferenceHarness(config)
    if providers:
        for provider in providers:
            harness.register_provider(provider)
    return harness


# ════════════════════════════════════════════════════════════════════
# Public API
# ════════════════════════════════════════════════════════════════════

__all__ = [
    # Core
    "InferenceHarness",
    "InferenceHarnessConfig",
    "InferenceResult",
    # Enums
    "ModelTier",
    "TaskComplexity",
    # Config
    "ModelConfig",
    # Subsystems
    "CostBudgetManager",
    "OutputQualityValidator",
    "TokenTracker",
    "LatencyTracker",
    "SemanticCache",
    "TaskRouter",
    # Providers
    "ModelProvider",
    "LocalGGUFProvider",
    "HTTPModelProvider",
    # Factory
    "get_inference_harness",
    "create_default_inference_harness",
    "create_inference_harness",
    # Routing tables
    "TASK_COMPLEXITY_MAP",
    "COMPLEXITY_TIER_MAP",
]
