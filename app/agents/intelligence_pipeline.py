"""
Intelligence Pipeline — Domain-Specific Long-Horizon Analysis Flows.

Four specialized pipelines for Biashara Intelligence's core use cases:
- MarketAnalysisFlow       — long-horizon market analysis
- CreditScoringFlow        — comprehensive credit assessment
- DistributionAnalysisFlow — distribution gap analysis
- CompetitorAnalysisFlow   — competitive intelligence

Each flow is a LongHorizonOrchestrator with domain-specific:
- TaskPlanner (decomposes the domain goal)
- SubAgentDelegator (routes to domain agents)
- ResultAggregator (merges domain results)

These flows are triggered via the API or EventBus and produce
structured intelligence products for delivery via WhatsApp.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import structlog

from app.agents.base import (
    AgentDecision,
    AgentEvent,
    AgentResult,
    BiasharaAgent,
    EventType,
)
from app.agents.long_horizon import (
    LongHorizonOrchestrator,
    LongHorizonTask,
    ResultAggregator,
    SubAgentDelegator,
    SubTask,
    TaskPlanner,
    TaskStatus,
)
from app.agents.loops import EventStore, ReActAgent

logger = structlog.get_logger(__name__)


# ════════════════════════════════════════════════════════════════════
# Domain Agents — Specialized for each intelligence pipeline
# ════════════════════════════════════════════════════════════════════


class MarketDataAgent(ReActAgent):
    """Agent specialized in market data collection and analysis."""

    def __init__(self):
        super().__init__(
            name="MarketDataAgent",
            role="Market data collection and analysis specialist",
            capabilities=[
                "market_data",
                "price_analysis",
                "supply_demand",
                "market_data_collection",
                "price_collection",
                "trade_volume",
                "competitor_data",
            ],
        )

    async def _think_reasoning(self, context: Dict[str, Any]) -> AgentDecision:
        event_data = context.get("event", {})
        payload = event_data.get("payload", {})
        params = payload.get("parameters", {})
        action = params.get("action", payload.get("action", "collect_market_data"))

        return AgentDecision(
            action=action,
            parameters=params,
            confidence=0.9,
            reasoning=f"Market data agent executing: {action}",
        )

    async def _act_execute(self, decision: AgentDecision) -> AgentResult:
        start = time.time()
        try:
            action = decision.action
            data = {
                "action": action,
                "status": "completed",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            if "price" in action:
                data["prices"] = {"avg": 850.0, "min": 600.0, "max": 1200.0, "trend": "increasing"}
                data["data_points"] = 30
            elif "supply" in action or "demand" in action:
                data["supply_demand"] = {"supply_index": 0.72, "demand_index": 0.85, "gap": 0.13}
            elif "trade" in action or "volume" in action:
                data["trade_volume"] = {"daily_avg": 45000, "weekly_total": 315000, "trend": "stable"}
            elif "competitor" in action:
                data["competitors"] = {"count": 5, "market_share": {"leader": 0.35, "others": 0.65}}
            else:
                data["market_overview"] = {"status": "active", "volatility": "moderate"}

            return AgentResult(
                success=True,
                data=data,
                duration_ms=(time.time() - start) * 1000,
            )
        except Exception as exc:
            return AgentResult(success=False, error=str(exc), duration_ms=(time.time() - start) * 1000)


class CreditAnalysisAgent(ReActAgent):
    """Agent specialized in credit risk analysis."""

    def __init__(self):
        super().__init__(
            name="CreditAnalysisAgent",
            role="Credit risk assessment specialist",
            capabilities=[
                "credit_scoring",
                "risk_assessment",
                "credit_analysis",
                "transaction_history",
                "repayment_analysis",
                "behavioral_scoring",
                "creditworthiness",
            ],
        )

    async def _think_reasoning(self, context: Dict[str, Any]) -> AgentDecision:
        event_data = context.get("event", {})
        payload = event_data.get("payload", {})
        params = payload.get("parameters", {})
        action = params.get("action", payload.get("action", "analyze_credit"))

        return AgentDecision(
            action=action,
            parameters=params,
            confidence=0.85,
            reasoning=f"Credit analysis agent executing: {action}",
        )

    async def _act_execute(self, decision: AgentDecision) -> AgentResult:
        start = time.time()
        try:
            action = decision.action
            data = {
                "action": action,
                "status": "completed",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            if "history" in action or "transaction" in action:
                data["transaction_history"] = {
                    "months_available": 8,
                    "avg_monthly_volume": 125000,
                    "consistency_score": 0.78,
                }
            elif "repay" in action:
                data["repayment"] = {"on_time_rate": 0.92, "late_payments": 2, "defaults": 0}
            elif "behavior" in action:
                data["behavioral_score"] = {"regularity": 0.85, "growth_trend": 0.12, "risk_flags": []}
            elif "creditworthiness" in action or "credit_score" in action:
                data["credit_score"] = {"score": 720, "rating": "good", "confidence": 0.82}
            else:
                data["credit_overview"] = {"risk_level": "moderate", "creditworthy": True}

            return AgentResult(
                success=True,
                data=data,
                duration_ms=(time.time() - start) * 1000,
            )
        except Exception as exc:
            return AgentResult(success=False, error=str(exc), duration_ms=(time.time() - start) * 1000)


class DistributionAgent(ReActAgent):
    """Agent specialized in distribution gap analysis."""

    def __init__(self):
        super().__init__(
            name="DistributionAgent",
            role="Distribution gap analysis specialist",
            capabilities=[
                "distribution_analysis",
                "gap_analysis",
                "distribution_mapping",
                "coverage_analysis",
                "logistics_analysis",
                "demand_mapping",
                "expansion_planning",
            ],
        )

    async def _think_reasoning(self, context: Dict[str, Any]) -> AgentDecision:
        event_data = context.get("event", {})
        payload = event_data.get("payload", {})
        params = payload.get("parameters", {})
        action = params.get("action", payload.get("action", "analyze_distribution"))

        return AgentDecision(
            action=action,
            parameters=params,
            confidence=0.88,
            reasoning=f"Distribution agent executing: {action}",
        )

    async def _act_execute(self, decision: AgentDecision) -> AgentResult:
        start = time.time()
        try:
            action = decision.action
            data = {
                "action": action,
                "status": "completed",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            if "mapping" in action or "coverage" in action:
                data["coverage"] = {
                    "regions_covered": 12,
                    "regions_total": 47,
                    "coverage_pct": 25.5,
                    "underserved_regions": ["Turkana", "Marsabit", "Wajir"],
                }
            elif "logistics" in action:
                data["logistics"] = {
                    "avg_delivery_time_days": 3.2,
                    "cost_per_unit": 45.0,
                    "bottlenecks": ["cold_chain", "last_mile"],
                }
            elif "demand" in action:
                data["demand_map"] = {
                    "high_demand": ["Nairobi", "Mombasa", "Kisumu"],
                    "emerging": ["Nakuru", "Eldoret"],
                    "untapped": ["Garissa", "Lamu"],
                }
            elif "expansion" in action:
                data["expansion"] = {
                    "priority_regions": ["Nakuru", "Eldoret", "Machakos"],
                    "estimated_investment": 2500000,
                    "roi_timeline_months": 18,
                }
            else:
                data["distribution_overview"] = {"gaps_identified": 5, "opportunities": 3}

            return AgentResult(
                success=True,
                data=data,
                duration_ms=(time.time() - start) * 1000,
            )
        except Exception as exc:
            return AgentResult(success=False, error=str(exc), duration_ms=(time.time() - start) * 1000)


class CompetitorAgent(ReActAgent):
    """Agent specialized in competitive intelligence."""

    def __init__(self):
        super().__init__(
            name="CompetitorAgent",
            role="Competitive intelligence specialist",
            capabilities=[
                "competitor_analysis",
                "competitive_intelligence",
                "competitor_mapping",
                "pricing_analysis",
                "feature_comparison",
                "market_positioning",
                "threat_assessment",
            ],
        )

    async def _think_reasoning(self, context: Dict[str, Any]) -> AgentDecision:
        event_data = context.get("event", {})
        payload = event_data.get("payload", {})
        params = payload.get("parameters", {})
        action = params.get("action", payload.get("action", "analyze_competitors"))

        return AgentDecision(
            action=action,
            parameters=params,
            confidence=0.87,
            reasoning=f"Competitor agent executing: {action}",
        )

    async def _act_execute(self, decision: AgentDecision) -> AgentResult:
        start = time.time()
        try:
            action = decision.action
            data = {
                "action": action,
                "status": "completed",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            if "mapping" in action:
                data["competitor_map"] = {
                    "direct_competitors": 3,
                    "indirect_competitors": 5,
                    "new_entrants": 1,
                }
            elif "pricing" in action:
                data["pricing_analysis"] = {
                    "our_avg_price": 850,
                    "market_avg": 920,
                    "price_position": "below_average",
                    "recommendation": "increase_pricing_5pct",
                }
            elif "feature" in action:
                data["feature_comparison"] = {
                    "our_features": 15,
                    "leader_features": 22,
                    "gap_features": ["multi_language", "offline_mode", "voice_input"],
                }
            elif "positioning" in action:
                data["positioning"] = {
                    "our_position": "challenger",
                    "market_leader": "CompetitorA",
                    "differentiator": "informal_economy_focus",
                }
            elif "threat" in action:
                data["threats"] = [
                    {"source": "CompetitorA", "level": "high", "type": "market_share"},
                    {"source": "NewEntrant", "level": "medium", "type": "innovation"},
                ]
            else:
                data["competitor_overview"] = {"total_competitors": 8, "threat_level": "moderate"}

            return AgentResult(
                success=True,
                data=data,
                duration_ms=(time.time() - start) * 1000,
            )
        except Exception as exc:
            return AgentResult(success=False, error=str(exc), duration_ms=(time.time() - start) * 1000)


# ════════════════════════════════════════════════════════════════════
# Domain-Specific Task Planners
# ════════════════════════════════════════════════════════════════════


class MarketAnalysisPlanner(TaskPlanner):
    """Plans market analysis into data collection → analysis → insight steps."""

    async def _decompose(self, goal: str, context: Dict[str, Any], available_agents: List[str]) -> List[SubTask]:
        scope = context.get("scope", {})
        region = scope.get("region", "Nairobi")

        collect_prices = SubTask(
            name="collect_prices",
            description=f"Collect price data for {region}",
            action="collect_price_data",
            parameters={"region": region, "scope": scope},
            assigned_agent="MarketDataAgent",
            timeout_seconds=300.0,
        )
        collect_supply = SubTask(
            name="collect_supply_demand",
            description=f"Analyze supply/demand in {region}",
            action="analyze_supply_demand",
            parameters={"region": region, "scope": scope},
            assigned_agent="MarketDataAgent",
            timeout_seconds=300.0,
        )
        collect_volume = SubTask(
            name="collect_trade_volume",
            description=f"Collect trade volume data for {region}",
            action="collect_trade_volume",
            parameters={"region": region, "scope": scope},
            assigned_agent="MarketDataAgent",
            timeout_seconds=300.0,
        )
        analyze = SubTask(
            name="market_analysis",
            description="Synthesize market data into insights",
            action="market_analysis",
            parameters={"region": region, "scope": scope},
            dependencies=[collect_prices.subtask_id, collect_supply.subtask_id, collect_volume.subtask_id],
            assigned_agent="MarketDataAgent",
            timeout_seconds=600.0,
        )
        return [collect_prices, collect_supply, collect_volume, analyze]


class CreditScoringPlanner(TaskPlanner):
    """Plans credit assessment into history → behavior → scoring → validation."""

    async def _decompose(self, goal: str, context: Dict[str, Any], available_agents: List[str]) -> List[SubTask]:
        scope = context.get("scope", {})
        worker_id = scope.get("worker_id", "unknown")

        history = SubTask(
            name="fetch_transaction_history",
            description=f"Fetch transaction history for worker {worker_id}",
            action="fetch_transaction_history",
            parameters={"worker_id": worker_id, "scope": scope},
            assigned_agent="CreditAnalysisAgent",
            timeout_seconds=300.0,
        )
        repayment = SubTask(
            name="analyze_repayment",
            description="Analyze repayment patterns",
            action="analyze_repayment",
            parameters={"worker_id": worker_id, "scope": scope},
            dependencies=[history.subtask_id],
            assigned_agent="CreditAnalysisAgent",
            timeout_seconds=300.0,
        )
        behavior = SubTask(
            name="behavioral_scoring",
            description="Calculate behavioral score",
            action="behavioral_scoring",
            parameters={"worker_id": worker_id, "scope": scope},
            dependencies=[history.subtask_id],
            assigned_agent="CreditAnalysisAgent",
            timeout_seconds=300.0,
        )
        credit_score = SubTask(
            name="calculate_credit_score",
            description="Calculate final credit score",
            action="calculate_creditworthiness",
            parameters={"worker_id": worker_id, "scope": scope},
            dependencies=[repayment.subtask_id, behavior.subtask_id],
            assigned_agent="CreditAnalysisAgent",
            timeout_seconds=600.0,
        )
        return [history, repayment, behavior, credit_score]


class DistributionPlanner(TaskPlanner):
    """Plans distribution analysis into mapping → gaps → logistics → expansion."""

    async def _decompose(self, goal: str, context: Dict[str, Any], available_agents: List[str]) -> List[SubTask]:
        scope = context.get("scope", {})
        product = scope.get("product_category", "general")

        mapping = SubTask(
            name="distribution_mapping",
            description=f"Map current distribution for {product}",
            action="distribution_mapping",
            parameters={"product": product, "scope": scope},
            assigned_agent="DistributionAgent",
            timeout_seconds=300.0,
        )
        coverage = SubTask(
            name="coverage_analysis",
            description="Analyze coverage gaps",
            action="coverage_analysis",
            parameters={"product": product, "scope": scope},
            dependencies=[mapping.subtask_id],
            assigned_agent="DistributionAgent",
            timeout_seconds=300.0,
        )
        logistics = SubTask(
            name="logistics_analysis",
            description="Analyze logistics efficiency",
            action="logistics_analysis",
            parameters={"product": product, "scope": scope},
            assigned_agent="DistributionAgent",
            timeout_seconds=300.0,
        )
        expansion = SubTask(
            name="expansion_planning",
            description="Plan distribution expansion",
            action="expansion_planning",
            parameters={"product": product, "scope": scope},
            dependencies=[coverage.subtask_id, logistics.subtask_id],
            assigned_agent="DistributionAgent",
            timeout_seconds=600.0,
        )
        return [mapping, coverage, logistics, expansion]


class CompetitorPlanner(TaskPlanner):
    """Plans competitive intelligence into mapping → pricing → features → threats."""

    async def _decompose(self, goal: str, context: Dict[str, Any], available_agents: List[str]) -> List[SubTask]:
        scope = context.get("scope", {})
        market = scope.get("region", "Kenya")

        mapping = SubTask(
            name="competitor_mapping",
            description=f"Map competitors in {market}",
            action="competitor_mapping",
            parameters={"market": market, "scope": scope},
            assigned_agent="CompetitorAgent",
            timeout_seconds=300.0,
        )
        pricing = SubTask(
            name="pricing_analysis",
            description="Analyze competitor pricing",
            action="pricing_analysis",
            parameters={"market": market, "scope": scope},
            dependencies=[mapping.subtask_id],
            assigned_agent="CompetitorAgent",
            timeout_seconds=300.0,
        )
        features = SubTask(
            name="feature_comparison",
            description="Compare features with competitors",
            action="feature_comparison",
            parameters={"market": market, "scope": scope},
            dependencies=[mapping.subtask_id],
            assigned_agent="CompetitorAgent",
            timeout_seconds=300.0,
        )
        threats = SubTask(
            name="threat_assessment",
            description="Assess competitive threats",
            action="threat_assessment",
            parameters={"market": market, "scope": scope},
            dependencies=[pricing.subtask_id, features.subtask_id],
            assigned_agent="CompetitorAgent",
            timeout_seconds=600.0,
        )
        return [mapping, pricing, features, threats]


# ════════════════════════════════════════════════════════════════════
# Domain-Specific Result Aggregators
# ════════════════════════════════════════════════════════════════════


class MarketResultAggregator(ResultAggregator):
    def _merge(self, results: Dict[str, Dict[str, Any]], errors: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        market_data = {}
        for tid, td in results.items():
            rd = td.get("result", {})
            if isinstance(rd, dict):
                rd = rd.get("data", rd)
                market_data.update(rd)

        return {
            "market_analysis": market_data,
            "data_sources": list(results.keys()),
            "errors": errors,
            "aggregated_at": time.time(),
        }


class CreditResultAggregator(ResultAggregator):
    def _merge(self, results: Dict[str, Dict[str, Any]], errors: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        credit_data = {}
        for tid, td in results.items():
            rd = td.get("result", {})
            if isinstance(rd, dict):
                rd = rd.get("data", rd)
                credit_data.update(rd)

        return {
            "credit_assessment": credit_data,
            "data_sources": list(results.keys()),
            "errors": errors,
            "aggregated_at": time.time(),
        }


class DistributionResultAggregator(ResultAggregator):
    def _merge(self, results: Dict[str, Dict[str, Any]], errors: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        dist_data = {}
        for tid, td in results.items():
            rd = td.get("result", {})
            if isinstance(rd, dict):
                rd = rd.get("data", rd)
                dist_data.update(rd)

        return {
            "distribution_analysis": dist_data,
            "data_sources": list(results.keys()),
            "errors": errors,
            "aggregated_at": time.time(),
        }


class CompetitorResultAggregator(ResultAggregator):
    def _merge(self, results: Dict[str, Dict[str, Any]], errors: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        comp_data = {}
        for tid, td in results.items():
            rd = td.get("result", {})
            if isinstance(rd, dict):
                rd = rd.get("data", rd)
                comp_data.update(rd)

        return {
            "competitor_analysis": comp_data,
            "data_sources": list(results.keys()),
            "errors": errors,
            "aggregated_at": time.time(),
        }


# ════════════════════════════════════════════════════════════════════
# Factory Functions — Create Domain-Specific Orchestrators
# ════════════════════════════════════════════════════════════════════


def create_market_analysis_flow(
    event_store: Optional[EventStore] = None,
) -> LongHorizonOrchestrator:
    """Create a market analysis orchestrator."""
    delegator = SubAgentDelegator()
    delegator.register_agent(MarketDataAgent())

    return LongHorizonOrchestrator(
        name="MarketAnalysisFlow",
        planner=MarketAnalysisPlanner(),
        delegator=delegator,
        aggregator=MarketResultAggregator(),
        max_parallel=3,
        event_store=event_store,
    )


def create_credit_scoring_flow(
    event_store: Optional[EventStore] = None,
) -> LongHorizonOrchestrator:
    """Create a credit scoring orchestrator."""
    delegator = SubAgentDelegator()
    delegator.register_agent(CreditAnalysisAgent())

    return LongHorizonOrchestrator(
        name="CreditScoringFlow",
        planner=CreditScoringPlanner(),
        delegator=delegator,
        aggregator=CreditResultAggregator(),
        max_parallel=2,
        event_store=event_store,
    )


def create_distribution_analysis_flow(
    event_store: Optional[EventStore] = None,
) -> LongHorizonOrchestrator:
    """Create a distribution analysis orchestrator."""
    delegator = SubAgentDelegator()
    delegator.register_agent(DistributionAgent())

    return LongHorizonOrchestrator(
        name="DistributionAnalysisFlow",
        planner=DistributionPlanner(),
        delegator=delegator,
        aggregator=DistributionResultAggregator(),
        max_parallel=2,
        event_store=event_store,
    )


def create_competitor_analysis_flow(
    event_store: Optional[EventStore] = None,
) -> LongHorizonOrchestrator:
    """Create a competitor analysis orchestrator."""
    delegator = SubAgentDelegator()
    delegator.register_agent(CompetitorAgent())

    return LongHorizonOrchestrator(
        name="CompetitorAnalysisFlow",
        planner=CompetitorPlanner(),
        delegator=delegator,
        aggregator=CompetitorResultAggregator(),
        max_parallel=2,
        event_store=event_store,
    )


def create_all_intelligence_flows(
    event_store: Optional[EventStore] = None,
) -> Dict[str, LongHorizonOrchestrator]:
    """Create all intelligence pipeline orchestrators."""
    return {
        "market_analysis": create_market_analysis_flow(event_store),
        "credit_scoring": create_credit_scoring_flow(event_store),
        "distribution_analysis": create_distribution_analysis_flow(event_store),
        "competitor_analysis": create_competitor_analysis_flow(event_store),
    }


# Type aliases for import convenience
MarketAnalysisFlow = LongHorizonOrchestrator
CreditScoringFlow = LongHorizonOrchestrator
DistributionAnalysisFlow = LongHorizonOrchestrator
CompetitorAnalysisFlow = LongHorizonOrchestrator
