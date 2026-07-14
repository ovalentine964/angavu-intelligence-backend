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
    """Get a database session factory for querying real data.

    Returns a SQLAlchemy async session factory or None if DB is unavailable.
    Falls back gracefully — agents return empty results rather than crashing.
    """
    try:
        from app.db.database import async_session_factory
        return async_session_factory
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


async def _query_supply_demand(region: str, product: Optional[str] = None) -> Dict[str, Any]:
    """Derive supply/demand signals from transaction data.

    Sales transactions represent demand; purchase transactions represent supply.
    The ratio and volume differences indicate market balance.
    """
    session_factory = _get_db_session()
    if session_factory is None:
        return {"supply_index": None, "demand_index": None, "gap": None, "source": "no_db"}

    try:
        from sqlalchemy import select, func
        from app.models.transaction import Transaction

        async with session_factory() as session:
            query = select(
                Transaction.transaction_type,
                func.count(Transaction.id).label("txn_count"),
                func.sum(Transaction.amount).label("total_amount"),
                func.avg(Transaction.amount).label("avg_amount"),
            )
            if product:
                query = query.where(Transaction.item.ilike(f"%{product}%"))
            query = query.group_by(Transaction.transaction_type)

            result = await session.execute(query)
            rows = result.all()

            supply_volume = 0.0
            demand_volume = 0.0
            supply_count = 0
            demand_count = 0
            for r in rows:
                if r.transaction_type == "SALE":
                    demand_volume = float(r.total_amount or 0)
                    demand_count = r.txn_count
                elif r.transaction_type == "PURCHASE":
                    supply_volume = float(r.total_amount or 0)
                    supply_count = r.txn_count

            total = supply_volume + demand_volume
            if total > 0:
                supply_index = round(supply_volume / total * 100, 1)
                demand_index = round(demand_volume / total * 100, 1)
                gap = round(demand_index - supply_index, 1)
            else:
                supply_index = None
                demand_index = None
                gap = None

            return {
                "supply_index": supply_index,
                "demand_index": demand_index,
                "gap": gap,
                "supply_volume": supply_volume,
                "demand_volume": demand_volume,
                "supply_txn_count": supply_count,
                "demand_txn_count": demand_count,
                "source": "database" if (supply_count + demand_count) > 0 else "no_data",
            }
    except Exception as exc:
        logger.warning("supply_demand_query_failed", error=str(exc), region=region)
    return {"supply_index": None, "demand_index": None, "gap": None, "source": "query_failed"}


async def _query_competitor_density(region: str, product: Optional[str] = None) -> Dict[str, Any]:
    """Estimate competitor density from distinct sellers in the same market.

    More distinct users selling the same product = more competitive.
    """
    session_factory = _get_db_session()
    if session_factory is None:
        return {"distinct_sellers": 0, "competitor_density": "unknown", "source": "no_db"}

    try:
        from sqlalchemy import select, func, distinct
        from app.models.transaction import Transaction

        async with session_factory() as session:
            query = select(
                func.count(distinct(Transaction.user_id)).label("distinct_sellers"),
                func.count(Transaction.id).label("total_txns"),
                func.sum(Transaction.amount).label("total_volume"),
            ).where(
                Transaction.transaction_type == "SALE"
            )
            if product:
                query = query.where(Transaction.item.ilike(f"%{product}%"))

            result = await session.execute(query)
            row = result.one_or_none()

            if row and row.distinct_sellers and row.distinct_sellers > 0:
                sellers = row.distinct_sellers
                if sellers >= 50:
                    density = "very_high"
                elif sellers >= 20:
                    density = "high"
                elif sellers >= 10:
                    density = "moderate"
                elif sellers >= 3:
                    density = "low"
                else:
                    density = "very_low"
                return {
                    "distinct_sellers": sellers,
                    "total_transactions": row.total_txns,
                    "total_volume": float(row.total_volume or 0),
                    "competitor_density": density,
                    "source": "database",
                }
    except Exception as exc:
        logger.warning("competitor_density_query_failed", error=str(exc), region=region)
    return {"distinct_sellers": 0, "competitor_density": "unknown", "source": "query_failed"}


async def _query_repayment_data(worker_id: str) -> Dict[str, Any]:
    """Query loan and repayment history for credit scoring.

    Uses Loan and LoanRepayment tables to calculate on-time rate,
    streak data, and default indicators.
    """
    session_factory = _get_db_session()
    if session_factory is None:
        return {"has_data": False, "source": "no_db"}

    try:
        from sqlalchemy import select, func
        from app.models.loan import Loan, LoanRepayment

        async with session_factory() as session:
            loan_q = select(
                func.count(Loan.id).label("total_loans"),
                func.sum(Loan.amount).label("total_borrowed"),
                func.sum(Loan.amount_repaid).label("total_repaid"),
                func.sum(Loan.total_due).label("total_due"),
                func.avg(Loan.current_streak).label("avg_streak"),
                func.max(Loan.best_streak).label("best_streak"),
            ).where(Loan.user_id == worker_id)

            loan_result = await session.execute(loan_q)
            loan_row = loan_result.one_or_none()

            if not loan_row or not loan_row.total_loans or loan_row.total_loans == 0:
                return {"has_data": False, "source": "no_loans"}

            status_q = select(
                Loan.status,
                func.count(Loan.id).label("count"),
            ).where(Loan.user_id == worker_id).group_by(Loan.status)
            status_result = await session.execute(status_q)
            status_rows = status_result.all()
            status_counts = {r.status: r.count for r in status_rows}

            repay_q = select(
                func.count(LoanRepayment.id).label("total_payments"),
                func.avg(LoanRepayment.amount).label("avg_payment"),
            ).join(Loan, Loan.id == LoanRepayment.loan_id).where(
                Loan.user_id == worker_id
            )
            repay_result = await session.execute(repay_q)
            repay_row = repay_result.one_or_none()

            total_borrowed = float(loan_row.total_borrowed or 0)
            total_repaid = float(loan_row.total_repaid or 0)
            total_due = float(loan_row.total_due or 0)

            on_time_rate = None
            if total_due > 0:
                on_time_rate = round(min(total_repaid / total_due, 1.0), 3)

            completed = status_counts.get("completed", 0)
            defaulted = status_counts.get("defaulted", 0)
            total = loan_row.total_loans

            return {
                "has_data": True,
                "total_loans": total,
                "total_borrowed": total_borrowed,
                "total_repaid": total_repaid,
                "total_due": total_due,
                "on_time_rate": on_time_rate,
                "completed_loans": completed,
                "defaulted_loans": defaulted,
                "active_loans": status_counts.get("active", 0),
                "completion_rate": round(completed / total, 3) if total > 0 else 0,
                "default_rate": round(defaulted / total, 3) if total > 0 else 0,
                "avg_streak": float(loan_row.avg_streak or 0),
                "best_streak": int(loan_row.best_streak or 0),
                "total_repayments": int(repay_row.total_payments or 0) if repay_row else 0,
                "avg_payment_amount": float(repay_row.avg_payment or 0) if repay_row else 0,
                "source": "database",
            }
    except Exception as exc:
        logger.warning("repayment_data_query_failed", error=str(exc), worker_id=worker_id)
    return {"has_data": False, "source": "query_failed"}


async def _query_behavioral_data(worker_id: str) -> Dict[str, Any]:
    """Analyze transaction patterns for behavioral credit signals.

    Calculates regularity, growth trend, and risk flags from
    the worker's transaction history.
    """
    session_factory = _get_db_session()
    if session_factory is None:
        return {"has_data": False, "source": "no_db"}

    try:
        import statistics
        from sqlalchemy import select, func
        from app.models.transaction import Transaction

        async with session_factory() as session:
            monthly_q = select(
                func.date_trunc('month', Transaction.timestamp).label("month"),
                func.count(Transaction.id).label("txn_count"),
                func.sum(Transaction.amount).label("total_amount"),
            ).where(
                Transaction.user_id == worker_id,
            ).group_by(
                func.date_trunc('month', Transaction.timestamp)
            ).order_by(
                func.date_trunc('month', Transaction.timestamp).desc()
            ).limit(6)

            monthly_result = await session.execute(monthly_q)
            monthly_rows = monthly_result.all()

            if not monthly_rows:
                return {"has_data": False, "source": "no_transactions"}

            monthly_amounts = [float(r.total_amount or 0) for r in monthly_rows]
            monthly_counts = [r.txn_count for r in monthly_rows]

            if len(monthly_counts) >= 2:
                mean_count = statistics.mean(monthly_counts)
                if mean_count > 0:
                    cv = statistics.stdev(monthly_counts) / mean_count
                    regularity = round(max(0, 1 - cv), 3)
                else:
                    regularity = 0.0
            else:
                regularity = None

            growth_trend = "stable"
            if len(monthly_amounts) >= 4:
                mid = len(monthly_amounts) // 2
                recent_avg = statistics.mean(monthly_amounts[:mid])
                older_avg = statistics.mean(monthly_amounts[mid:])
                if older_avg > 0:
                    growth_pct = (recent_avg - older_avg) / older_avg
                    if growth_pct > 0.15:
                        growth_trend = "growing"
                    elif growth_pct < -0.15:
                        growth_trend = "declining"

            risk_flags = []
            if len(monthly_amounts) >= 2:
                if monthly_amounts[0] < monthly_amounts[-1] * 0.3:
                    risk_flags.append("sudden_activity_drop")
                zero_months = sum(1 for a in monthly_amounts if a == 0)
                if zero_months > 0:
                    risk_flags.append(f"{zero_months}_inactive_months")

            total_q = select(
                func.count(Transaction.id).label("total"),
                func.avg(Transaction.amount).label("avg_amount"),
                func.count(func.distinct(Transaction.item)).label("distinct_items"),
            ).where(Transaction.user_id == worker_id)
            total_result = await session.execute(total_q)
            total_row = total_result.one_or_none()

            return {
                "has_data": True,
                "regularity": regularity,
                "growth_trend": growth_trend,
                "risk_flags": risk_flags,
                "months_analyzed": len(monthly_rows),
                "total_transactions": int(total_row.total or 0) if total_row else 0,
                "avg_transaction_amount": float(total_row.avg_amount or 0) if total_row else 0,
                "distinct_products": int(total_row.distinct_items or 0) if total_row else 0,
                "monthly_amounts": monthly_amounts,
                "monthly_counts": monthly_counts,
                "source": "database",
            }
    except Exception as exc:
        logger.warning("behavioral_data_query_failed", error=str(exc), worker_id=worker_id)
    return {"has_data": False, "source": "query_failed"}


async def _query_alama_score(worker_id: str) -> Dict[str, Any]:
    """Query the AlamaScore table for existing credit scores.

    Falls back to computing via AlamaScoreService if no cached score exists.
    """
    session_factory = _get_db_session()
    if session_factory is None:
        return {"has_score": False, "source": "no_db"}

    try:
        import hashlib
        from sqlalchemy import select
        from app.models.intelligence_products import AlamaScore as AlamaScoreModel

        async with session_factory() as session:
            biz_hash = hashlib.sha256(str(worker_id).encode()).hexdigest()

            score_q = select(AlamaScoreModel).where(
                AlamaScoreModel.business_hash == biz_hash
            ).order_by(AlamaScoreModel.created_at.desc()).limit(1)

            result = await session.execute(score_q)
            score_row = result.scalar_one_or_none()

            if score_row:
                return {
                    "has_score": True,
                    "score": score_row.alama_score,
                    "band": score_row.score_band,
                    "percentile": float(score_row.percentile or 0),
                    "activity_score": float(score_row.activity_score or 0),
                    "stability_score": float(score_row.stability_score or 0),
                    "growth_score": float(score_row.growth_score or 0),
                    "consistency_score": float(score_row.consistency_score or 0),
                    "diversity_score": float(score_row.diversity_score or 0),
                    "avg_daily_revenue": float(score_row.avg_daily_revenue_kes or 0),
                    "default_probability": float(score_row.default_probability or 0),
                    "recommended_credit_limit": float(score_row.recommended_credit_limit_kes or 0),
                    "source": "database",
                }

            try:
                from app.services.intelligence.alama_score import AlamaScoreService
                service = AlamaScoreService(session)
                computed = await service.compute_score(business_id=str(worker_id))
                if computed and isinstance(computed, dict) and computed.get("alama_score"):
                    return {
                        "has_score": True,
                        "score": computed["alama_score"],
                        "band": computed.get("score_band"),
                        "components": computed.get("components", {}),
                        "source": "computed",
                    }
            except Exception as svc_exc:
                logger.debug("alama_score_service_fallback_failed", error=str(svc_exc))

    except Exception as exc:
        logger.warning("alama_score_query_failed", error=str(exc), worker_id=worker_id)
    return {"has_score": False, "source": "no_score_found"}


async def _query_logistics_data(product: str) -> Dict[str, Any]:
    """Derive logistics insights from transaction location patterns.

    Uses transaction geohash distribution to estimate
    delivery patterns and potential bottlenecks.
    """
    session_factory = _get_db_session()
    if session_factory is None:
        return {"has_data": False, "source": "no_db"}

    try:
        from sqlalchemy import select, func
        from app.models.transaction import Transaction

        async with session_factory() as session:
            loc_q = select(
                func.substring(Transaction.location_geohash, 1, 4).label("area"),
                func.count(Transaction.id).label("txn_count"),
                func.sum(Transaction.amount).label("volume"),
                func.count(func.distinct(Transaction.user_id)).label("sellers"),
            ).where(
                Transaction.location_geohash.isnot(None),
                Transaction.transaction_type == "SALE",
            )
            if product:
                loc_q = loc_q.where(Transaction.item.ilike(f"%{product}%"))
            loc_q = loc_q.group_by(
                func.substring(Transaction.location_geohash, 1, 4)
            ).order_by(func.sum(Transaction.amount).desc())

            result = await session.execute(loc_q)
            rows = result.all()

            if not rows:
                return {"has_data": False, "source": "no_location_data"}

            areas = []
            for r in rows:
                areas.append({
                    "area_geohash": r.area,
                    "txn_count": r.txn_count,
                    "volume": float(r.volume or 0),
                    "sellers": r.sellers,
                })

            total_areas = len(areas)
            total_volume = sum(a["volume"] for a in areas)

            bottlenecks = []
            for a in areas:
                if a["sellers"] <= 2 and a["volume"] > 0:
                    bottlenecks.append({
                        "area": a["area_geohash"],
                        "reason": "high_volume_few_sellers",
                        "volume": a["volume"],
                    })

            return {
                "has_data": True,
                "total_distribution_areas": total_areas,
                "total_volume": total_volume,
                "top_areas": areas[:10],
                "bottlenecks": bottlenecks[:5],
                "avg_volume_per_area": round(total_volume / total_areas, 2) if total_areas > 0 else 0,
                "source": "database",
            }
    except Exception as exc:
        logger.warning("logistics_data_query_failed", error=str(exc), product=product)
    return {"has_data": False, "source": "query_failed"}


async def _query_expansion_opportunities(product: str) -> Dict[str, Any]:
    """Identify expansion opportunities from coverage gaps.

    Compares active distribution areas to find underserved
    regions with high revenue-per-seller potential.
    """
    session_factory = _get_db_session()
    if session_factory is None:
        return {"has_data": False, "source": "no_db"}

    try:
        from sqlalchemy import select, func
        from app.models.transaction import Transaction

        async with session_factory() as session:
            coverage_q = select(
                func.substring(Transaction.location_geohash, 1, 3).label("region"),
                func.count(Transaction.id).label("txn_count"),
                func.sum(Transaction.amount).label("volume"),
                func.count(func.distinct(Transaction.user_id)).label("active_users"),
            ).where(
                Transaction.location_geohash.isnot(None),
            )
            if product:
                coverage_q = coverage_q.where(Transaction.item.ilike(f"%{product}%"))
            coverage_q = coverage_q.group_by(
                func.substring(Transaction.location_geohash, 1, 3)
            )

            result = await session.execute(coverage_q)
            rows = result.all()

            if not rows:
                return {"has_data": False, "source": "no_coverage_data"}

            covered_regions = []
            for r in rows:
                covered_regions.append({
                    "region_geohash": r.region,
                    "txn_count": r.txn_count,
                    "volume": float(r.volume or 0),
                    "active_users": r.active_users,
                })

            covered_regions.sort(key=lambda x: x["volume"], reverse=True)

            priority_regions = []
            for r in covered_regions:
                if r["active_users"] >= 3 and r["volume"] > 0:
                    volume_per_user = r["volume"] / r["active_users"]
                    if volume_per_user > 10000:
                        priority_regions.append({
                            "region": r["region_geohash"],
                            "reason": "high_revenue_per_seller",
                            "volume_per_user": round(volume_per_user, 2),
                            "active_users": r["active_users"],
                            "volume": r["volume"],
                        })

            priority_regions.sort(key=lambda x: x["volume_per_user"], reverse=True)

            return {
                "has_data": True,
                "total_covered_regions": len(covered_regions),
                "coverage_regions": covered_regions,
                "priority_regions": priority_regions[:5],
                "total_volume": sum(r["volume"] for r in covered_regions),
                "total_active_users": sum(r["active_users"] for r in covered_regions),
                "source": "database",
            }
    except Exception as exc:
        logger.warning("expansion_query_failed", error=str(exc), product=product)
    return {"has_data": False, "source": "query_failed"}


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
                # Derive supply/demand from transaction SALES vs PURCHASES
                sd_data = await _query_supply_demand(region, params.get("product"))
                data["supply_demand"] = {
                    "supply_index": sd_data["supply_index"],
                    "demand_index": sd_data["demand_index"],
                    "gap": sd_data["gap"],
                    "supply_volume": sd_data.get("supply_volume"),
                    "demand_volume": sd_data.get("demand_volume"),
                }
                data["source"] = sd_data["source"]
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
                # Estimate competitor density from distinct sellers in transaction data
                comp_data = await _query_competitor_density(region, params.get("product"))
                data["competitors"] = {
                    "count": comp_data["distinct_sellers"],
                    "density": comp_data["competitor_density"],
                    "total_volume": comp_data.get("total_volume"),
                }
                data["source"] = comp_data["source"]
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
                # Query real loan and repayment data from Loan + LoanRepayment tables
                repay_data = await _query_repayment_data(worker_id)
                if repay_data["has_data"]:
                    data["repayment"] = {
                        "on_time_rate": repay_data["on_time_rate"],
                        "completed_loans": repay_data["completed_loans"],
                        "defaulted_loans": repay_data["defaulted_loans"],
                        "active_loans": repay_data["active_loans"],
                        "completion_rate": repay_data["completion_rate"],
                        "default_rate": repay_data["default_rate"],
                        "total_borrowed": repay_data["total_borrowed"],
                        "total_repaid": repay_data["total_repaid"],
                        "avg_streak": repay_data["avg_streak"],
                        "best_streak": repay_data["best_streak"],
                        "total_repayments": repay_data["total_repayments"],
                    }
                else:
                    data["repayment"] = {"on_time_rate": None, "completed_loans": 0, "defaulted_loans": 0}
                data["source"] = repay_data["source"]
            elif "behavior" in action:
                # Analyze transaction patterns for behavioral credit signals
                behav_data = await _query_behavioral_data(worker_id)
                if behav_data["has_data"]:
                    data["behavioral_score"] = {
                        "regularity": behav_data["regularity"],
                        "growth_trend": behav_data["growth_trend"],
                        "risk_flags": behav_data["risk_flags"],
                        "months_analyzed": behav_data["months_analyzed"],
                        "total_transactions": behav_data["total_transactions"],
                        "avg_transaction_amount": behav_data["avg_transaction_amount"],
                        "distinct_products": behav_data["distinct_products"],
                    }
                else:
                    data["behavioral_score"] = {"regularity": None, "growth_trend": "unknown", "risk_flags": []}
                data["source"] = behav_data["source"]
            elif "creditworthiness" in action or "credit_score" in action:
                # Query AlamaScore table or compute via AlamaScoreService
                score_data = await _query_alama_score(worker_id)
                if score_data["has_score"]:
                    band = score_data.get("band", "unknown")
                    data["credit_score"] = {
                        "score": score_data["score"],
                        "rating": band,
                        "confidence": 0.85 if score_data["source"] == "database" else 0.7,
                        "percentile": score_data.get("percentile"),
                        "components": {
                            "activity": score_data.get("activity_score"),
                            "stability": score_data.get("stability_score"),
                            "growth": score_data.get("growth_score"),
                            "consistency": score_data.get("consistency_score"),
                            "diversity": score_data.get("diversity_score"),
                        },
                        "default_probability": score_data.get("default_probability"),
                        "recommended_credit_limit": score_data.get("recommended_credit_limit"),
                    }
                else:
                    data["credit_score"] = {"score": None, "rating": "no_data", "confidence": 0.0}
                data["source"] = score_data["source"]
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
                # Derive logistics insights from transaction location patterns
                log_data = await _query_logistics_data(product)
                if log_data["has_data"]:
                    data["logistics"] = {
                        "total_distribution_areas": log_data["total_distribution_areas"],
                        "total_volume": log_data["total_volume"],
                        "top_areas": log_data["top_areas"],
                        "bottlenecks": log_data["bottlenecks"],
                        "avg_volume_per_area": log_data["avg_volume_per_area"],
                    }
                else:
                    data["logistics"] = {"total_distribution_areas": 0, "bottlenecks": []}
                data["source"] = log_data["source"]
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
                # Identify expansion opportunities from transaction coverage gaps
                exp_data = await _query_expansion_opportunities(product)
                if exp_data["has_data"]:
                    data["expansion"] = {
                        "priority_regions": exp_data["priority_regions"],
                        "total_covered_regions": exp_data["total_covered_regions"],
                        "total_volume": exp_data["total_volume"],
                        "total_active_users": exp_data["total_active_users"],
                    }
                else:
                    data["expansion"] = {"priority_regions": [], "total_covered_regions": 0}
                data["source"] = exp_data["source"]
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

            # Use real transaction data for competitive intelligence
            if "mapping" in action:
                comp_data = await _query_competitor_density(market, params.get("product"))
                data["competitor_map"] = {
                    "direct_competitors": comp_data["distinct_sellers"],
                    "density": comp_data["competitor_density"],
                    "total_market_volume": comp_data.get("total_volume"),
                }
                data["source"] = comp_data["source"]
            elif "pricing" in action:
                prices = await _query_market_prices(market, params.get("product"))
                if prices["data_points"] > 0:
                    data["pricing_analysis"] = {
                        "market_avg": prices["prices"].get("avg"),
                        "market_min": prices["prices"].get("min"),
                        "market_max": prices["prices"].get("max"),
                        "data_points": prices["data_points"],
                    }
                else:
                    data["pricing_analysis"] = {"market_avg": None, "data_points": 0}
                data["source"] = prices["source"]
            elif "feature" in action:
                # Derive feature insights from transaction categories
                try:
                    from sqlalchemy import select, func
                    from app.models.transaction import Transaction
                    session_factory = _get_db_session()
                    if session_factory:
                        async with session_factory() as session:
                            cat_q = select(
                                Transaction.item_category,
                                func.count(Transaction.id).label("count"),
                                func.count(func.distinct(Transaction.user_id)).label("sellers"),
                            ).where(
                                Transaction.transaction_type == "SALE",
                                Transaction.item_category.isnot(None),
                            ).group_by(Transaction.item_category).order_by(
                                func.count(Transaction.id).desc()
                            )
                            result = await session.execute(cat_q)
                            cats = result.all()
                            data["feature_comparison"] = {
                                "market_categories": [
                                    {"category": c.item_category, "transactions": c.count, "sellers": c.sellers}
                                    for c in cats
                                ],
                                "total_categories": len(cats),
                            }
                            data["source"] = "database"
                    else:
                        data["feature_comparison"] = {"market_categories": [], "total_categories": 0}
                        data["source"] = "no_db"
                except Exception:
                    data["feature_comparison"] = {"market_categories": [], "total_categories": 0}
                    data["source"] = "query_failed"
            elif "positioning" in action:
                # Use transaction volume for positioning analysis
                comp_data = await _query_competitor_density(market)
                data["positioning"] = {
                    "market_density": comp_data["competitor_density"],
                    "total_sellers": comp_data["distinct_sellers"],
                    "differentiator": "informal_economy_focus",
                }
                data["source"] = comp_data["source"]
            elif "threat" in action:
                # Derive threat level from competitor density and market dynamics
                comp_data = await _query_competitor_density(market)
                sd_data = await _query_supply_demand(market)
                threat_level = "low"
                if comp_data["competitor_density"] in ("very_high", "high"):
                    threat_level = "high"
                elif comp_data["competitor_density"] == "moderate":
                    threat_level = "medium"
                data["threats"] = [{
                    "type": "market_competition",
                    "level": threat_level,
                    "competitors": comp_data["distinct_sellers"],
                    "supply_demand_gap": sd_data.get("gap"),
                }]
                data["source"] = comp_data["source"]
            else:
                comp_data = await _query_competitor_density(market)
                data["competitor_overview"] = {
                    "total_competitors": comp_data["distinct_sellers"],
                    "density": comp_data["competitor_density"],
                }
                data["source"] = comp_data["source"]

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
