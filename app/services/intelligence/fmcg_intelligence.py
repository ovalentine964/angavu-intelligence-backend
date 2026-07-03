"""
FMCG Intelligence Service — Informal Channel Tracking.

FMCG-specific intelligence for companies like Pwani Oil, Unilever, Bidco.

Provides:
- Informal channel sales tracking (dukas, kiosks, markets)
- Route-to-market optimization
- Trade promotion ROI analysis
- Distribution gap identification
- Competitive pricing intelligence
- Fleet utilization optimization

Data source: 600M+ informal workers via Msaidizi network

Buyers: FMCG manufacturers and distributors operating in East Africa
"""

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import numpy as np
import structlog
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.transaction import Transaction
from app.models.user import User
from app.services.anonymizer import Anonymizer
from app.services.intelligence.cache import intelligence_cache
from app.services.intelligence.templates.pwani_oil import PwaniOilTemplate

logger = structlog.get_logger(__name__)
settings = get_settings()


class FMCGIntelligenceService:
    """
    FMCG-specific intelligence service for informal market tracking.

    Bridges the gap between formal FMCG operations and the 70%+ of
    East African commerce that happens through informal channels
    (dukas, kiosks, mama mbogas, open-air markets).

    Powered by Angavu Intelligence's network of 600M+ informal
    economy participants providing ground-truth data from actual
    points of sale.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.anonymizer = Anonymizer(db)

    # ─────────────────────────────────────────────────────────────────────────
    # 1. Informal Channel Sales Tracking
    # ─────────────────────────────────────────────────────────────────────────

    async def get_informal_channel_sales(
        self,
        company: str,
        region: str,
        period_start: Optional[date] = None,
        period_end: Optional[date] = None,
        product_category: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Track sales through informal channels (dukas, kiosks, markets).

        Provides real-time visibility into how products move through
        the informal distribution network — channels that Nielsen and
        Kantar don't cover.

        Args:
            company: Company identifier (e.g., 'pwani_oil')
            region: Geographic region (e.g., 'coast', 'nairobi')
            period_start: Analysis start (default: 30 days ago)
            period_end: Analysis end (default: today)
            product_category: Filter by category (cooking_oils, personal_care, home_care)

        Returns:
            Dict with informal channel sales metrics
        """
        cache_key = f"informal_sales_{company}_{region}"
        cached = await intelligence_cache.get(
            cache_key,
            company=company, region=region,
            start=str(period_start), end=str(period_end),
        )
        if cached:
            return cached

        if not period_end:
            period_end = date.today()
        if not period_start:
            period_start = period_end - timedelta(days=30)

        # Resolve company template
        template = self._get_template(company)
        products = template.get_all_products_flat() if template else []

        # Query informal channel transactions
        query = select(Transaction).where(
            and_(
                Transaction.transaction_type == "SALE",
                Transaction.timestamp >= datetime.combine(period_start, datetime.min.time()),
                Transaction.timestamp <= datetime.combine(period_end, datetime.max.time()),
            )
        )

        # Region filter via user location
        region_prefix = self._region_to_geohash(region)
        if region_prefix:
            query = query.join(User, Transaction.user_id == User.id).where(
                User.location_geohash.like(f"{region_prefix}%")
            )

        if product_category and template:
            category_products = template.get_products_by_category(product_category)
            if category_products:
                query = query.where(Transaction.item.in_(category_products))

        result = await self.db.execute(query)
        transactions = result.scalars().all()

        # Aggregate by vendor, product, day
        vendor_set = set()
        product_metrics = defaultdict(lambda: {
            "volume": 0, "revenue": 0, "transactions": 0, "vendors": set()
        })
        daily_revenue = defaultdict(float)
        channel_breakdown = defaultdict(lambda: {"volume": 0, "revenue": 0, "count": 0})

        for t in transactions:
            vendor_set.add(t.user_id)
            product_metrics[t.item]["volume"] += t.quantity or 0
            product_metrics[t.item]["revenue"] += t.amount
            product_metrics[t.item]["transactions"] += 1
            product_metrics[t.item]["vendors"].add(t.user_id)
            daily_revenue[t.timestamp.strftime("%Y-%m-%d")] += t.amount

            # Classify channel type (heuristic based on transaction size)
            avg_txn = t.amount / max(t.quantity or 1, 1)
            if avg_txn < 200:
                channel = "kiosk"
            elif avg_txn < 2000:
                channel = "duka"
            else:
                channel = "wholesaler"
            channel_breakdown[channel]["volume"] += t.quantity or 0
            channel_breakdown[channel]["revenue"] += t.amount
            channel_breakdown[channel]["count"] += 1

        k = len(vendor_set)
        if k < settings.K_ANONYMITY_THRESHOLD:
            return {
                "status": "insufficient_data",
                "message": f"Need {settings.K_ANONYMITY_THRESHOLD}+ unique vendors for k-anonymity",
                "vendors_found": k,
            }

        total_revenue = sum(m["revenue"] for m in product_metrics.values())
        total_volume = sum(m["volume"] for m in product_metrics.values())
        days = (period_end - period_start).days or 1

        # Apply differential privacy
        dp_revenue = max(0, self.anonymizer.add_laplace_noise(
            total_revenue, sensitivity=50000
        ))

        # Build product breakdown
        product_breakdown = []
        for product, metrics in sorted(
            product_metrics.items(), key=lambda x: x[1]["revenue"], reverse=True
        ):
            product_breakdown.append({
                "product": product,
                "volume": round(metrics["volume"], 2),
                "revenue": round(metrics["revenue"], 2),
                "transaction_count": metrics["transactions"],
                "vendor_count": len(metrics["vendors"]),
                "avg_price": round(
                    metrics["revenue"] / max(metrics["volume"], 1), 2
                ),
            })

        # Channel type breakdown
        channels = []
        for ch_type, ch_data in channel_breakdown.items():
            channels.append({
                "channel_type": ch_type,
                "volume": round(ch_data["volume"], 2),
                "revenue": round(ch_data["revenue"], 2),
                "transaction_count": ch_data["count"],
                "revenue_share_pct": round(
                    ch_data["revenue"] / max(total_revenue, 1) * 100, 1
                ),
            })

        response = {
            "service": "fmcg_informal_channel_sales",
            "version": "1.0",
            "company": company,
            "region": region,
            "period": f"{period_start} to {period_end}",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "total_revenue_kes": round(dp_revenue, 2),
                "total_volume": round(total_volume, 2),
                "unique_vendors": k,
                "unique_products": len(product_metrics),
                "days_in_period": days,
                "avg_daily_revenue": round(dp_revenue / max(days, 1), 2),
                "avg_transaction_value": round(
                    total_revenue / max(len(transactions), 1), 2
                ),
            },
            "product_breakdown": product_breakdown,
            "channel_breakdown": channels,
            "data_quality": {
                "k_anonymity": k,
                "quality_score": min(1.0, k / 50),
                "confidence_level": min(1.0, len(transactions) / 200),
            },
        }

        await intelligence_cache.set(cache_key, response,
            company=company, region=region,
            start=str(period_start), end=str(period_end),
        )

        logger.info(
            "informal_channel_sales_tracked",
            company=company, region=region,
            revenue=round(dp_revenue), vendors=k,
        )
        return response

    # ─────────────────────────────────────────────────────────────────────────
    # 2. Route-to-Market Optimization
    # ─────────────────────────────────────────────────────────────────────────

    async def get_route_to_market_analysis(
        self,
        company: str,
        period_start: Optional[date] = None,
        period_end: Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        Optimize distribution routes for informal markets.

        Maps informal distribution networks, identifies bottlenecks,
        and recommends route optimizations for maximum coverage with
        minimum logistics cost.

        Args:
            company: Company identifier
            period_start: Analysis start (default: 90 days ago)
            period_end: Analysis end (default: today)

        Returns:
            Dict with route optimization recommendations
        """
        if not period_end:
            period_end = date.today()
        if not period_start:
            period_start = period_end - timedelta(days=90)

        template = self._get_template(company)

        # Get vendor distribution across regions
        query = (
            select(
                User.location_geohash,
                func.count(User.id).label("vendor_count"),
            )
            .where(
                and_(
                    User.is_active == True,
                    User.consent_data_sharing == True,
                    User.location_geohash.isnot(None),
                )
            )
            .group_by(User.location_geohash)
        )
        result = await self.db.execute(query)
        vendor_locations = result.all()

        # Get transaction volume by location
        txn_query = select(Transaction).where(
            and_(
                Transaction.transaction_type == "SALE",
                Transaction.timestamp >= datetime.combine(period_start, datetime.min.time()),
                Transaction.timestamp <= datetime.combine(period_end, datetime.max.time()),
            )
        )
        result = await self.db.execute(txn_query)
        transactions = result.scalars().all()

        # Build location-volume map
        location_volume = defaultdict(lambda: {"volume": 0, "revenue": 0, "vendors": set()})
        for t in transactions:
            user_query = select(User.location_geohash).where(User.id == t.user_id)
            user_result = await self.db.execute(user_query)
            loc = user_result.scalar()
            if loc:
                prefix = loc[:5]
                location_volume[prefix]["volume"] += t.quantity or 0
                location_volume[prefix]["revenue"] += t.amount
                location_volume[prefix]["vendors"].add(t.user_id)

        # Analyze route efficiency
        routes = []
        for loc, data in sorted(
            location_volume.items(), key=lambda x: x[1]["revenue"], reverse=True
        ):
            vendor_count = len(data["vendors"])
            revenue_per_vendor = data["revenue"] / max(vendor_count, 1)
            routes.append({
                "location": loc,
                "vendor_count": vendor_count,
                "total_volume": round(data["volume"], 2),
                "total_revenue": round(data["revenue"], 2),
                "revenue_per_vendor": round(revenue_per_vendor, 2),
                "efficiency_score": min(100, round(revenue_per_vendor / 100, 1)),
            })

        # Identify underserved high-potential areas
        if template:
            expansion_priorities = template.get_expansion_priorities()
        else:
            expansion_priorities = []

        # Route consolidation recommendations
        low_efficiency = [r for r in routes if r["efficiency_score"] < 30]
        high_potential = [r for r in routes if r["efficiency_score"] > 70]

        return {
            "service": "fmcg_route_to_market",
            "version": "1.0",
            "company": company,
            "period": f"{period_start} to {period_end}",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "route_analysis": {
                "total_active_routes": len(routes),
                "high_efficiency_routes": len(high_potential),
                "low_efficiency_routes": len(low_efficiency),
                "routes": routes[:20],
            },
            "expansion_opportunities": expansion_priorities[:5] if expansion_priorities else [],
            "consolidation_recommendations": [
                {
                    "location": r["location"],
                    "action": "consolidate",
                    "reason": "low_revenue_per_vendor",
                    "current_efficiency": r["efficiency_score"],
                }
                for r in low_efficiency[:5]
            ],
            "data_quality": {
                "locations_analyzed": len(routes),
                "transactions_analyzed": len(transactions),
            },
        }

    # ─────────────────────────────────────────────────────────────────────────
    # 3. Trade Promotion ROI
    # ─────────────────────────────────────────────────────────────────────────

    async def get_trade_promotion_roi(
        self,
        company: str,
        promotion_id: str,
        promotion_start: Optional[date] = None,
        promotion_end: Optional[date] = None,
        baseline_days: int = 30,
    ) -> Dict[str, Any]:
        """
        Measure ROI of trade promotions in informal channels.

        Tracks whether promotions actually drive incremental sales
        or just shift timing. Measures adoption across informal outlets.

        Args:
            company: Company identifier
            promotion_id: Promotion identifier
            promotion_start: Promotion start date
            promotion_end: Promotion end date
            baseline_days: Days of pre-promotion baseline

        Returns:
            Dict with promotion ROI analysis
        """
        if not promotion_end:
            promotion_end = date.today()
        if not promotion_start:
            promotion_start = promotion_end - timedelta(days=14)

        baseline_start = promotion_start - timedelta(days=baseline_days)

        template = self._get_template(company)

        # Get baseline period transactions
        baseline_query = select(Transaction).where(
            and_(
                Transaction.transaction_type == "SALE",
                Transaction.timestamp >= datetime.combine(baseline_start, datetime.min.time()),
                Transaction.timestamp < datetime.combine(promotion_start, datetime.min.time()),
            )
        )
        result = await self.db.execute(baseline_query)
        baseline_txns = result.scalars().all()

        # Get promotion period transactions
        promo_query = select(Transaction).where(
            and_(
                Transaction.transaction_type == "SALE",
                Transaction.timestamp >= datetime.combine(promotion_start, datetime.min.time()),
                Transaction.timestamp <= datetime.combine(promotion_end, datetime.max.time()),
            )
        )
        result = await self.db.execute(promo_query)
        promo_txns = result.scalars().all()

        baseline_days_actual = (promotion_start - baseline_start).days or 1
        promo_days = (promotion_end - promotion_start).days or 1

        # Aggregate metrics
        baseline_revenue = sum(t.amount for t in baseline_txns)
        promo_revenue = sum(t.amount for t in promo_txns)
        baseline_volume = sum(t.quantity or 0 for t in baseline_txns)
        promo_volume = sum(t.quantity or 0 for t in promo_txns)

        baseline_vendors = len(set(t.user_id for t in baseline_txns))
        promo_vendors = len(set(t.user_id for t in promo_txns))

        # Normalize to daily rates
        baseline_daily_rev = baseline_revenue / max(baseline_days_actual, 1)
        promo_daily_rev = promo_revenue / max(promo_days, 1)
        baseline_daily_vol = baseline_volume / max(baseline_days_actual, 1)
        promo_daily_vol = promo_volume / max(promo_days, 1)

        # Calculate lift
        revenue_lift_pct = (
            (promo_daily_rev - baseline_daily_rev) / max(baseline_daily_rev, 1) * 100
        )
        volume_lift_pct = (
            (promo_daily_vol - baseline_daily_vol) / max(baseline_daily_vol, 1) * 100
        )

        # Vendor adoption rate
        new_vendors = promo_vendors - baseline_vendors
        vendor_adoption_pct = new_vendors / max(baseline_vendors, 1) * 100

        # Estimated promotion cost (heuristic: 5% of incremental revenue)
        incremental_revenue = max(0, (promo_daily_rev - baseline_daily_rev) * promo_days)
        estimated_promo_cost = incremental_revenue * 0.05
        roi_pct = (
            (incremental_revenue - estimated_promo_cost)
            / max(estimated_promo_cost, 1) * 100
        )

        return {
            "service": "fmcg_trade_promotion_roi",
            "version": "1.0",
            "company": company,
            "promotion_id": promotion_id,
            "promotion_period": f"{promotion_start} to {promotion_end}",
            "baseline_period": f"{baseline_start} to {promotion_start}",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "baseline_metrics": {
                "total_revenue_kes": round(baseline_revenue, 2),
                "total_volume": round(baseline_volume, 2),
                "daily_avg_revenue": round(baseline_daily_rev, 2),
                "daily_avg_volume": round(baseline_daily_vol, 2),
                "unique_vendors": baseline_vendors,
                "days": baseline_days_actual,
            },
            "promotion_metrics": {
                "total_revenue_kes": round(promo_revenue, 2),
                "total_volume": round(promo_volume, 2),
                "daily_avg_revenue": round(promo_daily_rev, 2),
                "daily_avg_volume": round(promo_daily_vol, 2),
                "unique_vendors": promo_vendors,
                "days": promo_days,
            },
            "impact": {
                "revenue_lift_pct": round(revenue_lift_pct, 1),
                "volume_lift_pct": round(volume_lift_pct, 1),
                "incremental_revenue_kes": round(incremental_revenue, 2),
                "new_vendors_adopted": max(0, new_vendors),
                "vendor_adoption_pct": round(vendor_adoption_pct, 1),
                "estimated_promo_cost_kes": round(estimated_promo_cost, 2),
                "estimated_roi_pct": round(roi_pct, 1),
                "effectiveness": (
                    "high" if revenue_lift_pct > 20
                    else "moderate" if revenue_lift_pct > 5
                    else "low" if revenue_lift_pct > 0
                    else "negative"
                ),
            },
            "data_quality": {
                "baseline_transactions": len(baseline_txns),
                "promotion_transactions": len(promo_txns),
                "confidence": min(1.0, (len(baseline_txns) + len(promo_txns)) / 200),
            },
        }

    # ─────────────────────────────────────────────────────────────────────────
    # 4. Distribution Gap Identification
    # ─────────────────────────────────────────────────────────────────────────

    async def get_distribution_gaps(
        self,
        company: str,
        product: str,
        region: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Identify where products aren't reaching in informal channels.

        Cross-references product sales data with population density
        and informal market presence to find distribution blind spots.

        Args:
            company: Company identifier
            product: Product name (e.g., 'Fresh Fri', 'Salit')
            region: Region to analyze (default: national)

        Returns:
            Dict with distribution gap analysis
        """
        template = self._get_template(company)
        period_end = date.today()
        period_start = period_end - timedelta(days=90)

        # Get all markets with vendor presence
        market_query = (
            select(
                User.location_geohash,
                func.count(User.id).label("vendor_count"),
            )
            .where(
                and_(
                    User.is_active == True,
                    User.consent_data_sharing == True,
                    User.location_geohash.isnot(None),
                )
            )
            .group_by(User.location_geohash)
        )
        if region:
            prefix = self._region_to_geohash(region)
            if prefix:
                market_query = market_query.where(
                    User.location_geohash.like(f"{prefix}%")
                )

        result = await self.db.execute(market_query)
        all_markets = result.all()

        # Get markets with this product
        product_query = select(Transaction).where(
            and_(
                Transaction.transaction_type == "SALE",
                Transaction.item == product,
                Transaction.timestamp >= datetime.combine(period_start, datetime.min.time()),
                Transaction.timestamp <= datetime.combine(period_end, datetime.max.time()),
            )
        )
        result = await self.db.execute(product_query)
        product_txns = result.scalars().all()

        # Map product presence by market
        markets_with_product = set()
        market_revenue = defaultdict(float)
        for t in product_txns:
            user_query = select(User.location_geohash).where(User.id == t.user_id)
            user_result = await self.db.execute(user_query)
            loc = user_result.scalar()
            if loc:
                market = loc[:5]
                markets_with_product.add(market)
                market_revenue[market] += t.amount

        # Identify gaps
        all_market_codes = set(m[0][:5] for m in all_markets if m[0])
        gap_markets = all_market_codes - markets_with_product

        # Filter by k-anonymity
        market_user_counts = {}
        for m in all_markets:
            code = m[0][:5]
            market_user_counts[code] = market_user_counts.get(code, 0) + m[1]

        valid_gaps = [
            m for m in gap_markets
            if market_user_counts.get(m, 0) >= settings.K_ANONYMITY_THRESHOLD
        ]

        total_markets = len(all_market_codes)
        covered = len(markets_with_product)
        coverage_pct = round(covered / max(total_markets, 1) * 100, 1)

        # Estimate revenue potential of gap markets
        avg_revenue = (
            np.mean(list(market_revenue.values())) if market_revenue else 0
        )
        gap_potential = round(avg_revenue * len(valid_gaps), 0)

        # Rank gap markets by opportunity
        gap_rankings = []
        for m in valid_gaps:
            user_count = market_user_counts.get(m, 0)
            gap_rankings.append({
                "market_id": m,
                "population_proxy": user_count,
                "opportunity_score": min(100, round(user_count / 10, 1)),
                "estimated_monthly_revenue_kes": round(
                    avg_revenue * (user_count / max(
                        np.mean(list(market_user_counts.values())), 1
                    )), 0
                ),
            })
        gap_rankings.sort(key=lambda x: x["opportunity_score"], reverse=True)

        # Competitor presence in gap markets (if template available)
        competitors = []
        if template:
            competitors = [
                {"name": c["name"], "products": c["key_products"]}
                for c in template.COMPETITORS.values()
            ]

        return {
            "service": "fmcg_distribution_gaps",
            "version": "1.0",
            "company": company,
            "product": product,
            "region": region or "national",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "coverage": {
                "total_markets": total_markets,
                "markets_with_product": covered,
                "gap_markets": len(valid_gaps),
                "coverage_pct": coverage_pct,
                "gap_pct": round(100 - coverage_pct, 1),
            },
            "gap_markets": gap_rankings[:20],
            "gap_revenue_potential_kes": gap_potential,
            "competitors_in_gaps": competitors[:5],
            "recommendations": [
                {
                    "priority": "high",
                    "action": "expand_distribution",
                    "target_markets": [g["market_id"] for g in gap_rankings[:5]],
                    "estimated_impact_kes": round(
                        sum(g["estimated_monthly_revenue_kes"] for g in gap_rankings[:5]), 0
                    ),
                },
                {
                    "priority": "medium",
                    "action": "increase_penetration",
                    "target_markets": [
                        m for m in markets_with_product
                        if market_revenue.get(m, 0) < avg_revenue * 0.5
                    ][:5],
                    "reason": "below_average_revenue",
                },
            ],
        }

    # ─────────────────────────────────────────────────────────────────────────
    # 5. Competitive Pricing Intelligence
    # ─────────────────────────────────────────────────────────────────────────

    async def get_competitive_pricing(
        self,
        company: str,
        product_category: str,
        region: Optional[str] = None,
        period_days: int = 30,
    ) -> Dict[str, Any]:
        """
        Track competitor pricing across informal markets.

        Monitors price points at the last mile — what consumers
        actually pay vs. recommended retail price. Tracks competitor
        pricing moves in real time.

        Args:
            company: Company identifier
            product_category: Category (cooking_oils, personal_care, home_care)
            region: Geographic region filter
            period_days: Analysis window in days

        Returns:
            Dict with competitive pricing intelligence
        """
        period_end = date.today()
        period_start = period_end - timedelta(days=period_days)

        template = self._get_template(company)

        # Get all transactions in category
        query = select(Transaction).where(
            and_(
                Transaction.transaction_type == "SALE",
                Transaction.item_category == product_category,
                Transaction.timestamp >= datetime.combine(period_start, datetime.min.time()),
                Transaction.timestamp <= datetime.combine(period_end, datetime.max.time()),
            )
        )

        if region:
            prefix = self._region_to_geohash(region)
            if prefix:
                query = query.join(User, Transaction.user_id == User.id).where(
                    User.location_geohash.like(f"{prefix}%")
                )

        result = await self.db.execute(query)
        transactions = result.scalars().all()

        # Price analysis by product
        product_prices = defaultdict(list)
        for t in transactions:
            if t.unit_price and t.unit_price > 0:
                product_prices[t.item].append(t.unit_price)

        price_analysis = []
        for product, prices in sorted(product_prices.items()):
            if len(prices) < 5:
                continue
            prices_arr = np.array(prices)
            price_analysis.append({
                "product": product,
                "sample_size": len(prices),
                "avg_price_kes": round(float(np.mean(prices_arr)), 2),
                "median_price_kes": round(float(np.median(prices_arr)), 2),
                "min_price_kes": round(float(np.min(prices_arr)), 2),
                "max_price_kes": round(float(np.max(prices_arr)), 2),
                "std_dev": round(float(np.std(prices_arr)), 2),
                "coefficient_of_variation": round(
                    float(np.std(prices_arr) / max(np.mean(prices_arr), 1) * 100), 1
                ),
                "is_company_product": (
                    template is not None
                    and product in template.get_all_products_flat()
                ),
            })

        # Competitive positioning
        company_products = []
        competitor_products = []
        for p in price_analysis:
            if p["is_company_product"]:
                company_products.append(p)
            else:
                competitor_products.append(p)

        # Price gaps
        price_gaps = []
        if company_products and competitor_products:
            avg_company = np.mean([p["avg_price_kes"] for p in company_products])
            avg_competitor = np.mean([p["avg_price_kes"] for p in competitor_products])
            price_gaps.append({
                "company_avg": round(float(avg_company), 2),
                "competitor_avg": round(float(avg_competitor), 2),
                "gap_pct": round(
                    (avg_company - avg_competitor) / max(avg_competitor, 1) * 100, 1
                ),
                "position": (
                    "premium" if avg_company > avg_competitor * 1.1
                    else "competitive" if avg_company > avg_competitor * 0.9
                    else "value"
                ),
            })

        return {
            "service": "fmcg_competitive_pricing",
            "version": "1.0",
            "company": company,
            "category": product_category,
            "region": region or "national",
            "period": f"{period_start} to {period_end}",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "price_analysis": price_analysis,
            "company_products": company_products,
            "competitor_products": competitor_products[:10],
            "competitive_positioning": price_gaps,
            "price_volatility_alerts": [
                p for p in price_analysis if p["coefficient_of_variation"] > 20
            ],
            "data_quality": {
                "transactions_analyzed": len(transactions),
                "products_tracked": len(price_analysis),
                "confidence": min(1.0, len(transactions) / 500),
            },
        }

    # ─────────────────────────────────────────────────────────────────────────
    # 6. Fleet Utilization Optimization
    # ─────────────────────────────────────────────────────────────────────────

    async def get_fleet_utilization(
        self,
        company: str,
        period_days: int = 30,
    ) -> Dict[str, Any]:
        """
        Optimize delivery fleet for informal distribution.

        Analyzes transaction density patterns to recommend optimal
        delivery routes, timing, and fleet allocation for reaching
        informal markets efficiently.

        Args:
            company: Company identifier
            period_days: Analysis window

        Returns:
            Dict with fleet utilization recommendations
        """
        period_end = date.today()
        period_start = period_end - timedelta(days=period_days)

        # Get vendor distribution (proxy for delivery demand)
        vendor_query = (
            select(
                User.location_geohash,
                func.count(User.id).label("vendor_count"),
            )
            .where(
                and_(
                    User.is_active == True,
                    User.consent_data_sharing == True,
                    User.location_geohash.isnot(None),
                )
            )
            .group_by(User.location_geohash)
        )
        result = await self.db.execute(vendor_query)
        vendor_locations = result.all()

        # Get transaction volume by location and day-of-week
        txn_query = select(Transaction).where(
            and_(
                Transaction.transaction_type == "SALE",
                Transaction.timestamp >= datetime.combine(period_start, datetime.min.time()),
                Transaction.timestamp <= datetime.combine(period_end, datetime.max.time()),
            )
        )
        result = await self.db.execute(txn_query)
        transactions = result.scalars().all()

        # Build demand heatmap
        location_demand = defaultdict(lambda: {
            "volume": 0, "vendors": set(), "dow_pattern": defaultdict(float)
        })
        for t in transactions:
            user_query = select(User.location_geohash).where(User.id == t.user_id)
            user_result = await self.db.execute(user_query)
            loc = user_result.scalar()
            if loc:
                prefix = loc[:5]
                location_demand[prefix]["volume"] += t.quantity or 0
                location_demand[prefix]["vendors"].add(t.user_id)
                dow = t.timestamp.strftime("%a")
                location_demand[prefix]["dow_pattern"][dow] += t.amount

        # Route recommendations
        routes = []
        for loc, data in sorted(
            location_demand.items(), key=lambda x: len(x[1]["vendors"]), reverse=True
        ):
            vendor_count = len(data["vendors"])
            # Peak delivery day
            dow = data["dow_pattern"]
            peak_day = max(dow, key=dow.get) if dow else "Mon"

            routes.append({
                "location": loc,
                "vendor_count": vendor_count,
                "demand_volume": round(data["volume"], 2),
                "recommended_frequency": (
                    "daily" if vendor_count > 20
                    else "3x_weekly" if vendor_count > 10
                    else "weekly"
                ),
                "peak_delivery_day": peak_day,
                "priority": "high" if vendor_count > 15 else "medium" if vendor_count > 5 else "low",
            })

        # Fleet allocation (heuristic)
        high_priority = [r for r in routes if r["priority"] == "high"]
        medium_priority = [r for r in routes if r["priority"] == "medium"]

        estimated_vehicles = max(1, len(high_priority) * 2 + len(medium_priority))

        return {
            "service": "fmcg_fleet_utilization",
            "version": "1.0",
            "company": company,
            "period": f"{period_start} to {period_end}",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "demand_heatmap": routes[:30],
            "fleet_recommendations": {
                "estimated_vehicles_needed": estimated_vehicles,
                "high_priority_routes": len(high_priority),
                "medium_priority_routes": len(medium_priority),
                "total_active_locations": len(routes),
            },
            "optimization_opportunities": [
                {
                    "type": "route_consolidation",
                    "description": "Combine low-volume adjacent routes",
                    "target_routes": [r for r in routes if r["priority"] == "low"][:5],
                    "estimated_savings_pct": 15,
                },
                {
                    "type": "frequency_adjustment",
                    "description": "Reduce delivery frequency to low-demand areas",
                    "target_routes": [r for r in routes if r["recommended_frequency"] == "weekly"],
                    "estimated_savings_pct": 10,
                },
            ],
            "data_quality": {
                "locations_analyzed": len(routes),
                "transactions_analyzed": len(transactions),
            },
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _get_template(company: str) -> Optional[PwaniOilTemplate]:
        """Get client template by company identifier."""
        templates = {
            "pwani_oil": PwaniOilTemplate,
            "pwani": PwaniOilTemplate,
        }
        template_class = templates.get(company.lower())
        return template_class() if template_class else None

    @staticmethod
    def _region_to_geohash(region: str) -> Optional[str]:
        """Convert region name to geohash prefix for filtering."""
        # Map region names to approximate geohash prefixes for Kenya
        region_map = {
            "coast": "k",
            "nairobi": "kd",
            "central": "kc",
            "western": "jb",
            "nyanza": "jb",
            "rift_valley": "jj",
            "eastern": "kd",
            "north_eastern": "k",
        }
        return region_map.get(region.lower())
