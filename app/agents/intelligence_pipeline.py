"""
Intelligence Pipeline — Domain-Specific Long-Horizon Analysis Flows.

Four specialized pipelines for Angavu Intelligence's core use cases:
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
# Database query helpers — replace hardcoded stub data
# ════════════════════════════════════════════════════════════════════


def _get_db_session():
    """Get a database session for querying real data.

    Returns a SQLAlchemy async session or None if DB is unavailable.
    Falls back gracefully — agents return empty results rather than crashing.
    """
    try:
        from app.database import async_session
        return async_session
    except (ImportError, Exception) as exc:
        logger.debug("db_session_unavailable", error=str(exc))
        return None


async def _query_market_prices(region: str, product: Optional[str] = None) -> Dict[str, Any]:
    """Query real market price data from the database.

    Falls back to empty structure if DB is unavailable.
    """
    session_factory = _get_db_session()
    if session_factory is None:
        return {"prices": {}, "data_points": 0, "source": "no_db"}

    try:
        from sqlalchemy import select, func
        from app.models.transaction import Transaction

        async with session_factory() as session:
            query = select(
                func.avg(Transaction.amount).label("avg"),
                func.min(Transaction.amount).label("min"),
                func.max(Transaction.amount).label("max"),
                func.count(Transaction.id).label("count"),
            ).where(Transaction.region == region)
            if product:
                query = query.where(Transaction.product_name.ilike(f"%{product}%"))

            result = await session.execute(query)
            row = result.one_or_none()
            if row and row.count > 0:
                return {
                    "prices": {"avg": float(row.avg), "min": float(row.min), "max": float(row.max)},
                    "data_points": row.count,
                    "source": "database",
                }
    except Exception as exc:
        logger.warning("market_price_query_failed", error=str(exc), region=region)

    return {"prices": {}, "data_points": 0, "source": "query_failed"}


async def _query_transaction_history(worker_id: str) -> Dict[str, Any]:
    """Query real transaction history for credit scoring.

    Falls back to empty structure if DB is unavailable.
    """
    session_factory = _get_db_session()
    if session_factory is None:
        return {"months_available": 0, "transactions": [], "source": "no_db"}

    try:
        from sqlalchemy import select, func
        from app.models.transaction import Transaction

        async with session_factory() as session:
            query = select(
                func.count(Transaction.id).label("total"),
                func.avg(Transaction.amount).label("avg_amount"),
                func.min(Transaction.created_at).label("first_txn"),
                func.max(Transaction.created_at).label("last_txn"),
            ).where(Transaction.user_id == worker_id)

            result = await session.execute(query)
            row = result.one_or_none()
            if row and row.total > 0:
                return {
                    "total_transactions": row.total,
                    "avg_amount": float(row.avg_amount) if row.avg_amount else 0,
                    "first_transaction": str(row.first_txn),
                    "last_transaction": str(row.last_txn),
                    "source": "database",
                }
    except Exception as exc:
        logger.warning("transaction_history_query_failed", error=str(exc), worker_id=worker_id)

    return {"total_transactions": 0, "source": "query_failed"}


async def _query_distribution_data(product: str) -> Dict[str, Any]:
    """Query real distribution/coverage data from the database.

    Falls back to empty structure if DB is unavailable.
    """
    session_factory = _get_db_session()
    if session_factory is None:
        return {"regions": [], "source": "no_db"}

    try:
        from sqlalchemy import select, func
        from app.models.transaction import Transaction

        async with session_factory() as session:
            query = select(
                Transaction.region,
                func.count(Transaction.id).label("txn_count"),
                func.sum(Transaction.amount).label("total_volume"),
            ).group_by(Transaction.region)
            if product:
                query = query.where(Transaction.product_name.ilike(f"%{product}%"))

            result = await session.execute(query)
            rows = result.all()
            if rows:
                return {
                    "regions": [
                        {"region": r.region, "txn_count": r.txn_count, "volume": float(r.total_volume or 0)}
                        for r in rows
                    ],
                    "source": "database",
                }
    except Exception as exc:
        logger.warning("distribution_query_failed", error=str(exc), product=product)

    return {"regions": [], "source": "query_failed"}


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
            params = decision.parameters
            region = params.get("region", "Nairobi")
            data: Dict[str, Any] = {
                "action": action,
                "status": "completed",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            if "price" in action:
                # Query real market prices from DB
                db_prices = await _query_market_prices(region)
                if db_prices["data_points"] > 0:
                    data["prices"] = db_prices["prices"]
                    data["data_points"] = db_prices["data_points"]
                else:
                    # DB unavailable — report empty rather than fake data
                    data["prices"] = {"avg": None, "min": None, "max": None}
                    data["data_points"] = 0
                    data["source"] = "no_data_available"
                    logger.info("market_price_no_data", region=region, action=action)
            elif "supply" in action or "demand" in action:
                # TODO: Wire to real supply/demand data source
                # Currently no dedicated supply/demand table exists.
                # When available, query: SELECT * FROM supply_demand_index WHERE region = ?
                data["supply_demand"] = {"supply_index": None, "demand_index": None, "gap": None}
                data["source"] = "not_implemented"
                data["todo"] = "Wire to supply/demand data source when available"
            elif "trade" in action or "volume" in action:
                # Query real trade volume from DB
                db_dist = await _query_distribution_data(params.get("product", ""))
                if db_dist["regions"]:
                    total_volume = sum(r["volume"] for r in db_dist["regions"])
                    total_txns = sum(r["txn_count"] for r in db_dist["regions"])
                    data["trade_volume"] = {"total_volume": total_volume, "total_transactions": total_txns}
                else:
                    data["trade_volume"] = {"total_volume": 0, "total_transactions": 0}
                    data["source"] = "no_data_available"
            elif "competitor" in action:
                # TODO: Wire to real competitor data source
                # Currently no competitor table exists.
                # When available, query: SELECT * FROM competitor_profiles WHERE market = ?
                data["competitors"] = {"count": None, "market_share": {}}
                data["source"] = "not_implemented"
                data["todo"] = "Wire to competitor data source when available"
            else:
                data["market_overview"] = {"status": "data_driven", "volatility": "unknown"}

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
            params = decision.parameters
            worker_id = params.get("worker_id", "unknown")
            data: Dict[str, Any] = {
                "action": action,
                "status": "completed",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            if "history" in action or "transaction" in action:
                # Query real transaction history from DB
                history = await _query_transaction_history(worker_id)
                data["transaction_history"] = {
                    "total_transactions": history["total_transactions"],
                    "avg_amount": history.get("avg_amount", 0),
                    "first_transaction": history.get("first_transaction"),
                    "last_transaction": history.get("last_transaction"),
                    "source": history["source"],
                }
            elif "repay" in action:
                # TODO: Wire to repayment data when loan tracking table exists
                # Currently no dedicated repayment/loan table.
                # When available: SELECT * FROM loan_repayments WHERE worker_id = ?
                data["repayment"] = {"on_time_rate": None, "late_payments": None, "defaults": None}
                data["source"] = "not_implemented"
                data["todo"] = "Wire to loan repayment tracking when available"
            elif "behavior" in action:
                # TODO: Wire to behavioral analytics when available
                data["behavioral_score"] = {"regularity": None, "growth_trend": None, "risk_flags": []}
                data["source"] = "not_implemented"
            elif "creditworthiness" in action or "credit_score" in action:
                # TODO: Wire to Alama Score service for real credit scoring
                # Currently AlamaScoreService exists but needs integration here
                data["credit_score"] = {"score": None, "rating": "pending", "confidence": 0.0}
                data["source"] = "not_wired_to_alama_score"
                data["todo"] = "Wire to AlamaScoreService.compute_score()"
            else:
                data["credit_overview"] = {"risk_level": "unknown", "creditworthy": None}

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
            params = decision.parameters
            product = params.get("product", "")
            data: Dict[str, Any] = {
                "action": action,
                "status": "completed",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            if "mapping" in action or "coverage" in action:
                # Query real distribution coverage from DB
                dist_data = await _query_distribution_data(product)
                if dist_data["regions"]:
                    regions_covered = len(dist_data["regions"])
                    data["coverage"] = {
                        "regions_covered": regions_covered,
                        "regions_total": 47,  # Kenya has 47 counties
                        "coverage_pct": round(regions_covered / 47 * 100, 1),
                        "regions": dist_data["regions"],
                    }
                else:
                    data["coverage"] = {"regions_covered": 0, "regions_total": 47, "coverage_pct": 0.0}
                    data["source"] = "no_data_available"
            elif "logistics" in action:
                # TODO: Wire to logistics data source when available
                # Currently no dedicated logistics/warehouse table.
                data["logistics"] = {"avg_delivery_time_days": None, "cost_per_unit": None, "bottlenecks": []}
                data["source"] = "not_implemented"
                data["todo"] = "Wire to logistics tracking system when available"
            elif "demand" in action:
                # Query demand signals from transaction data
                dist_data = await _query_distribution_data(product)
                if dist_data["regions"]:
                    # Sort regions by volume to identify high-demand areas
                    sorted_regions = sorted(dist_data["regions"], key=lambda r: r["volume"], reverse=True)
                    data["demand_map"] = {
                        "high_demand": [r["region"] for r in sorted_regions[:5]],
                        "total_regions_with_data": len(sorted_regions),
                    }
                else:
                    data["demand_map"] = {"high_demand": [], "total_regions_with_data": 0}
                    data["source"] = "no_data_available"
            elif "expansion" in action:
                # TODO: Wire to expansion planning service when available
                data["expansion"] = {"priority_regions": [], "estimated_investment": None, "roi_timeline_months": None}
                data["source"] = "not_implemented"
                data["todo"] = "Wire to expansion planning service when available"
            else:
                data["distribution_overview"] = {"gaps_identified": None, "opportunities": None}

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
            params = decision.parameters
            market = params.get("market", "Kenya")
            data: Dict[str, Any] = {
                "action": action,
                "status": "completed",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            # All competitor intelligence requires external data sources
            # that don't exist yet. Return clear TODOs rather than fake data.
            if "mapping" in action:
                data["competitor_map"] = {
                    "direct_competitors": None,
                    "indirect_competitors": None,
                    "new_entrants": None,
                }
                data["source"] = "not_implemented"
                data["todo"] = "Wire to competitor profiling service or web scraping pipeline"
            elif "pricing" in action:
                data["pricing_analysis"] = {
                    "our_avg_price": None,
                    "market_avg": None,
                    "price_position": "unknown",
                }
                data["source"] = "not_implemented"
                data["todo"] = "Wire to market pricing data source"
            elif "feature" in action:
                data["feature_comparison"] = {
                    "our_features": None,
                    "leader_features": None,
                    "gap_features": [],
                }
                data["source"] = "not_implemented"
                data["todo"] = "Wire to competitor feature database"
            elif "positioning" in action:
                data["positioning"] = {
                    "our_position": None,
                    "market_leader": None,
                    "differentiator": "informal_economy_focus",
                }
                data["source"] = "not_implemented"
            elif "threat" in action:
                data["threats"] = []
                data["source"] = "not_implemented"
                data["todo"] = "Wire to threat intelligence feed"
            else:
                data["competitor_overview"] = {"total_competitors": None, "threat_level": "unknown"}
                data["source"] = "not_implemented"

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
    """Aggregates market analysis results from multiple sub-tasks."""
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
    """Aggregates credit scoring results from multiple sub-tasks."""
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
    """Aggregates distribution gap analysis results from multiple sub-tasks."""
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
