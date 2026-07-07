"""
Model Router — Hybrid Reasoning Model Router for Angavu Intelligence.

Routes inference requests across multiple providers with:
- Smart provider selection based on task type and complexity
- Cost-aware routing ($0.013/user/month target)
- Reasoning chain storage for auditability and learning
- Financial reasoning templates for informal economy tasks
- Token compression for cost optimization
- Automatic fallback on provider failure
- Per-user budget tracking

## Cost Model (Swarm 2 Research)
| Layer             | Queries/Day | Tokens/Query | Monthly Cost |
|-------------------|-------------|--------------|--------------|
| On-Device (free)  | 40          | 500          | $0.00        |
| Cloud Reasoning   | 8           | 2,000        | $0.01        |
| Cloud Premium     | 2           | 5,000        | $0.003       |
| **Total**         | **50**      | —            | **$0.013**   |

## Fallback Chain
on-device → DeepSeek V4 Flash → GPT-5.4 nano → Claude Haiku → backend

Usage:
    router = ModelRouter()
    response = await router.infer(messages=[...], task_complexity="medium")
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from enum import Enum
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


# ═══════════════════════════════════════════════════════════════
# Task Types for Financial Reasoning Routing
# ═══════════════════════════════════════════════════════════════


class TaskType(str, Enum):
    """Task types for routing decisions based on Swarm 2 research."""
    GENERAL = "general"
    TRANSACTION_RECORDING = "transaction_recording"  # Simple → on-device
    BALANCE_INQUIRY = "balance_inquiry"              # Simple → on-device
    PRICE_LOOKUP = "price_lookup"                    # Simple → on-device
    CASH_FLOW_ALERT = "cash_flow_alert"              # On-device, complex → cloud
    CREDIT_ASSESSMENT = "credit_assessment"           # Cloud reasoning primary
    MARKET_FORECASTING = "market_forecasting"         # Cloud reasoning primary
    RISK_ASSESSMENT = "risk_assessment"               # Cloud reasoning primary
    GROWTH_PLANNING = "growth_planning"               # Cloud premium primary
    DAILY_BRIEFING = "daily_briefing"                 # Template on-device, content cloud
    FINANCIAL_ANALYSIS = "financial_analysis"          # Cloud reasoning


class ReasoningEffort(str, Enum):
    """Test-time compute scaling levels."""
    NONE = "none"         # Instant, no thinking tokens
    LIGHT = "light"       # Quick reasoning (256 tokens)
    STANDARD = "standard" # Normal reasoning (512 tokens)
    EXTENDED = "extended" # Deep reasoning (1024 tokens)
    XHIGH = "xhigh"       # Maximum reasoning (2048 tokens)


class FinancialTemplate(str, Enum):
    """Pre-built reasoning templates for common informal economy tasks."""
    PRICE_ANALYSIS = "price_analysis"
    CREDIT_ASSESSMENT = "credit_assessment"
    CASH_FLOW_ANALYSIS = "cash_flow_analysis"
    RISK_ASSESSMENT = "risk_assessment"
    MARKET_FORECAST = "market_forecast"
    GROWTH_PLANNING = "growth_planning"
    DAILY_BRIEFING = "daily_briefing"
    INVENTORY_OPTIMIZATION = "inventory_optimization"
    SUPPLIER_ANALYSIS = "supplier_analysis"
    PROFITABILITY_ANALYSIS = "profitability_analysis"


# Task type → preferred provider chain
# Based on Swarm 2: 80% on-device, 15% cloud reasoning, 5% premium
TASK_ROUTING_TABLE: Dict[str, List[str]] = {
    TaskType.TRANSACTION_RECORDING: ["on-device"],
    TaskType.BALANCE_INQUIRY: ["on-device"],
    TaskType.PRICE_LOOKUP: ["on-device"],
    TaskType.CASH_FLOW_ALERT: ["on-device", "deepseek-flash"],
    TaskType.DAILY_BRIEFING: ["on-device", "deepseek-flash"],
    TaskType.CREDIT_ASSESSMENT: ["deepseek-flash", "gpt-nano", "claude-haiku"],
    TaskType.MARKET_FORECASTING: ["deepseek-flash", "gpt-nano", "claude-haiku"],
    TaskType.RISK_ASSESSMENT: ["deepseek-flash", "gpt-nano", "claude-haiku"],
    TaskType.FINANCIAL_ANALYSIS: ["deepseek-flash", "gpt-nano"],
    TaskType.GROWTH_PLANNING: ["claude-haiku", "deepseek-flash", "gpt-nano"],
    TaskType.GENERAL: ["on-device", "deepseek-flash", "gpt-nano", "backend"],
}


# ═══════════════════════════════════════════════════════════════
# Reasoning Chain Storage
# ═══════════════════════════════════════════════════════════════


class ReasoningStep:
    """A single step in a reasoning chain."""
    def __init__(self, step_number: int, step_type: str, content: str, confidence: float = 1.0):
        self.step_number = step_number
        self.step_type = step_type  # observe, think, act, reflect, template_inject
        self.content = content
        self.confidence = confidence
        self.timestamp = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step": self.step_number,
            "type": self.step_type,
            "content": self.content,
            "confidence": self.confidence,
            "timestamp": self.timestamp,
        }


class ReasoningChain:
    """
    Stores step-by-step reasoning for auditability and learning.

    Based on Swarm 2 finding: reasoning chains enable:
    - Auditability of financial decisions
    - Learning from successful reasoning patterns
    - Debugging when reasoning goes wrong
    """
    def __init__(self, chain_id: str, request_id: str, template: Optional[str] = None):
        self.chain_id = chain_id
        self.request_id = request_id
        self.template = template
        self.steps: List[ReasoningStep] = []
        self.model_used: str = ""
        self.total_thinking_tokens: int = 0
        self.started_at: float = time.time()
        self.completed_at: float = 0.0
        self.success: bool = False

    def add_step(self, step_type: str, content: str, confidence: float = 1.0) -> None:
        step = ReasoningStep(
            step_number=len(self.steps),
            step_type=step_type,
            content=content,
            confidence=confidence,
        )
        self.steps.append(step)

    def complete(self, success: bool) -> None:
        self.success = success
        self.completed_at = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chain_id": self.chain_id,
            "request_id": self.request_id,
            "template": self.template,
            "steps": [s.to_dict() for s in self.steps],
            "model_used": self.model_used,
            "thinking_tokens": self.total_thinking_tokens,
            "duration_ms": (self.completed_at - self.started_at) * 1000,
            "success": self.success,
        }


# ═══════════════════════════════════════════════════════════════
# Financial Reasoning Templates
# ═══════════════════════════════════════════════════════════════


FINANCIAL_TEMPLATES: Dict[str, str] = {
    FinancialTemplate.PRICE_ANALYSIS: """Analyze pricing for an informal market vendor.
Data: {data} | Product: {product}
Step by step: current price vs market, factors (season/supply/demand), optimal price, volume impact.
Provide: recommended price, reasoning, expected impact, confidence.""",

    FinancialTemplate.CREDIT_ASSESSMENT: """Assess creditworthiness for an informal economy worker.
History: {history} | Business: {business_type}
Analyze: transaction consistency, revenue trend, cash flow patterns, risk factors.
Alternative signals: mobile money, utility payments, inventory turnover, customer diversity.
Provide: credit score (0-100), risk level, recommendation.""",

    FinancialTemplate.CASH_FLOW_ANALYSIS: """Analyze cash flow for a small business.
Income: {income} | Expenses: {expenses} | Period: {period}
Analyze: net cash flow, timing, safety buffer, upcoming obligations.
Identify cash crunch risks and suggest mitigation.""",

    FinancialTemplate.RISK_ASSESSMENT: """Assess business risk for an informal vendor.
Profile: {profile} | Market: {market}
Evaluate: market risk, supply chain, weather/environmental, financial, operational.
For each: probability, impact, mitigation. Suggest micro-insurance if applicable.""",

    FinancialTemplate.MARKET_FORECAST: """Forecast market conditions for a vendor.
History: {history} | Market: {market_type}
Consider: seasonal patterns, supply trends, demand patterns, external factors.
Provide 7-day and 30-day forecast with confidence levels.""",

    FinancialTemplate.GROWTH_PLANNING: """Create growth plan for a micro-entrepreneur.
Business: {business} | Financials: {financials} | Goals: {goals}
Assess current state, rank opportunities (volume/margin/products/location/hiring),
analyze investment ROI, create 30/60/90 day plan.""",

    FinancialTemplate.DAILY_BRIEFING: """Generate morning briefing for a vendor.
Yesterday: {yesterday} | Goals: {goals} | Weather: {weather}
Include: yesterday recap, today's priority, goal progress, tip.
Keep SHORT (3-5 sentences). Simple language.""",

    FinancialTemplate.INVENTORY_OPTIMIZATION: """Optimize inventory for a vendor.
Stock: {stock} | Sales: {sales}
Analyze: turnover, fast/slow movers, reorder points, product mix.
Recommend: what to increase/decrease/add.""",

    FinancialTemplate.SUPPLIER_ANALYSIS: """Analyze suppliers for a vendor.
Suppliers: {suppliers} | Purchases: {purchases}
Evaluate: price, reliability, quality, payment terms, dependency risk.
Recommend: diversification, cost savings.""",

    FinancialTemplate.PROFITABILITY_ANALYSIS: """Analyze profitability for a business.
Revenue: {revenue} | Costs: {costs} | Period: {period}
Calculate: gross/net margins, most/least profitable items, break-even.
Recommend: actions to improve profitability.""",
}


def get_financial_template_prompt(template: str, context: Dict[str, str] = None) -> Optional[str]:
    """Get a financial reasoning template prompt with context injected."""
    template_text = FINANCIAL_TEMPLATES.get(template)
    if not template_text:
        return None
    if context:
        for key, value in context.items():
            template_text = template_text.replace(f"{{{key}}}", value)
    return template_text


class ModelRouter:
    """
    Hybrid Reasoning Model Router for Angavu Intelligence.

    Orchestrates:
    - Task-aware provider selection (routing table by task type)
    - Cost-aware routing ($0.013/user/month target)
    - Reasoning chain storage for auditability
    - Financial template injection
    - Token compression (via TokenCompressor)
    - Fallback handling (via FallbackHandler)
    - Per-user budget tracking
    """

    # Monthly budget per user: $0.013 = 13,000 micro-dollars
    MONTHLY_BUDGET_MICROS = 13_000
    DAILY_BUDGET_MICROS = 433  # $0.013 / 30
    ALERT_THRESHOLD_PCT = 0.8

    def __init__(
        self,
        provider_registry: Optional[ProviderRegistry] = None,
        token_compressor: Optional[TokenCompressor] = None,
        fallback_handler: Optional[FallbackHandler] = None,
        enable_compression: bool = True,
        compression_threshold_tokens: int = 2000,
        default_max_tokens: int = 1024,
        default_temperature: float = 0.7,
        enable_reasoning_chains: bool = True,
    ):
        self.registry = provider_registry or get_provider_registry()
        self.compressor = token_compressor or get_token_compressor()
        self.fallback = fallback_handler or get_fallback_handler(self.registry)
        self.enable_compression = enable_compression
        self.compression_threshold_tokens = compression_threshold_tokens
        self.default_max_tokens = default_max_tokens
        self.default_temperature = default_temperature
        self.enable_reasoning_chains = enable_reasoning_chains

        # Usage tracking
        self._usage_log: List[Dict[str, Any]] = []
        self._max_log = 500
        self._total_tokens_in: int = 0
        self._total_tokens_out: int = 0
        self._total_cost: float = 0.0
        self._requests_by_provider: Dict[str, int] = defaultdict(int)
        self._requests_by_model: Dict[str, int] = defaultdict(int)
        self._requests_by_task_type: Dict[str, int] = defaultdict(int)

        # Per-user cost tracking
        self._user_monthly_cost: Dict[str, float] = defaultdict(float)
        self._user_daily_cost: Dict[str, float] = defaultdict(float)
        self._current_month: int = datetime.now(timezone.utc).month
        self._current_day: int = datetime.now(timezone.utc).timetuple().tm_yday

        # Reasoning chain storage
        self._reasoning_chains: Dict[str, ReasoningChain] = {}
        self._max_chains = 100

    async def infer(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        task_complexity: str = "medium",
        task_type: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
        financial_template: Optional[str] = None,
        template_context: Optional[Dict[str, str]] = None,
        preferred_providers: Optional[List[str]] = None,
        enable_compression: Optional[bool] = None,
        request_id: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> InferenceResponse:
        """
        Route an inference request to the optimal provider.

        Hybrid routing logic:
        1. Check user budget (force on-device if over budget)
        2. Classify task type for routing table lookup
        3. Inject financial reasoning template if applicable
        4. Build provider chain from routing table
        5. Execute with fallback
        6. Store reasoning chain for auditability

        Args:
            messages: Conversation messages [{role, content}, ...]
            model: Preferred model name (optional)
            max_tokens: Max output tokens
            temperature: Sampling temperature
            task_complexity: "low", "medium", "high"
            task_type: Task type for routing (see TaskType enum)
            reasoning_effort: Test-time compute level (see ReasoningEffort enum)
            financial_template: Financial template to inject (see FinancialTemplate enum)
            template_context: Context variables for the template
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

        # Reset daily/monthly counters if needed
        self._reset_counters_if_needed()

        # Step 0: Check user budget
        budget_forced_on_device = False
        if user_id:
            budget_status = self._check_budget(user_id)
            if budget_status["is_over_budget"]:
                logger.warning(
                    "user_over_budget",
                    user_id=user_id,
                    monthly_used=budget_status["monthly_used"],
                    budget=self.MONTHLY_BUDGET_MICROS,
                )
                # Force on-device only
                preferred_providers = ["on-device"]
                budget_forced_on_device = True
            elif budget_status["is_near_budget"]:
                # Prefer cheaper providers
                logger.info("user_near_budget", user_id=user_id)

        # Step 1: Inject financial template if provided
        if financial_template and financial_template in FINANCIAL_TEMPLATES:
            template_prompt = get_financial_template_prompt(
                financial_template, template_context or {}
            )
            if template_prompt:
                messages = [
                    {"role": "system", "content": template_prompt},
                    *messages,
                ]

        # Step 2: Compress if needed
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

        # Step 3: Build inference request
        request = InferenceRequest(
            request_id=request_id,
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            task_complexity=task_complexity,
            metadata=metadata or {},
        )

        # Step 4: Initialize reasoning chain
        chain: Optional[ReasoningChain] = None
        if self.enable_reasoning_chains:
            chain = ReasoningChain(
                chain_id=uuid.uuid4().hex[:12],
                request_id=request_id,
                template=financial_template,
            )
            if financial_template:
                chain.add_step("template_inject", f"Injected {financial_template} template")
            chain.add_step("think", f"Task type: {task_type or 'general'}, complexity: {task_complexity}")

        # Step 5: Determine provider chain
        effective_providers = preferred_providers
        if not effective_providers and task_type and task_type in TASK_ROUTING_TABLE:
            effective_providers = TASK_ROUTING_TABLE[task_type]
            if chain:
                chain.add_step("think", f"Routing table: {effective_providers}")

        # Step 6: Execute with fallback
        start_time = time.time()

        async def _execute(provider_id: str, req: InferenceRequest) -> InferenceResponse:
            if chain:
                chain.add_step("act", f"Calling provider: {provider_id}")
            return await self._call_provider(provider_id, req)

        response = await self.fallback.execute_with_fallback(
            request=request,
            inference_func=_execute,
            preferred_providers=effective_providers,
        )

        # Step 7: Attach metadata
        response.compression_info = compression_info
        response.metadata["task_type"] = task_type or "general"
        response.metadata["financial_template"] = financial_template
        response.metadata["budget_forced_on_device"] = budget_forced_on_device

        # Step 8: Complete reasoning chain
        if chain:
            chain.model_used = response.model_used
            chain.add_step("act", f"Response: {response.output_tokens} tokens from {response.provider_id}")
            chain.complete(success=bool(response.content))
            self._store_reasoning_chain(chain)
            response.metadata["reasoning_chain_id"] = chain.chain_id

        # Step 9: Track usage
        self._track_usage(response, user_id, task_type)

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

    def _track_usage(
        self,
        response: InferenceResponse,
        user_id: Optional[str] = None,
        task_type: Optional[str] = None,
    ):
        """Track usage statistics with per-user cost tracking."""
        self._total_tokens_in += response.input_tokens
        self._total_tokens_out += response.output_tokens
        self._requests_by_provider[response.provider_id] += 1
        self._requests_by_model[response.model_used] += 1
        if task_type:
            self._requests_by_task_type[task_type] += 1

        # Estimate cost
        provider = self.registry.get(response.provider_id)
        cost = 0.0
        if provider:
            cost = (
                response.input_tokens * provider.cost_per_1k_input / 1000
                + response.output_tokens * provider.cost_per_1k_output / 1000
            )
            self._total_cost += cost
            response.metadata["cost_estimate"] = cost

        # Per-user cost tracking
        if user_id and cost > 0:
            cost_micros = cost * 1_000_000
            self._user_monthly_cost[user_id] += cost_micros
            self._user_daily_cost[user_id] += cost_micros

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
            "task_type": task_type,
            "cost_estimate": cost,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._usage_log.append(entry)
        if len(self._usage_log) > self._max_log:
            self._usage_log = self._usage_log[-self._max_log:]

    def _check_budget(self, user_id: str) -> Dict[str, Any]:
        """Check user's monthly and daily budget status."""
        monthly_used = self._user_monthly_cost.get(user_id, 0.0)
        daily_used = self._user_daily_cost.get(user_id, 0.0)
        return {
            "user_id": user_id,
            "monthly_used": monthly_used,
            "monthly_budget": self.MONTHLY_BUDGET_MICROS,
            "daily_used": daily_used,
            "daily_budget": self.DAILY_BUDGET_MICROS,
            "monthly_pct": monthly_used / self.MONTHLY_BUDGET_MICROS if self.MONTHLY_BUDGET_MICROS else 0,
            "is_over_budget": monthly_used >= self.MONTHLY_BUDGET_MICROS,
            "is_near_budget": monthly_used >= self.MONTHLY_BUDGET_MICROS * self.ALERT_THRESHOLD_PCT,
        }

    def _reset_counters_if_needed(self) -> None:
        """Reset daily/monthly counters on period change."""
        now = datetime.now(timezone.utc)
        if now.month != self._current_month:
            self._current_month = now.month
            self._user_monthly_cost.clear()
        if now.timetuple().tm_yday != self._current_day:
            self._current_day = now.timetuple().tm_yday
            self._user_daily_cost.clear()

    def _store_reasoning_chain(self, chain: ReasoningChain) -> None:
        """Store reasoning chain, evicting oldest if at capacity."""
        if len(self._reasoning_chains) >= self._max_chains:
            # Evict oldest
            oldest_key = min(
                self._reasoning_chains.keys(),
                key=lambda k: self._reasoning_chains[k].started_at,
            )
            del self._reasoning_chains[oldest_key]
        self._reasoning_chains[chain.chain_id] = chain

    def get_reasoning_chain(self, chain_id: str) -> Optional[Dict[str, Any]]:
        """Get a reasoning chain by ID."""
        chain = self._reasoning_chains.get(chain_id)
        return chain.to_dict() if chain else None

    def get_recent_reasoning_chains(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent reasoning chains."""
        chains = sorted(
            self._reasoning_chains.values(),
            key=lambda c: c.started_at,
            reverse=True,
        )[:limit]
        return [c.to_dict() for c in chains]

    def get_user_budget_status(self, user_id: str) -> Dict[str, Any]:
        """Get budget status for a specific user."""
        return self._check_budget(user_id)

    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive routing and usage statistics."""
        return {
            "total_requests": len(self._usage_log),
            "total_tokens_input": self._total_tokens_in,
            "total_tokens_output": self._total_tokens_out,
            "total_cost_estimate": round(self._total_cost, 6),
            "requests_by_provider": dict(self._requests_by_provider),
            "requests_by_model": dict(self._requests_by_model),
            "requests_by_task_type": dict(self._requests_by_task_type),
            "compression_stats": self.compressor.get_stats(),
            "fallback_stats": self.fallback.get_stats(),
            "provider_health": self.registry.get_health_summary(),
            "reasoning_chains_stored": len(self._reasoning_chains),
            "active_users_tracked": len(self._user_monthly_cost),
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
            "by_task_type": dict(self._requests_by_task_type),
            "target_cost_per_user_month": 0.013,
            "active_users": len(self._user_monthly_cost),
        }


# Singleton
_router: Optional[ModelRouter] = None


def get_model_router() -> ModelRouter:
    global _router
    if _router is None:
        _router = ModelRouter()
    return _router
