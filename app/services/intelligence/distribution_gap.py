"""
Distribution Gap Analysis — FMCG Market Coverage Service.

Identifies where products are NOT reaching:
- Underserved market identification
- Coverage and penetration analysis
- Expansion recommendations with ROI

Buyers: FMCG distribution companies
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

logger = structlog.get_logger(__name__)
settings = get_settings()


class DistributionGapService:
    """
    Distribution gap analysis service for FMCG buyers.

    Identifies markets where products are not reaching
    and estimates revenue potential of gap markets.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.anonymizer = Anonymizer(db)

    async def analyze_gaps(
        self,
        product_category: str,
        product_name: Optional[str] = None,
        region: Optional[str] = None,
        period_start: Optional[date] = None,
        period_end: Optional[date] = None,
        buyer_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Analyze distribution gaps for a product category.

        Args:
            product_category: Category to analyze
            product_name: Specific product or None for category
            region: Geographic region or None for national
            period_start: Analysis start (default: 90 days ago)
            period_end: Analysis end (default: today)
            buyer_id: Buyer requesting this data

        Returns:
            Gap analysis dict or None if insufficient data
        """
        cached = await intelligence_cache.get(
            "distribution_gap",
            category=product_category,
            product=product_name,
            region=region,
            start=str(period_start),
            end=str(period_end),
        )
        if cached:
            return cached

        if not period_end:
            period_end = date.today()
        if not period_start:
            period_start = period_end - timedelta(days=90)

        # Get all markets (geohash-5 areas) with active users
        market_query = (
            select(
                User.location_geohash,
                func.count(User.id).label("user_count"),
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
            market_query = market_query.where(
                User.location_geohash.like(f"{region}%")
            )

        result = await self.db.execute(market_query)
        all_markets = result.all()

        if not all_markets:
            return None

        # Get markets that have the product
        product_query = select(Transaction).where(
            and_(
                Transaction.transaction_type == "SALE",
                Transaction.item_category == product_category,
                Transaction.timestamp >= datetime.combine(period_start, datetime.min.time()),
                Transaction.timestamp <= datetime.combine(period_end, datetime.max.time()),
            )
        )
        if product_name:
            product_query = product_query.where(Transaction.item == product_name)

        result = await self.db.execute(product_query)
        product_txns = result.scalars().all()

        # Group by market
        markets_with_product = set()
        market_data = defaultdict(lambda: {
            "volume": 0, "revenue": 0, "vendors": set(), "txns": 0
        })
        for t in product_txns:
            # Find user's market
            user_query = select(User.location_geohash).where(User.id == t.user_id)
            user_result = await self.db.execute(user_query)
            loc = user_result.scalar()
            if loc:
                market = loc[:5]  # geohash-5
                markets_with_product.add(market)
                market_data[market]["volume"] += t.quantity or 0
                market_data[market]["revenue"] += t.amount
                market_data[market]["vendors"].add(t.user_id)
                market_data[market]["txns"] += 1

        # Identify gap markets
        all_market_codes = set(m[0][:5] for m in all_markets if m[0])
        gap_markets = all_market_codes - markets_with_product

        # k-anonymity: only report markets with enough users
        market_user_counts = {}
        for m in all_markets:
            code = m[0][:5]
            market_user_counts[code] = market_user_counts.get(code, 0) + m[1]

        valid_gap_markets = [
            m for m in gap_markets
            if market_user_counts.get(m, 0) >= settings.K_ANONYMITY_THRESHOLD
        ]

        total_markets = len(all_market_codes)
        covered_markets = len(markets_with_product)
        coverage_pct = round(covered_markets / max(total_markets, 1) * 100, 1)

        # Estimate revenue potential for gap markets
        avg_revenue_per_market = 0
        if market_data:
            avg_revenue_per_market = np.mean([
                d["revenue"] for d in market_data.values()
            ])

        gap_revenue_potential = round(avg_revenue_per_market * len(valid_gap_markets), 0)

        # Demand index for gap markets (based on user count as proxy)
        gap_demand = {}
        for m in valid_gap_markets[:20]:  # Top 20 gaps
            user_count = market_user_counts.get(m, 0)
            demand_index = min(100, round(user_count / 10, 1))
            gap_demand[m] = {
                "market_id": m,
                "user_count": user_count,
                "demand_index": demand_index,
                "revenue_potential_kes": round(avg_revenue_per_market * (demand_index / 50), 0),
            }

        # Sort by demand
        sorted_gaps = sorted(
            gap_demand.values(),
            key=lambda x: x["demand_index"],
            reverse=True,
        )

        # Priority gaps with recommendations
        priority_gaps = [
            {
                "market_id": g["market_id"],
                "market_name": f"Market {g['market_id']}",
                "region": region or "national",
                "population_estimate": g["user_count"] * 50,  # Rough multiplier
                "demand_index": g["demand_index"],
                "revenue_potential_kes": g["revenue_potential_kes"],
                "competitor_presence": "unknown",
                "priority_rank": i + 1,
                "recommended_action": "high_potential" if g["demand_index"] > 60 else "monitor",
            }
            for i, g in enumerate(sorted_gaps[:10])
        ]

        # Underserved regions (markets with low coverage relative to demand)
        underserved = []
        for m, d in market_data.items():
            if d["txns"] > 0 and len(d["vendors"]) < 3:
                underserved.append({
                    "market_id": m,
                    "vendor_count": len(d["vendors"]),
                    "transaction_count": d["txns"],
                    "issue": "low_vendor_density",
                })

        # Distribution density
        if market_data:
            densities = [
                d["volume"] / max(len(d["vendors"]), 1)
                for d in market_data.values()
            ]
            avg_density = round(float(np.mean(densities)), 2)
        else:
            avg_density = 0

        # Penetration rate (vendors in covered markets / total potential)
        total_vendors = sum(
            len(d["vendors"]) for d in market_data.values()
        )
        potential_vendors = total_markets * 5  # Assume 5 vendors per market
        penetration = round(total_vendors / max(potential_vendors, 1) * 100, 1)

        # ROI estimate
        investment = len(valid_gap_markets) * 500_000  # KES per market expansion
        annual_return = gap_revenue_potential
        roi = round((annual_return - investment) / max(investment, 1) * 100, 1)

        # Competitor analysis placeholder
        competitor_presence = {
            "total_markets": total_markets,
            "markets_with_competitors": covered_markets,
            "our_coverage_pct": coverage_pct,
        }

        # Apply DP
        dp_gap_revenue = max(0, round(
            self.anonymizer.add_laplace_noise(gap_revenue_potential, sensitivity=100000), 0
        ))

        response = {
            "product": "distribution_gap",
            "version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "data_freshness": datetime.now(timezone.utc).isoformat(),
            "k_anonymity_threshold": settings.K_ANONYMITY_THRESHOLD,
            "quality_score": min(1.0, total_vendors / 50),
            "confidence_level": min(1.0, len(product_txns) / 100),
            "product_category": product_category,
            "product_name": product_name or "all",
            "region": region or "national",
            "time_period": f"{period_start} to {period_end}",
            "coverage": {
                "total_markets_surveyed": total_markets,
                "markets_with_product": covered_markets,
                "markets_without_product": len(valid_gap_markets),
                "coverage_pct": coverage_pct,
                "penetration_rate": penetration,
            },
            "gap_markets": priority_gaps,
            "gap_market_population": sum(
                g.get("population_estimate", 0) for g in priority_gaps
            ),
            "gap_revenue_potential_kes": dp_gap_revenue,
            "demand_without_supply": round(
                np.mean([g["demand_index"] for g in sorted_gaps]) if sorted_gaps else 0, 1
            ),
            "underserved_regions": underserved[:10],
            "underserved_demographics": [],
            "competitor_presence": competitor_presence,
            "competitive_gap_pct": round(100 - coverage_pct, 1),
            "market_share_estimate": None,
            "avg_distribution_cost_per_unit": None,
            "distribution_density": avg_density,
            "recommended_expansion_markets": [
                {"market_id": g["market_id"], "priority": g["priority_rank"]}
                for g in priority_gaps[:5]
            ],
            "estimated_roi_pct": roi,
            "investment_required_kes": investment,
            "users_included": total_vendors,
            "report_type": "one_time",
        }

        await intelligence_cache.set(
            "distribution_gap", response,
            category=product_category, product=product_name,
            region=region, start=str(period_start), end=str(period_end),
        )

        logger.info(
            "distribution_gap_analyzed",
            category=product_category,
            coverage=coverage_pct,
            gaps=len(valid_gap_markets),
        )
        return response
