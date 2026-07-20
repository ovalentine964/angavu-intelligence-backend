"""
"""
from __future__ import annotations
from typing import Any
import structlog
logger = structlog.get_logger(__name__)
# ════════════════════════════════════════════════════════════════════
# Database session helper
# ════════════════════════════════════════════════════════════════════
def _get_db_session():
    """Get a database session factory for querying real data.
    """
    try:
        from app.db.database import async_session_factory
        return async_session_factory
    except (ImportError, Exception) as exc:
        logger.debug("db_session_unavailable", error=str(exc))
        return None
# ════════════════════════════════════════════════════════════════════
# Market data queries
# ════════════════════════════════════════════════════════════════════
async def _query_market_prices(region: str, product: str | None = None) -> dict[str, Any]:
    """Query real market price data from the database.
    Falls back to empty structure if DB is unavailable.
    """
    session_factory = _get_db_session()
    if session_factory is None:
        return {"prices": {}, "data_points": 0, "source": "no_db"}
    try:
        from sqlalchemy import func, select
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
async def _query_transaction_history(worker_id: str) -> dict[str, Any]:
    """Query real transaction history for credit scoring.
    Falls back to empty structure if DB is unavailable.
    """
    session_factory = _get_db_session()
    if session_factory is None:
        return {"months_available": 0, "transactions": [], "source": "no_db"}
    try:
        from sqlalchemy import func, select
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
async def _query_distribution_data(product: str) -> dict[str, Any]:
    """Query real distribution/coverage data from the database.
    Falls back to empty structure if DB is unavailable.
    """
    session_factory = _get_db_session()
    if session_factory is None:
        return {"regions": [], "source": "no_db"}
    try:
        from sqlalchemy import func, select
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
async def _query_supply_demand(region: str, product: str | None = None) -> dict[str, Any]:
    """Derive supply/demand signals from transaction data.
    """
    session_factory = _get_db_session()
    if session_factory is None:
        return {"supply_index": None, "demand_index": None, "gap": None, "source": "no_db"}
    try:
        from sqlalchemy import func, select
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
async def _query_competitor_density(region: str, product: str | None = None) -> dict[str, Any]:
    """Estimate competitor density from distinct sellers in the same market.
    More distinct users selling the same product = more competitive.
    """
    session_factory = _get_db_session()
    if session_factory is None:
        return {"distinct_sellers": 0, "competitor_density": "unknown", "source": "no_db"}
    try:
        from sqlalchemy import distinct, func, select
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
# ════════════════════════════════════════════════════════════════════
# Credit / loan data queries
# ════════════════════════════════════════════════════════════════════
async def _query_repayment_data(worker_id: str) -> dict[str, Any]:
    """Query loan and repayment history for credit scoring.
    """
    session_factory = _get_db_session()
    if session_factory is None:
        return {"has_data": False, "source": "no_db"}
    try:
        from sqlalchemy import func, select
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
async def _query_behavioral_data(worker_id: str) -> dict[str, Any]:
    """Analyze transaction patterns for behavioral credit signals.
    """
    session_factory = _get_db_session()
    if session_factory is None:
        return {"has_data": False, "source": "no_db"}
    try:
        import statistics
        from sqlalchemy import func, select
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
async def _query_alama_score(worker_id: str) -> dict[str, Any]:
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
# ════════════════════════════════════════════════════════════════════
# Distribution / logistics data queries
# ════════════════════════════════════════════════════════════════════
async def _query_logistics_data(product: str) -> dict[str, Any]:
    """Derive logistics insights from transaction location patterns.
    """
    session_factory = _get_db_session()
    if session_factory is None:
        return {"has_data": False, "source": "no_db"}
    try:
        from sqlalchemy import func, select
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
async def _query_category_breakdown() -> dict[str, Any]:
    """Query transaction category breakdown for feature comparison.
    Returns market categories with transaction counts and seller counts.
    """
    session_factory = _get_db_session()
    if session_factory is None:
        return {"market_categories": [], "total_categories": 0, "source": "no_db"}
    try:
        from sqlalchemy import func, select
        from app.models.transaction import Transaction
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
            return {
                "market_categories": [
                    {"category": c.item_category, "transactions": c.count, "sellers": c.sellers}
                    for c in cats
                ],
                "total_categories": len(cats),
                "source": "database",
            }
    except Exception as exc:
        logger.warning("category_breakdown_query_failed", error=str(exc))
    return {"market_categories": [], "total_categories": 0, "source": "query_failed"}
async def _query_expansion_opportunities(product: str) -> dict[str, Any]:
    """Identify expansion opportunities from coverage gaps.
    """
    session_factory = _get_db_session()
    if session_factory is None:
        return {"has_data": False, "source": "no_db"}
    try:
        from sqlalchemy import func, select
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
