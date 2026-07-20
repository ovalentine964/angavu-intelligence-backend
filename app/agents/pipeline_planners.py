"""
Intelligence Pipeline — Task Planners & Result Aggregators.

Domain-specific TaskPlanner and ResultAggregator implementations
for the four intelligence pipeline flows.
"""

from __future__ import annotations

import time
from typing import Any

from app.agents.long_horizon import ResultAggregator, SubTask, TaskPlanner


# ════════════════════════════════════════════════════════════════════
# Domain-Specific Task Planners
# ════════════════════════════════════════════════════════════════════


class MarketAnalysisPlanner(TaskPlanner):
    """Plans market analysis into data collection → analysis → insight steps."""

    async def _decompose(self, goal: str, context: dict[str, Any], available_agents: list[str]) -> list[SubTask]:
        scope = context.get("scope", {})
        region = scope.get("region", "Nairobi")
        collect_prices = SubTask(
            name="collect_prices", description=f"Collect price data for {region}",
            action="collect_price_data", parameters={"region": region, "scope": scope},
            assigned_agent="MarketDataAgent", timeout_seconds=300.0,
        )
        collect_supply = SubTask(
            name="collect_supply_demand", description=f"Analyze supply/demand in {region}",
            action="analyze_supply_demand", parameters={"region": region, "scope": scope},
            assigned_agent="MarketDataAgent", timeout_seconds=300.0,
        )
        collect_volume = SubTask(
            name="collect_trade_volume", description=f"Collect trade volume data for {region}",
            action="collect_trade_volume", parameters={"region": region, "scope": scope},
            assigned_agent="MarketDataAgent", timeout_seconds=300.0,
        )
        analyze = SubTask(
            name="market_analysis", description="Synthesize market data into insights",
            action="market_analysis", parameters={"region": region, "scope": scope},
            dependencies=[collect_prices.subtask_id, collect_supply.subtask_id, collect_volume.subtask_id],
            assigned_agent="MarketDataAgent", timeout_seconds=600.0,
        )
        return [collect_prices, collect_supply, collect_volume, analyze]


class CreditScoringPlanner(TaskPlanner):
    """Plans credit assessment into history → behavior → scoring → validation."""

    async def _decompose(self, goal: str, context: dict[str, Any], available_agents: list[str]) -> list[SubTask]:
        scope = context.get("scope", {})
        worker_id = scope.get("worker_id", "unknown")
        history = SubTask(
            name="fetch_transaction_history",
            description=f"Fetch transaction history for worker {worker_id}",
            action="fetch_transaction_history", parameters={"worker_id": worker_id, "scope": scope},
            assigned_agent="CreditAnalysisAgent", timeout_seconds=300.0,
        )
        repayment = SubTask(
            name="analyze_repayment", description="Analyze repayment patterns",
            action="analyze_repayment", parameters={"worker_id": worker_id, "scope": scope},
            dependencies=[history.subtask_id], assigned_agent="CreditAnalysisAgent", timeout_seconds=300.0,
        )
        behavior = SubTask(
            name="behavioral_scoring", description="Calculate behavioral score",
            action="behavioral_scoring", parameters={"worker_id": worker_id, "scope": scope},
            dependencies=[history.subtask_id], assigned_agent="CreditAnalysisAgent", timeout_seconds=300.0,
        )
        credit_score = SubTask(
            name="calculate_credit_score", description="Calculate final credit score",
            action="calculate_creditworthiness", parameters={"worker_id": worker_id, "scope": scope},
            dependencies=[repayment.subtask_id, behavior.subtask_id],
            assigned_agent="CreditAnalysisAgent", timeout_seconds=600.0,
        )
        return [history, repayment, behavior, credit_score]


class DistributionPlanner(TaskPlanner):
    """Plans distribution analysis into mapping → gaps → logistics → expansion."""

    async def _decompose(self, goal: str, context: dict[str, Any], available_agents: list[str]) -> list[SubTask]:
        scope = context.get("scope", {})
        product = scope.get("product_category", "general")
        mapping = SubTask(
            name="distribution_mapping", description=f"Map current distribution for {product}",
            action="distribution_mapping", parameters={"product": product, "scope": scope},
            assigned_agent="DistributionAgent", timeout_seconds=300.0,
        )
        coverage = SubTask(
            name="coverage_analysis", description="Analyze coverage gaps",
            action="coverage_analysis", parameters={"product": product, "scope": scope},
            dependencies=[mapping.subtask_id], assigned_agent="DistributionAgent", timeout_seconds=300.0,
        )
        logistics = SubTask(
            name="logistics_analysis", description="Analyze logistics efficiency",
            action="logistics_analysis", parameters={"product": product, "scope": scope},
            assigned_agent="DistributionAgent", timeout_seconds=300.0,
        )
        expansion = SubTask(
            name="expansion_planning", description="Plan distribution expansion",
            action="expansion_planning", parameters={"product": product, "scope": scope},
            dependencies=[coverage.subtask_id, logistics.subtask_id],
            assigned_agent="DistributionAgent", timeout_seconds=600.0,
        )
        return [mapping, coverage, logistics, expansion]


class CompetitorPlanner(TaskPlanner):
    """Plans competitive intelligence into mapping → pricing → features → threats."""

    async def _decompose(self, goal: str, context: dict[str, Any], available_agents: list[str]) -> list[SubTask]:
        scope = context.get("scope", {})
        market = scope.get("region", "Kenya")
        mapping = SubTask(
            name="competitor_mapping", description=f"Map competitors in {market}",
            action="competitor_mapping", parameters={"market": market, "scope": scope},
            assigned_agent="CompetitorAgent", timeout_seconds=300.0,
        )
        pricing = SubTask(
            name="pricing_analysis", description="Analyze competitor pricing",
            action="pricing_analysis", parameters={"market": market, "scope": scope},
            dependencies=[mapping.subtask_id], assigned_agent="CompetitorAgent", timeout_seconds=300.0,
        )
        features = SubTask(
            name="feature_comparison", description="Compare features with competitors",
            action="feature_comparison", parameters={"market": market, "scope": scope},
            dependencies=[mapping.subtask_id], assigned_agent="CompetitorAgent", timeout_seconds=300.0,
        )
        threats = SubTask(
            name="threat_assessment", description="Assess competitive threats",
            action="threat_assessment", parameters={"market": market, "scope": scope},
            dependencies=[pricing.subtask_id, features.subtask_id],
            assigned_agent="CompetitorAgent", timeout_seconds=600.0,
        )
        return [mapping, pricing, features, threats]


# ════════════════════════════════════════════════════════════════════
# Domain-Specific Result Aggregators
# ════════════════════════════════════════════════════════════════════


def _merge_results(results: dict[str, dict[str, Any]], errors: dict[str, dict[str, Any]], key: str) -> dict[str, Any]:
    """Common merge logic for all result aggregators."""
    merged = {}
    for tid, td in results.items():
        rd = td.get("result", {})
        if isinstance(rd, dict):
            rd = rd.get("data", rd)
            merged.update(rd)
    return {key: merged, "data_sources": list(results.keys()), "errors": errors, "aggregated_at": time.time()}


class MarketResultAggregator(ResultAggregator):
    """Aggregates market analysis results from multiple sub-tasks."""
    def _merge(self, results: dict[str, dict[str, Any]], errors: dict[str, dict[str, Any]]) -> dict[str, Any]:
        return _merge_results(results, errors, "market_analysis")


class CreditResultAggregator(ResultAggregator):
    """Aggregates credit scoring results from multiple sub-tasks."""
    def _merge(self, results: dict[str, dict[str, Any]], errors: dict[str, dict[str, Any]]) -> dict[str, Any]:
        return _merge_results(results, errors, "credit_assessment")


class DistributionResultAggregator(ResultAggregator):
    """Aggregates distribution gap analysis results from multiple sub-tasks."""
    def _merge(self, results: dict[str, dict[str, Any]], errors: dict[str, dict[str, Any]]) -> dict[str, Any]:
        return _merge_results(results, errors, "distribution_analysis")


class CompetitorResultAggregator(ResultAggregator):
    """Aggregates competitive intelligence results from multiple sub-tasks."""
    def _merge(self, results: dict[str, dict[str, Any]], errors: dict[str, dict[str, Any]]) -> dict[str, Any]:
        return _merge_results(results, errors, "competitor_analysis")
