"""
Cloud Reasoning Service — Gemini 3.5 Flash integration.
Wraps Gemini REST API with retry, cost tracking, and complexity classification.
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Dict, List, Optional

import structlog

from app.config.gemini import get_gemini_config

logger = structlog.get_logger(__name__)


class QueryComplexity(str, Enum):
    """Query complexity for routing decisions."""
    SIMPLE = "simple"      # "What's my balance?" → on-device
    MODERATE = "moderate"  # "How much did I spend on stock?" → either
    COMPLEX = "complex"    # "Compare cash flow and suggest cuts" → cloud


# Swahili + English keywords for complexity classification
_COMPLEX_KEYWORDS = frozenset([
    "compare", "analyze", "predict", "forecast", "suggest", "recommend",
    "optimize", "strategy", "plan", "budget", "trend", "pattern", "why",
    "linganisha", "changanua", "bashiri", "pendekeza", "mpango", "kwa nini",
    "tathimini", "uangalifu", "mwelekeo", "mfumo",
])

_SIMPLE_KEYWORDS = frozenset([
    "balance", "last", "show", "list", "how much", "total", "count",
    "salio", "mwisho", "onyesha", "orodha", "ngapi", "jumla", "hesabu",
])


def classify_complexity(query: str) -> QueryComplexity:
    """Classify query complexity using keyword matching (no LLM needed)."""
    lower = query.lower()
    words = lower.split()

    if any(kw in lower for kw in _COMPLEX_KEYWORDS):
        return QueryComplexity.COMPLEX
    if any(kw in lower for kw in _SIMPLE_KEYWORDS) and len(words) < 8:
        return QueryComplexity.SIMPLE
    return QueryComplexity.MODERATE


@dataclass
class CloudResponse:
    """Response from cloud reasoning."""
    text: str
    tokens_used: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    function_calls: List[str] = field(default_factory=list)
    model: str = ""
    cached: bool = False


class CloudReasoningService:
    """
    Gemini 3.5 Flash cloud reasoning service.
    
    Handles:
    - Query complexity classification
    - Gemini REST API calls with retry
    - Per-user cost tracking
    - Rate limiting
    - Graceful degradation
    """

    def __init__(self) -> None:
        self._config = get_gemini_config()
        self._user_daily_tokens: Dict[str, int] = {}  # user_id → tokens used today
        self._user_daily_queries: Dict[str, int] = {}  # user_id → queries today
        self._daily_token_budget_remaining = self._config.tokens_per_day
        self._last_reset_day = 0

    @property
    def enabled(self) -> bool:
        return self._config.enabled and bool(self._config.api_key)

    async def reason(
        self,
        query: str,
        user_id: str,
        transaction_context: str = "",
        system_prompt: str = "",
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[CloudResponse]:
        """
        Send a query to Gemini for cloud reasoning.
        
        Returns None if:
        - Cloud reasoning is disabled
        - User exceeded daily budget
        - Global token budget exhausted
        - Network error (after retries)
        """
        if not self.enabled:
            logger.debug("cloud_reasoning.disabled")
            return None

        # Budget checks
        if not self._check_budget(user_id):
            logger.warning("cloud_reasoning.budget_exceeded", user_id=user_id)
            return None

        # Rate limit check
        if not self._check_rate_limit(user_id):
            logger.warning("cloud_reasoning.rate_limited", user_id=user_id)
            return None

        start_time = time.monotonic()

        try:
            response = await self._call_gemini(query, transaction_context, system_prompt, tools)
            latency_ms = (time.monotonic() - start_time) * 1000

            # Calculate cost
            cost = self._calculate_cost(response.input_tokens, response.output_tokens)
            response.cost_usd = cost
            response.latency_ms = latency_ms
            response.model = self._config.model

            # Track usage
            self._track_usage(user_id, response.tokens_used, cost)

            logger.info(
                "cloud_reasoning.success",
                user_id=user_id,
                tokens=response.tokens_used,
                cost_usd=round(cost, 6),
                latency_ms=round(latency_ms, 1),
            )

            return response

        except Exception as e:
            latency_ms = (time.monotonic() - start_time) * 1000
            logger.error(
                "cloud_reasoning.error",
                user_id=user_id,
                error=str(e),
                latency_ms=round(latency_ms, 1),
            )
            return None

    async def _call_gemini(
        self,
        query: str,
        transaction_context: str,
        system_prompt: str,
        tools: Optional[List[Dict[str, Any]]],
    ) -> CloudResponse:
        """Make REST API call to Gemini with retry."""
        import httpx

        url = f"{self._config.base_url}/models/{self._config.model}:generateContent?key={self._config.api_key}"

        # Build request
        contents = []
        if system_prompt:
            contents.append({"role": "user", "parts": [{"text": f"System: {system_prompt}"}]})

        user_text = query
        if transaction_context:
            user_text = f"{query}\n\n=== Transaction Context ===\n{transaction_context}"
        contents.append({"role": "user", "parts": [{"text": user_text}]})

        body: Dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": self._config.max_tokens_per_query,
                "temperature": self._config.temperature,
            },
        }

        if tools and self._config.function_calling_enabled:
            body["tools"] = [{"functionDeclarations": tools}]

        # Retry with exponential backoff
        last_error = None
        for attempt in range(self._config.max_retries + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(
                        connect=self._config.connect_timeout_seconds,
                        read=self._config.read_timeout_seconds,
                    )
                ) as client:
                    resp = await client.post(url, json=body)

                    if resp.status_code == 429:
                        # Rate limited — back off
                        retry_after = int(resp.headers.get("Retry-After", 2 ** attempt))
                        logger.warning("cloud_reasoning.rate_limited_by_api", retry_after=retry_after)
                        await asyncio.sleep(retry_after)
                        continue

                    resp.raise_for_status()
                    data = resp.json()

                    return self._parse_response(data)

            except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
                last_error = e
                if attempt < self._config.max_retries:
                    await asyncio.sleep(2 ** attempt)
                    continue

        raise last_error or RuntimeError("Gemini API call failed after retries")

    def _parse_response(self, data: Dict[str, Any]) -> CloudResponse:
        """Parse Gemini API response."""
        candidates = data.get("candidates", [])
        if not candidates:
            return CloudResponse(text="No response from cloud reasoning.")

        candidate = candidates[0]
        content = candidate.get("content", {})
        parts = content.get("parts", [])

        text_parts = []
        function_calls = []
        for part in parts:
            if "text" in part:
                text_parts.append(part["text"])
            if "functionCall" in part:
                fc = part["functionCall"]
                function_calls.append(fc.get("name", "unknown"))

        usage = data.get("usageMetadata", {})

        return CloudResponse(
            text="\n".join(text_parts),
            tokens_used=usage.get("totalTokenCount", 0),
            input_tokens=usage.get("promptTokenCount", 0),
            output_tokens=usage.get("candidatesTokenCount", 0),
            function_calls=function_calls,
        )

    def _calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Calculate USD cost for a request."""
        cfg = self._config
        input_cost = (input_tokens / 1_000_000) * cfg.cost_per_million_input_tokens
        output_cost = (output_tokens / 1_000_000) * cfg.cost_per_million_output_tokens
        return input_cost + output_cost

    def _check_budget(self, user_id: str) -> bool:
        """Check if user is within daily budget."""
        import time as _time
        today = int(_time.time() // 86400)
        if today != self._last_reset_day:
            self._user_daily_tokens.clear()
            self._user_daily_queries.clear()
            self._daily_token_budget_remaining = self._config.tokens_per_day
            self._last_reset_day = today

        user_queries = self._user_daily_queries.get(user_id, 0)
        if user_queries >= self._config.max_queries_per_user_per_day:
            return False

        if self._daily_token_budget_remaining <= 0:
            return False

        return True

    def _check_rate_limit(self, user_id: str) -> bool:
        """Simple per-user rate limiting."""
        return True  # Handled by budget check + API 429 handling

    def _track_usage(self, user_id: str, tokens: int, cost: float) -> None:
        """Track token usage for budget enforcement."""
        self._user_daily_tokens[user_id] = self._user_daily_tokens.get(user_id, 0) + tokens
        self._user_daily_queries[user_id] = self._user_daily_queries.get(user_id, 0) + 1
        self._daily_token_budget_remaining -= tokens
