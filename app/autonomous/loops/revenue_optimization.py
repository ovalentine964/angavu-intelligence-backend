"""
Revenue Optimization Loop — Self-Improving Pricing & Revenue Strategy.

Implements the Reflexion pattern for revenue optimization:
    1. Track revenue metrics (MRR, ARPU, churn, conversion)
    2. Identify optimization opportunities
    3. Test pricing strategies (A/B framework)
    4. Auto-adjust based on results
    5. Track improvement over time

Architecture:
    ┌──────────────┐
    │   Revenue     │ (MRR, ARPU, churn, conversion)
    │   Metrics     │
    └──────┬───────┘
           ▼
    ┌──────────────┐
    │  Opportunity  │ (identify gaps, benchmarks)
    │  Analysis     │
    └──────┬───────┘
           ▼
    ┌──────────────┐     ┌──────────────┐
    │  Strategy     │────▶│   Test &     │
    │  Generation   │     │   Measure    │
    └──────────────┘     └──────┬───────┘
                                ▼
                         ┌──────────────┐
                         │  Auto-Adjust │
                         │  & Track     │
                         └──────────────┘
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog

from app.autonomous.learning import LearningSystem, MetricType
from app.autonomous.reflexion import (
    ReflexionResult,
    ReflexionStatus,
    create_reflexion_engine,
)

logger = structlog.get_logger(__name__)


# ════════════════════════════════════════════════════════════════════
# Data Types
# ════════════════════════════════════════════════════════════════════


class PricingStrategy(str, Enum):
    """Pricing strategy types."""
    FLAT_MONTHLY = "flat_monthly"
    TIERED = "tiered"
    USAGE_BASED = "usage_based"
    FREEMIUM = "freemium"
    VALUE_BASED = "value_based"
    BUNDLE = "bundle"


class OptimizationGoal(str, Enum):
    """Revenue optimization goals."""
    INCREASE_MRR = "increase_mrr"
    REDUCE_CHURN = "reduce_churn"
    INCREASE_ARPU = "increase_arpu"
    INCREASE_CONVERSION = "increase_conversion"
    IMPROVE_LTV = "improve_ltv"


@dataclass
class RevenueMetrics:
    """Current revenue metrics snapshot."""
    timestamp: float = field(default_factory=time.time)
    mrr: float = 0.0              # Monthly Recurring Revenue
    arr: float = 0.0              # Annual Recurring Revenue
    arpu: float = 0.0             # Average Revenue Per User
    active_customers: int = 0
    new_customers: int = 0
    churned_customers: int = 0
    churn_rate: float = 0.0       # Monthly churn rate
    conversion_rate: float = 0.0  # Trial-to-paid conversion
    ltv: float = 0.0              # Customer Lifetime Value
    cac: float = 0.0              # Customer Acquisition Cost

    @property
    def ltv_cac_ratio(self) -> float:
        """LTV:CAC ratio — healthy if > 3."""
        if self.cac == 0:
            return 0.0
        return self.ltv / self.cac

    def to_dict(self) -> dict[str, Any]:
        return {
            "mrr": self.mrr,
            "arr": self.arr,
            "arpu": self.arpu,
            "active_customers": self.active_customers,
            "new_customers": self.new_customers,
            "churned_customers": self.churned_customers,
            "churn_rate": self.churn_rate,
            "conversion_rate": self.conversion_rate,
            "ltv": self.ltv,
            "cac": self.cac,
            "ltv_cac_ratio": self.ltv_cac_ratio,
        }


@dataclass
class PricingTier:
    """A pricing tier definition."""
    name: str = ""
    price: float = 0.0
    features: list[str] = field(default_factory=list)
    target_segment: str = ""
    max_customers: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "price": self.price,
            "features": self.features,
            "target_segment": self.target_segment,
        }


@dataclass
class OptimizationOpportunity:
    """An identified revenue optimization opportunity."""
    opportunity_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    goal: OptimizationGoal = OptimizationGoal.INCREASE_MRR
    description: str = ""
    current_value: float = 0.0
    target_value: float = 0.0
    estimated_impact: float = 0.0  # Estimated revenue impact
    confidence: float = 0.0
    strategy: PricingStrategy | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "opportunity_id": self.opportunity_id,
            "goal": self.goal.value,
            "description": self.description,
            "current_value": self.current_value,
            "target_value": self.target_value,
            "estimated_impact": self.estimated_impact,
            "confidence": self.confidence,
            "strategy": self.strategy.value if self.strategy else None,
        }


@dataclass
class ABTestConfig:
    """Configuration for a pricing A/B test."""
    test_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str = ""
    variant_a: dict[str, Any] = field(default_factory=dict)  # Control
    variant_b: dict[str, Any] = field(default_factory=dict)  # Treatment
    metric: str = "conversion_rate"  # Primary metric to measure
    traffic_split: float = 0.5       # Fraction of traffic for variant B
    min_sample_size: int = 100
    started_at: float = field(default_factory=time.time)
    ended_at: float | None = None
    winner: str | None = None  # "a" or "b"

    def to_dict(self) -> dict[str, Any]:
        return {
            "test_id": self.test_id,
            "name": self.name,
            "variant_a": self.variant_a,
            "variant_b": self.variant_b,
            "metric": self.metric,
            "traffic_split": self.traffic_split,
            "winner": self.winner,
        }


@dataclass
class OptimizationResult:
    """Result of a revenue optimization cycle."""
    cycle_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    metrics: RevenueMetrics | None = None
    opportunities: list[OptimizationOpportunity] = field(default_factory=list)
    strategies_applied: list[dict[str, Any]] = field(default_factory=list)
    estimated_impact: float = 0.0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "metrics": self.metrics.to_dict() if self.metrics else None,
            "opportunities_count": len(self.opportunities),
            "opportunities": [o.to_dict() for o in self.opportunities],
            "strategies_applied": self.strategies_applied,
            "estimated_impact": self.estimated_impact,
        }


# ════════════════════════════════════════════════════════════════════
# Revenue Analyzer
# ════════════════════════════════════════════════════════════════════


class RevenueAnalyzer:
    """
    Analyzes revenue metrics and identifies optimization opportunities.

    Compares current metrics against benchmarks and historical data
    to find the highest-impact improvement areas.
    """

    # Industry benchmarks for SaaS (African market adjusted)
    BENCHMARKS = {
        "churn_rate_monthly": 0.05,       # 5% monthly churn
        "conversion_rate": 0.15,           # 15% trial-to-paid
        "ltv_cac_ratio": 3.0,             # 3:1 LTV:CAC
        "arpu_monthly": 50.0,             # $50/month target
        "net_revenue_retention": 1.10,     # 110% NRR
    }

    def analyze(
        self,
        metrics: RevenueMetrics,
        historical: list[RevenueMetrics] | None = None,
        reflexion_context: dict[str, Any] | None = None,
    ) -> list[OptimizationOpportunity]:
        """
        Analyze metrics and identify optimization opportunities.

        Returns opportunities sorted by estimated impact.
        """
        opportunities: list[OptimizationOpportunity] = []

        # 1. Churn analysis
        if metrics.churn_rate > self.BENCHMARKS["churn_rate_monthly"]:
            gap = metrics.churn_rate - self.BENCHMARKS["churn_rate_monthly"]
            revenue_at_risk = metrics.mrr * gap * 12  # Annualized
            opportunities.append(OptimizationOpportunity(
                goal=OptimizationGoal.REDUCE_CHURN,
                description=(
                    f"Churn rate ({metrics.churn_rate:.1%}) exceeds benchmark "
                    f"({self.BENCHMARKS['churn_rate_monthly']:.1%}). "
                    f"Revenue at risk: ${revenue_at_risk:.0f}/year"
                ),
                current_value=metrics.churn_rate,
                target_value=self.BENCHMARKS["churn_rate_monthly"],
                estimated_impact=revenue_at_risk,
                confidence=0.85,
                strategy=PricingStrategy.VALUE_BASED,
            ))

        # 2. Conversion analysis
        if metrics.conversion_rate < self.BENCHMARKS["conversion_rate"]:
            gap = self.BENCHMARKS["conversion_rate"] - metrics.conversion_rate
            potential_new_mrr = metrics.active_customers * gap * metrics.arpu
            opportunities.append(OptimizationOpportunity(
                goal=OptimizationGoal.INCREASE_CONVERSION,
                description=(
                    f"Conversion rate ({metrics.conversion_rate:.1%}) below benchmark "
                    f"({self.BENCHMARKS['conversion_rate']:.1%}). "
                    f"Potential new MRR: ${potential_new_mrr:.0f}"
                ),
                current_value=metrics.conversion_rate,
                target_value=self.BENCHMARKS["conversion_rate"],
                estimated_impact=potential_new_mrr,
                confidence=0.75,
                strategy=PricingStrategy.FREEMIUM,
            ))

        # 3. ARPU analysis
        if metrics.arpu < self.BENCHMARKS["arpu_monthly"]:
            gap = self.BENCHMARKS["arpu_monthly"] - metrics.arpu
            potential_uplift = gap * metrics.active_customers
            opportunities.append(OptimizationOpportunity(
                goal=OptimizationGoal.INCREASE_ARPU,
                description=(
                    f"ARPU (${metrics.arpu:.0f}) below benchmark "
                    f"(${self.BENCHMARKS['arpu_monthly']:.0f}). "
                    f"Potential uplift: ${potential_uplift:.0f}/month"
                ),
                current_value=metrics.arpu,
                target_value=self.BENCHMARKS["arpu_monthly"],
                estimated_impact=potential_uplift,
                confidence=0.70,
                strategy=PricingStrategy.TIERED,
            ))

        # 4. LTV:CAC analysis
        if metrics.ltv_cac_ratio < self.BENCHMARKS["ltv_cac_ratio"] and metrics.ltv_cac_ratio > 0:
            opportunities.append(OptimizationOpportunity(
                goal=OptimizationGoal.IMPROVE_LTV,
                description=(
                    f"LTV:CAC ratio ({metrics.ltv_cac_ratio:.1f}) below benchmark "
                    f"({self.BENCHMARKS['ltv_cac_ratio']:.1f}). "
                    f"Increase retention or reduce acquisition cost."
                ),
                current_value=metrics.ltv_cac_ratio,
                target_value=self.BENCHMARKS["ltv_cac_ratio"],
                estimated_impact=metrics.mrr * 0.2,  # 20% MRR improvement estimate
                confidence=0.65,
                strategy=PricingStrategy.VALUE_BASED,
            ))

        # 5. MRR growth opportunity (if historical data available)
        if historical and len(historical) >= 2:
            prev_mrr = historical[-2].mrr
            if prev_mrr > 0:
                growth_rate = (metrics.mrr - prev_mrr) / prev_mrr
                if growth_rate < 0.05:  # Less than 5% MoM growth
                    opportunities.append(OptimizationOpportunity(
                        goal=OptimizationGoal.INCREASE_MRR,
                        description=(
                            f"MRR growth rate ({growth_rate:.1%}) is below target (5%). "
                            f"Consider pricing strategy refresh."
                        ),
                        current_value=growth_rate,
                        target_value=0.05,
                        estimated_impact=metrics.mrr * 0.15,
                        confidence=0.60,
                        strategy=PricingStrategy.BUNDLE,
                    ))

        # Apply Reflexion context — boost opportunities that align with past feedback
        if reflexion_context:
            suggestions = reflexion_context.get("suggestions", [])
            for opp in opportunities:
                for suggestion in suggestions:
                    if opp.goal.value in suggestion.lower():
                        opp.confidence = min(1.0, opp.confidence + 0.1)

        # Sort by estimated impact
        opportunities.sort(key=lambda o: o.estimated_impact, reverse=True)
        return opportunities


# ════════════════════════════════════════════════════════════════════
# Strategy Generator
# ════════════════════════════════════════════════════════════════════


class StrategyGenerator:
    """
    Generates pricing and revenue strategies based on opportunities.

    Creates concrete, testable strategy proposals with A/B test configs.
    """

    def generate_strategies(
        self,
        opportunities: list[OptimizationOpportunity],
        current_metrics: RevenueMetrics,
    ) -> list[dict[str, Any]]:
        """
        Generate strategies for the top opportunities.

        Returns a list of strategy dicts with action items and A/B test configs.
        """
        strategies = []

        for opp in opportunities[:3]:  # Top 3 opportunities
            strategy = self._generate_for_opportunity(opp, current_metrics)
            if strategy:
                strategies.append(strategy)

        return strategies

    def _generate_for_opportunity(
        self,
        opp: OptimizationOpportunity,
        metrics: RevenueMetrics,
    ) -> dict[str, Any] | None:
        """Generate a strategy for a specific opportunity."""

        if opp.goal == OptimizationGoal.REDUCE_CHURN:
            return {
                "strategy_type": "churn_reduction",
                "opportunity_id": opp.opportunity_id,
                "actions": [
                    "Implement proactive churn prediction model",
                    "Create retention offers for at-risk customers (20% discount for 3 months)",
                    "Add in-app engagement nudges for inactive users",
                    "Launch customer success check-in program",
                ],
                "ab_test": ABTestConfig(
                    name="Retention Offer Test",
                    variant_a={"offer": None, "price": metrics.arpu},
                    variant_b={"offer": "20% discount 3 months", "price": metrics.arpu * 0.8},
                    metric="churn_rate",
                ).to_dict(),
                "estimated_impact": opp.estimated_impact,
                "timeline": "30 days",
            }

        elif opp.goal == OptimizationGoal.INCREASE_CONVERSION:
            return {
                "strategy_type": "conversion_optimization",
                "opportunity_id": opp.opportunity_id,
                "actions": [
                    "Extend trial period from 7 to 14 days",
                    "Add feature-gated prompts during trial",
                    "Implement onboarding email sequence (5 emails)",
                    "Create ROI calculator for prospects",
                ],
                "ab_test": ABTestConfig(
                    name="Trial Length Test",
                    variant_a={"trial_days": 7},
                    variant_b={"trial_days": 14},
                    metric="conversion_rate",
                ).to_dict(),
                "estimated_impact": opp.estimated_impact,
                "timeline": "45 days",
            }

        elif opp.goal == OptimizationGoal.INCREASE_ARPU:
            return {
                "strategy_type": "arpu_growth",
                "opportunity_id": opp.opportunity_id,
                "actions": [
                    "Introduce premium tier with advanced analytics",
                    "Add usage-based pricing for API calls",
                    "Create feature bundles for specific verticals",
                    "Implement upsell prompts at usage thresholds",
                ],
                "ab_test": ABTestConfig(
                    name="Tiered Pricing Test",
                    variant_a={"pricing": "flat", "price": metrics.arpu},
                    variant_b={"pricing": "tiered", "tiers": [
                        {"name": "Basic", "price": metrics.arpu * 0.7},
                        {"name": "Pro", "price": metrics.arpu * 1.2},
                        {"name": "Enterprise", "price": metrics.arpu * 2.0},
                    ]},
                    metric="arpu",
                ).to_dict(),
                "estimated_impact": opp.estimated_impact,
                "timeline": "60 days",
            }

        elif opp.goal == OptimizationGoal.INCREASE_MRR:
            return {
                "strategy_type": "mrr_growth",
                "opportunity_id": opp.opportunity_id,
                "actions": [
                    "Launch referral program (1 month free for referrer + referee)",
                    "Create industry-specific intelligence packages",
                    "Implement annual billing discount (20% off)",
                    "Partner with complementary services for cross-sell",
                ],
                "estimated_impact": opp.estimated_impact,
                "timeline": "90 days",
            }

        return None


# ════════════════════════════════════════════════════════════════════
# Revenue Optimization Executor
# ════════════════════════════════════════════════════════════════════


class RevenueOptimizationExecutor:
    """
    Executes revenue optimization analysis.

    Takes current metrics, analyzes opportunities, and generates strategies.
    """

    def __init__(self):
        self._analyzer = RevenueAnalyzer()
        self._generator = StrategyGenerator()
        self._logger = logger.bind(component="revenue_optimization_executor")

    async def execute(
        self,
        task: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute revenue optimization analysis."""
        start = time.time()

        try:
            # Parse metrics from task
            metrics_data = task.get("metrics", {})
            metrics = RevenueMetrics(
                mrr=metrics_data.get("mrr", 0),
                arr=metrics_data.get("arr", 0),
                arpu=metrics_data.get("arpu", 0),
                active_customers=metrics_data.get("active_customers", 0),
                new_customers=metrics_data.get("new_customers", 0),
                churned_customers=metrics_data.get("churned_customers", 0),
                churn_rate=metrics_data.get("churn_rate", 0),
                conversion_rate=metrics_data.get("conversion_rate", 0),
                ltv=metrics_data.get("ltv", 0),
                cac=metrics_data.get("cac", 0),
            )

            # Parse historical metrics
            historical_data = task.get("historical", [])
            historical = [RevenueMetrics(**m) for m in historical_data] if historical_data else []

            # Check for Reflexion feedback
            reflexion = task.get("_reflexion_feedback", {})

            # Analyze opportunities
            opportunities = self._analyzer.analyze(metrics, historical, reflexion)

            # Generate strategies
            strategies = self._generator.generate_strategies(opportunities, metrics)

            # Calculate total estimated impact
            total_impact = sum(o.estimated_impact for o in opportunities)

            return {
                "success": True,
                "data": {
                    "metrics": metrics.to_dict(),
                    "opportunities": [o.to_dict() for o in opportunities],
                    "strategies": strategies,
                    "total_estimated_impact": total_impact,
                    "opportunities_count": len(opportunities),
                    "strategies_count": len(strategies),
                },
                "duration_ms": (time.time() - start) * 1000,
            }

        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
                "duration_ms": (time.time() - start) * 1000,
            }


# ════════════════════════════════════════════════════════════════════
# Revenue Optimization Critic
# ════════════════════════════════════════════════════════════════════


class RevenueOptimizationCritic:
    """
    Evaluates the quality of revenue optimization analysis.

    Checks:
    - Opportunities are data-driven and specific
    - Strategies are actionable with clear timelines
    - A/B tests are properly configured
    - Impact estimates are reasonable
    """

    async def critique(
        self,
        task: dict[str, Any],
        result: dict[str, Any],
        attempt_number: int,
    ) -> dict[str, Any]:
        """Evaluate optimization analysis quality."""
        if not result.get("success", False):
            return {
                "score": 0.0,
                "issues": [f"Analysis failed: {result.get('error', 'unknown')}"],
                "suggestions": ["Verify metrics data quality", "Check analysis pipeline"],
            }

        data = result.get("data", {})
        opportunities = data.get("opportunities", [])
        strategies = data.get("strategies", [])

        issues = []
        suggestions = []
        score = 1.0

        # Check opportunities quality
        if not opportunities:
            score -= 0.3
            issues.append("No optimization opportunities identified")
            suggestions.append("Check if metrics are within benchmarks or add more data points")

        # Check for high-confidence opportunities
        high_conf = sum(1 for o in opportunities if o.get("confidence", 0) >= 0.7)
        if high_conf == 0 and opportunities:
            score -= 0.15
            issues.append("No high-confidence opportunities")
            suggestions.append("Gather more historical data to improve confidence")

        # Check strategies
        if not strategies and opportunities:
            score -= 0.2
            issues.append("Opportunities found but no strategies generated")
            suggestions.append("Ensure strategy generator covers all opportunity types")

        # Check for A/B tests
        has_ab_test = any(s.get("ab_test") for s in strategies)
        if strategies and not has_ab_test:
            score -= 0.1
            suggestions.append("Add A/B test configurations for strategies")

        # Check impact reasonableness
        total_impact = data.get("total_estimated_impact", 0)
        metrics = data.get("metrics", {})
        mrr = metrics.get("mrr", 0)
        if mrr > 0 and total_impact > mrr * 5:
            score -= 0.1
            issues.append("Impact estimates may be overly optimistic")
            suggestions.append("Calibrate impact estimates against historical improvements")

        # Penalize repeated attempts
        if attempt_number > 1:
            score -= 0.05 * (attempt_number - 1)

        return {
            "score": max(0.0, min(1.0, score)),
            "issues": issues,
            "suggestions": suggestions,
        }


# ════════════════════════════════════════════════════════════════════
# Revenue Optimization Reviser
# ════════════════════════════════════════════════════════════════════


class RevenueOptimizationReviser:
    """
    Revises revenue optimization analysis based on critique.

    Adjusts analysis parameters, adds more context, or refines strategies.
    """

    async def revise(
        self,
        task: dict[str, Any],
        critique: dict[str, Any],
        previous_attempts: list,
    ) -> dict[str, Any]:
        """Create a revised analysis task."""
        revised_task = dict(task)
        suggestions = critique.get("suggestions", [])
        plan_parts = []

        # Lower confidence thresholds if no high-confidence results
        if "No high-confidence opportunities" in str(critique.get("issues", [])):
            revised_task["_lower_confidence_threshold"] = True
            plan_parts.append("Lower confidence threshold for opportunity detection")

        # Add more benchmark data
        if "No optimization opportunities" in str(critique.get("issues", [])):
            revised_task["_expand_benchmarks"] = True
            plan_parts.append("Expand benchmark comparison range")

        # Refine strategies
        if "no strategies generated" in str(critique.get("issues", [])):
            revised_task["_force_strategy_generation"] = True
            plan_parts.append("Generate strategies for all opportunity types")

        for suggestion in suggestions[:3]:
            plan_parts.append(f"Apply: {suggestion}")

        return {
            "revised_task": revised_task,
            "plan": "; ".join(plan_parts) if plan_parts else "Refine analysis parameters",
        }


# ════════════════════════════════════════════════════════════════════
# Revenue Optimization Loop
# ════════════════════════════════════════════════════════════════════


class RevenueOptimizationLoop:
    """
    Self-improving revenue optimization loop.

    Analyzes revenue metrics, identifies opportunities, generates strategies,
    and tracks optimization impact over time using the Reflexion pattern.

    Usage:
        loop = RevenueOptimizationLoop()

        # Run optimization cycle
        result = await loop.optimize(RevenueMetrics(
            mrr=5000,
            arpu=25,
            active_customers=200,
            churn_rate=0.08,
            conversion_rate=0.10,
        ))

        # Get optimization history
        history = loop.get_optimization_history()
    """

    def __init__(
        self,
        quality_threshold: float = 0.65,
        max_attempts: int = 2,
        learning_system: LearningSystem | None = None,
        event_bus: Any = None,
    ):
        self._learning = learning_system or LearningSystem()
        self._metrics_history: list[RevenueMetrics] = []
        self._optimization_history: list[OptimizationResult] = []
        self._applied_strategies: list[dict[str, Any]] = []

        self._engine = create_reflexion_engine(
            executor=RevenueOptimizationExecutor(),
            critic=RevenueOptimizationCritic(),
            reviser=RevenueOptimizationReviser(),
            quality_threshold=quality_threshold,
            max_attempts=max_attempts,
            event_bus=event_bus,
        )
        self._event_bus = event_bus
        self._logger = logger.bind(component="revenue_optimization_loop")

    async def optimize(
        self,
        metrics: RevenueMetrics,
        historical: list[RevenueMetrics] | None = None,
    ) -> ReflexionResult:
        """
        Run a revenue optimization cycle.

        Analyzes current metrics, identifies opportunities, and generates strategies.
        Returns a ReflexionResult with optimization analysis and strategies.
        """
        self._metrics_history.append(metrics)
        if historical:
            self._metrics_history.extend(historical)

        task = {
            "metrics": metrics.to_dict(),
            "historical": [m.to_dict() for m in (historical or [])],
        }

        self._logger.info(
            "revenue_optimization_started",
            mrr=metrics.mrr,
            arpu=metrics.arpu,
            churn_rate=metrics.churn_rate,
        )

        result = await self._engine.run(
            task=task,
            task_name="revenue_optimization",
        )

        # Store optimization result
        if result.final_result and result.final_result.get("success"):
            opt_data = result.final_result.get("data", {})
            opt_result = OptimizationResult(
                metrics=metrics,
                strategies_applied=opt_data.get("strategies", []),
                estimated_impact=opt_data.get("total_estimated_impact", 0),
            )
            self._optimization_history.append(opt_result)

        # Record in learning system
        if result.status == ReflexionStatus.ACCEPTED:
            self._learning.record_success(
                agent_name="RevenueOptimizationLoop",
                task_name="optimize",
                quality_score=result.final_score,
                duration_ms=result.total_duration_ms,
            )
        else:
            self._learning.record_failure(
                agent_name="RevenueOptimizationLoop",
                task_name="optimize",
                error=f"Quality below threshold: {result.final_score:.2f}",
            )

        # Record revenue impact metric
        if result.final_result and result.final_result.get("success"):
            impact = result.final_result.get("data", {}).get("total_estimated_impact", 0)
            if metrics.mrr > 0:
                self._learning.record_metric(
                    agent_name="RevenueOptimizationLoop",
                    task_name="optimize",
                    metric_type=MetricType.REVENUE_IMPACT,
                    value=impact / metrics.mrr,  # Impact as % of MRR
                )

        return result

    def get_optimization_history(self, n: int = 10) -> list[dict[str, Any]]:
        """Get recent optimization results."""
        return [r.to_dict() for r in self._optimization_history[-n:]]

    def get_metrics_trend(self) -> dict[str, Any]:
        """Get revenue metrics trend over time."""
        if not self._metrics_history:
            return {"data_points": 0}

        mrr_values = [m.mrr for m in self._metrics_history]
        arpu_values = [m.arpu for m in self._metrics_history]
        churn_values = [m.churn_rate for m in self._metrics_history]

        return {
            "data_points": len(self._metrics_history),
            "mrr": {
                "current": mrr_values[-1],
                "min": min(mrr_values),
                "max": max(mrr_values),
                "trend": "up" if len(mrr_values) > 1 and mrr_values[-1] > mrr_values[0] else "down",
            },
            "arpu": {
                "current": arpu_values[-1],
                "min": min(arpu_values),
                "max": max(arpu_values),
            },
            "churn_rate": {
                "current": churn_values[-1],
                "min": min(churn_values),
                "max": max(churn_values),
                "trend": "improving" if len(churn_values) > 1 and churn_values[-1] < churn_values[0] else "worsening",
            },
        }

    def get_stats(self) -> dict[str, Any]:
        """Get revenue optimization loop statistics."""
        return {
            "engine_stats": self._engine.get_stats(),
            "optimization_cycles": len(self._optimization_history),
            "metrics_history_size": len(self._metrics_history),
            "applied_strategies": len(self._applied_strategies),
            "metrics_trend": self.get_metrics_trend(),
            "learning_profile": self._learning.get_profile("RevenueOptimizationLoop").to_dict(),
        }
