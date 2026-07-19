"""
Agent Cost Tracker — Per-agent, per-swarm, per-domain cost tracking.

Bridges InferenceHarness cost data → AgentMetricsCollector → Prometheus.

Architecture:
    InferenceHarness.infer()
        │
        ▼
    ExecutionRecord (cost_usd, input_tokens, output_tokens)
        │
        ▼
    AgentCostTracker
        ├── Per-agent counters (Prometheus Gauge)
        ├── Per-swarm aggregation (Prometheus Gauge)
        ├── Per-domain breakdown (Prometheus Gauge)
        └── Budget alerts (event bus → Governance swarm)

Feature flag: Wire into agents via set_cost_tracker() — None means disabled.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from app.agents.event_bus import EventBus

logger = structlog.get_logger(__name__)

# ── Prometheus Metrics ──────────────────────────────────────────────

try:
    from prometheus_client import Counter, Gauge, Histogram
    from app.infrastructure.metrics import _registry

    # Per-agent token usage
    AGENT_TOKENS_INPUT = Counter(
        "angavu_agent_tokens_input_total",
        "Total input tokens consumed per agent",
        ["agent_name", "swarm", "model"],
        registry=_registry,
    )

    AGENT_TOKENS_OUTPUT = Counter(
        "angavu_agent_tokens_output_total",
        "Total output tokens consumed per agent",
        ["agent_name", "swarm", "model"],
        registry=_registry,
    )

    # Per-agent cost
    AGENT_COST_USD = Counter(
        "angavu_agent_cost_usd_total",
        "Total cost in USD per agent",
        ["agent_name", "swarm", "domain"],
        registry=_registry,
    )

    # Per-swarm cost
    SWARM_COST_USD = Counter(
        "angavu_swarm_cost_usd_total",
        "Total cost in USD per swarm",
        ["swarm"],
        registry=_registry,
    )

    # Per-domain cost
    DOMAIN_COST_USD = Counter(
        "angavu_domain_cost_usd_total",
        "Total cost in USD per business domain",
        ["domain"],
        registry=_registry,
    )

    # Cost per evaluation loop
    EVALUATION_COST_USD = Counter(
        "angavu_evaluation_cost_usd_total",
        "Cost of self-evaluation loops",
        ["agent_name", "verdict"],
        registry=_registry,
    )

    EVALUATION_TOKENS = Counter(
        "angavu_evaluation_tokens_total",
        "Tokens consumed by self-evaluation",
        ["agent_name"],
        registry=_registry,
    )

    # Cost rate (USD per hour, gauge for current rate)
    COST_RATE_USD_PER_HOUR = Gauge(
        "angavu_cost_rate_usd_per_hour",
        "Current cost rate in USD per hour",
        ["agent_name"],
        registry=_registry,
    )

    # Budget utilization
    BUDGET_UTILIZATION = Gauge(
        "angavu_budget_utilization_ratio",
        "Budget utilization ratio (0.0-1.0+)",
        ["scope"],  # "agent:{name}", "swarm:{name}", "domain:{name}", "total"
        registry=_registry,
    )

    # Inference latency by tier
    INFERENCE_LATENCY_BY_TIER = Histogram(
        "angavu_inference_latency_seconds",
        "Inference latency by model tier",
        ["tier", "agent_name"],
        buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
        registry=_registry,
    )

    # Model fallback counter
    MODEL_FALLBACK_TOTAL = Counter(
        "angavu_model_fallback_total",
        "Number of model fallbacks",
        ["from_model", "to_model", "reason"],
        registry=_registry,
    )

    COST_PROMETHEUS_AVAILABLE = True

except ImportError:
    COST_PROMETHEUS_AVAILABLE = False


# ════════════════════════════════════════════════════════════════════
# Cost Tracker
# ════════════════════════════════════════════════════════════════════


@dataclass
class CostBudget:
    """Budget configuration for a scope (agent, swarm, domain, total)."""
    scope: str                      # e.g. "agent:IntelligenceGenerator"
    daily_limit_usd: float = 1.0    # Daily budget
    monthly_limit_usd: float = 25.0 # Monthly budget
    alert_threshold_pct: float = 0.8  # Alert at 80% utilization


@dataclass
class CostRecord:
    """A single cost event."""
    agent_name: str
    swarm: str = ""
    domain: str = ""
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    timestamp: float = field(default_factory=time.time)
    source: str = "inference"  # "inference" | "evaluation"


class AgentCostTracker:
    """
    Per-agent, per-swarm, per-domain cost tracking with Prometheus export.

    Integrates with:
    - AgentExecutionHarness (receives ExecutionRecord with cost data)
    - SelfEvaluationMiddleware (tracks evaluation loop costs)
    - InferenceHarness (receives InferenceResult with token/cost data)
    - Event Bus (emits budget alerts to Governance swarm)

    Usage:
        tracker = AgentCostTracker()
        tracker.set_budget("agent:IntelligenceGenerator", daily_limit_usd=5.0)

        # Record a cost event
        tracker.record(CostRecord(
            agent_name="IntelligenceGenerator",
            swarm="intelligence",
            domain="retail",
            input_tokens=500,
            output_tokens=200,
            cost_usd=0.003,
        ))

        # Get stats
        stats = tracker.get_stats()
    """

    def __init__(self, event_bus: Optional[Any] = None):
        self._records: List[CostRecord] = []
        self._max_records = 50_000
        self._event_bus = event_bus
        self._logger = logger.bind(component="cost_tracker")

        # Agent → swarm mapping
        self._agent_swarm: Dict[str, str] = {}
        # Agent → domain mapping
        self._agent_domain: Dict[str, str] = {}

        # Budgets
        self._budgets: Dict[str, CostBudget] = {}

        # Running totals (in-memory, reset daily)
        self._daily_costs: Dict[str, float] = defaultdict(float)
        self._daily_swarm_costs: Dict[str, float] = defaultdict(float)
        self._daily_domain_costs: Dict[str, float] = defaultdict(float)
        self._daily_total: float = 0.0
        self._current_day: str = ""

        # Rate tracking (for cost/hour calculation)
        self._rate_window: Dict[str, List[float]] = defaultdict(list)
        self._rate_window_seconds = 3600  # 1 hour

    def register_agent(
        self,
        agent_name: str,
        swarm: str = "",
        domain: str = "",
    ) -> None:
        """Register an agent with its swarm and domain."""
        self._agent_swarm[agent_name] = swarm
        self._agent_domain[agent_name] = domain

    def set_budget(
        self,
        scope: str,
        daily_limit_usd: float = 1.0,
        monthly_limit_usd: float = 25.0,
        alert_threshold_pct: float = 0.8,
    ) -> None:
        """Set a cost budget for a scope."""
        self._budgets[scope] = CostBudget(
            scope=scope,
            daily_limit_usd=daily_limit_usd,
            monthly_limit_usd=monthly_limit_usd,
            alert_threshold_pct=alert_threshold_pct,
        )

    def record(self, record: CostRecord) -> None:
        """Record a cost event and update all tracking."""
        # Auto-resolve swarm/domain if not provided
        if not record.swarm:
            record.swarm = self._agent_swarm.get(record.agent_name, "unknown")
        if not record.domain:
            record.domain = self._agent_domain.get(record.agent_name, "unknown")

        # Store record
        self._records.append(record)
        if len(self._records) > self._max_records:
            self._records = self._records[-self._max_records:]

        # Update daily totals (reset if new day)
        self._maybe_reset_daily()

        self._daily_costs[record.agent_name] += record.cost_usd
        self._daily_swarm_costs[record.swarm] += record.cost_usd
        self._daily_domain_costs[record.domain] += record.cost_usd
        self._daily_total += record.cost_usd

        # Update rate tracking
        now = time.time()
        self._rate_window[record.agent_name].append(now)
        # Trim old entries
        cutoff = now - self._rate_window_seconds
        self._rate_window[record.agent_name] = [
            t for t in self._rate_window[record.agent_name] if t > cutoff
        ]

        # Export to Prometheus
        self._export_prometheus(record)

        # Check budgets
        self._check_budgets(record)

    def record_evaluation_cost(
        self,
        agent_name: str,
        tokens_used: int,
        cost_usd: float,
        verdict: str,
    ) -> None:
        """Record cost from self-evaluation loop."""
        self.record(CostRecord(
            agent_name=agent_name,
            input_tokens=tokens_used,
            cost_usd=cost_usd,
            source="evaluation",
        ))

        if COST_PROMETHEUS_AVAILABLE:
            EVALUATION_COST_USD.labels(
                agent_name=agent_name,
                verdict=verdict,
            ).inc(cost_usd)
            EVALUATION_TOKENS.labels(
                agent_name=agent_name,
            ).inc(tokens_used)

    def _export_prometheus(self, record: CostRecord) -> None:
        """Export cost data to Prometheus metrics."""
        if not COST_PROMETHEUS_AVAILABLE:
            return

        AGENT_TOKENS_INPUT.labels(
            agent_name=record.agent_name,
            swarm=record.swarm,
            model=record.model,
        ).inc(record.input_tokens)

        AGENT_TOKENS_OUTPUT.labels(
            agent_name=record.agent_name,
            swarm=record.swarm,
            model=record.model,
        ).inc(record.output_tokens)

        AGENT_COST_USD.labels(
            agent_name=record.agent_name,
            swarm=record.swarm,
            domain=record.domain,
        ).inc(record.cost_usd)

        SWARM_COST_USD.labels(
            swarm=record.swarm,
        ).inc(record.cost_usd)

        DOMAIN_COST_USD.labels(
            domain=record.domain,
        ).inc(record.cost_usd)

        # Update cost rate gauge
        rate = self._compute_rate(record.agent_name)
        COST_RATE_USD_PER_HOUR.labels(
            agent_name=record.agent_name,
        ).set(rate)

    def _compute_rate(self, agent_name: str) -> float:
        """Compute current cost rate (USD/hour) for an agent."""
        window = self._rate_window.get(agent_name, [])
        if len(window) < 2:
            return 0.0

        # Count records in last hour
        now = time.time()
        cutoff = now - self._rate_window_seconds
        recent_records = [r for r in self._records if r.agent_name == agent_name and r.timestamp > cutoff]
        total_cost = sum(r.cost_usd for r in recent_records)

        # Extrapolate to hourly rate
        elapsed = now - min(r.timestamp for r in recent_records) if recent_records else 3600
        if elapsed < 60:
            elapsed = 60  # Minimum 1 minute window

        return total_cost * 3600 / elapsed

    def _maybe_reset_daily(self) -> None:
        """Reset daily counters if it's a new day."""
        import datetime
        today = datetime.date.today().isoformat()
        if today != self._current_day:
            self._daily_costs.clear()
            self._daily_swarm_costs.clear()
            self._daily_domain_costs.clear()
            self._daily_total = 0.0
            self._current_day = today

    def _check_budgets(self, record: CostRecord) -> None:
        """Check if any budget thresholds are exceeded."""
        scopes_to_check = [
            f"agent:{record.agent_name}",
            f"swarm:{record.swarm}",
            f"domain:{record.domain}",
            "total",
        ]

        for scope in scopes_to_check:
            budget = self._budgets.get(scope)
            if not budget:
                continue

            # Get current daily spend for this scope
            if scope.startswith("agent:"):
                agent = scope.split(":", 1)[1]
                current = self._daily_costs.get(agent, 0.0)
            elif scope.startswith("swarm:"):
                swarm = scope.split(":", 1)[1]
                current = self._daily_swarm_costs.get(swarm, 0.0)
            elif scope.startswith("domain:"):
                domain = scope.split(":", 1)[1]
                current = self._daily_domain_costs.get(domain, 0.0)
            else:
                current = self._daily_total

            utilization = current / budget.daily_limit_usd if budget.daily_limit_usd > 0 else 0

            # Update Prometheus gauge
            if COST_PROMETHEUS_AVAILABLE:
                BUDGET_UTILIZATION.labels(scope=scope).set(utilization)

            # Alert if threshold exceeded
            if utilization >= budget.alert_threshold_pct:
                self._logger.warning(
                    "budget_threshold_exceeded",
                    scope=scope,
                    current_usd=round(current, 6),
                    limit_usd=budget.daily_limit_usd,
                    utilization=round(utilization, 2),
                )
                # Emit alert to governance swarm
                self._emit_budget_alert(scope, current, budget, utilization)

    def _emit_budget_alert(
        self,
        scope: str,
        current: float,
        budget: CostBudget,
        utilization: float,
    ) -> None:
        """Emit a budget alert event to the governance swarm."""
        if not self._event_bus:
            return

        try:
            from app.agents.base import AgentEvent, EventType
            alert_event = AgentEvent(
                event_type=EventType.SECURITY_ALERT,  # Closest existing type
                source="AgentCostTracker",
                payload={
                    "alert_type": "budget_threshold",
                    "scope": scope,
                    "current_usd": round(current, 6),
                    "daily_limit_usd": budget.daily_limit_usd,
                    "utilization": round(utilization, 2),
                    "message": (
                        f"Budget alert: {scope} has used {utilization:.0%} of daily budget "
                        f"(${current:.4f} / ${budget.daily_limit_usd:.2f})"
                    ),
                },
            )
            # Fire and forget
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._event_bus.publish(alert_event))
            except RuntimeError:
                pass
        except Exception as exc:
            self._logger.debug("budget_alert_emit_failed", error=str(exc))

    # ── Query Methods ───────────────────────────────────────────────

    def get_agent_cost(self, agent_name: str, hours: int = 24) -> Dict[str, Any]:
        """Get cost breakdown for a specific agent."""
        cutoff = time.time() - hours * 3600
        records = [r for r in self._records if r.agent_name == agent_name and r.timestamp > cutoff]

        if not records:
            return {"agent_name": agent_name, "total_cost_usd": 0.0}

        total_tokens_in = sum(r.input_tokens for r in records)
        total_tokens_out = sum(r.output_tokens for r in records)
        total_cost = sum(r.cost_usd for r in records)

        # Breakdown by model
        model_costs: Dict[str, float] = defaultdict(float)
        model_tokens: Dict[str, int] = defaultdict(int)
        for r in records:
            if r.model:
                model_costs[r.model] += r.cost_usd
                model_tokens[r.model] += r.input_tokens + r.output_tokens

        return {
            "agent_name": agent_name,
            "period_hours": hours,
            "total_cost_usd": round(total_cost, 8),
            "total_input_tokens": total_tokens_in,
            "total_output_tokens": total_tokens_out,
            "total_tokens": total_tokens_in + total_tokens_out,
            "call_count": len(records),
            "cost_by_model": {k: round(v, 8) for k, v in model_costs.items()},
            "tokens_by_model": dict(model_tokens),
            "avg_cost_per_call": round(total_cost / len(records), 8) if records else 0,
            "daily_budget": self._budgets.get(f"agent:{agent_name}", CostBudget("")).daily_limit_usd,
            "daily_spend": round(self._daily_costs.get(agent_name, 0), 8),
        }

    def get_swarm_cost(self, swarm_name: str, hours: int = 24) -> Dict[str, Any]:
        """Get aggregated cost for a swarm."""
        cutoff = time.time() - hours * 3600
        agents = [name for name, s in self._agent_swarm.items() if s == swarm_name]
        records = [
            r for r in self._records
            if r.agent_name in agents and r.timestamp > cutoff
        ]

        if not records:
            return {"swarm_name": swarm_name, "total_cost_usd": 0.0}

        total_cost = sum(r.cost_usd for r in records)
        agent_costs: Dict[str, float] = defaultdict(float)
        for r in records:
            agent_costs[r.agent_name] += r.cost_usd

        return {
            "swarm_name": swarm_name,
            "period_hours": hours,
            "total_cost_usd": round(total_cost, 8),
            "agents": agents,
            "cost_by_agent": {k: round(v, 8) for k, v in agent_costs.items()},
            "call_count": len(records),
            "total_tokens": sum(r.input_tokens + r.output_tokens for r in records),
        }

    def get_domain_cost(self, domain: str, hours: int = 24) -> Dict[str, Any]:
        """Get aggregated cost for a business domain."""
        cutoff = time.time() - hours * 3600
        records = [r for r in self._records if r.domain == domain and r.timestamp > cutoff]

        if not records:
            return {"domain": domain, "total_cost_usd": 0.0}

        total_cost = sum(r.cost_usd for r in records)
        agent_costs: Dict[str, float] = defaultdict(float)
        for r in records:
            agent_costs[r.agent_name] += r.cost_usd

        return {
            "domain": domain,
            "period_hours": hours,
            "total_cost_usd": round(total_cost, 8),
            "cost_by_agent": {k: round(v, 8) for k, v in agent_costs.items()},
            "call_count": len(records),
        }

    def get_stats(self, hours: int = 24) -> Dict[str, Any]:
        """Get overall cost statistics."""
        cutoff = time.time() - hours * 3600
        records = [r for r in self._records if r.timestamp > cutoff]

        if not records:
            return {"total_cost_usd": 0.0, "period_hours": hours}

        total_cost = sum(r.cost_usd for r in records)
        total_tokens = sum(r.input_tokens + r.output_tokens for r in records)

        # By swarm
        swarm_costs: Dict[str, float] = defaultdict(float)
        for r in records:
            swarm_costs[r.swarm] += r.cost_usd

        # By domain
        domain_costs: Dict[str, float] = defaultdict(float)
        for r in records:
            domain_costs[r.domain] += r.cost_usd

        # By source (inference vs evaluation)
        source_costs: Dict[str, float] = defaultdict(float)
        for r in records:
            source_costs[r.source] += r.cost_usd

        return {
            "period_hours": hours,
            "total_cost_usd": round(total_cost, 8),
            "total_tokens": total_tokens,
            "total_calls": len(records),
            "cost_by_swarm": {k: round(v, 8) for k, v in swarm_costs.items()},
            "cost_by_domain": {k: round(v, 8) for k, v in domain_costs.items()},
            "cost_by_source": {k: round(v, 8) for k, v in source_costs.items()},
            "daily_spend": round(self._daily_total, 8),
            "budgets": {
                scope: {
                    "daily_limit": b.daily_limit_usd,
                    "utilization": round(
                        self._daily_costs.get(scope.split(":", 1)[-1], 0) / b.daily_limit_usd
                        if b.daily_limit_usd > 0 else 0, 2
                    ),
                }
                for scope, b in self._budgets.items()
            },
        }


# ════════════════════════════════════════════════════════════════════
# Singleton
# ════════════════════════════════════════════════════════════════════

_cost_tracker: Optional[AgentCostTracker] = None


def get_cost_tracker() -> AgentCostTracker:
    """Get the singleton AgentCostTracker."""
    global _cost_tracker
    if _cost_tracker is None:
        _cost_tracker = AgentCostTracker()
    return _cost_tracker
