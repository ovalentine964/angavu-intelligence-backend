"""
Biashara Pulse — Government MSME Activity Index Service.

Economic activity heatmaps by county/sub-county:
- Business formation/destruction rates
- MSME activity indices (0-100)
- Sector breakdown and employment estimates

Buyers: Government (KNBS, CBK, county governments)
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

# Kenya county codes
KENYA_COUNTIES = {
    "001": "Mombasa", "002": "Kwale", "003": "Kilifi", "004": "Tana River",
    "005": "Lamu", "006": "Taita Taveta", "007": "Garissa", "008": "Wajir",
    "009": "Mandera", "010": "Marsabit", "011": "Isiolo", "012": "Meru",
    "013": "Tharaka Nithi", "014": "Embu", "015": "Kitui", "016": "Machakos",
    "017": "Makueni", "018": "Nyandarua", "019": "Nyeri", "020": "Kirinyaga",
    "021": "Murang'a", "022": "Kiambu", "023": "Turkana", "024": "West Pokot",
    "025": "Samburu", "026": "Trans Nzoia", "027": "Uasin Gishu",
    "028": "Elgeyo Marakwet", "029": "Nandi", "030": "Baringo", "031": "Laikipia",
    "032": "Nakuru", "033": "Narok", "034": "Kajiado", "035": "Kericho",
    "036": "Bomet", "037": "Kakamega", "038": "Vihiga", "039": "Bungoma",
    "040": "Busia", "041": "Siaya", "042": "Kisumu", "043": "Homa Bay",
    "044": "Migori", "045": "Kisii", "046": "Nyamira", "047": "Nairobi",
}


class BiasharaPulseService:
    """
    Government MSME Activity Index service.

    Generates economic activity intelligence for government buyers.
    Produces county-level and sub-county level activity indices.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.anonymizer = Anonymizer(db)

    async def generate_activity_index(
        self,
        region: str,
        period_start: Optional[date] = None,
        period_end: Optional[date] = None,
        buyer_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Generate MSME activity index for a region.

        Args:
            region: County code (e.g., '047' for Nairobi) or 'national'
            period_start: Analysis start (default: 30 days ago)
            period_end: Analysis end (default: today)
            buyer_id: Buyer requesting this data

        Returns:
            Activity index dict or None if k-anonymity not met
        """
        # Check cache
        cached = await intelligence_cache.get(
            "biashara_pulse",
            region=region,
            start=str(period_start),
            end=str(period_end),
        )
        if cached:
            return cached

        if not period_end:
            period_end = date.today()
        if not period_start:
            period_start = period_end - timedelta(days=30)

        region_type = self._determine_region_type(region)
        county_name = KENYA_COUNTIES.get(region, region)

        # Get users in region
        user_query = select(User).where(
            and_(
                User.is_active == True,
                User.consent_data_sharing == True,
            )
        )
        if region != "national":
            user_query = user_query.where(
                User.location_geohash.like(f"{region}%")
            )

        result = await self.db.execute(user_query)
        users = result.scalars().all()
        user_count = len(users)

        if user_count < settings.K_ANONYMITY_THRESHOLD:
            logger.warning("biashara_pulse_k_failed", region=region, users=user_count)
            return None

        user_ids = [u.id for u in users]
        user_map = {u.id: u for u in users}

        # Get transactions
        txn_query = select(Transaction).where(
            and_(
                Transaction.user_id.in_(user_ids),
                Transaction.timestamp >= datetime.combine(period_start, datetime.min.time()),
                Transaction.timestamp <= datetime.combine(period_end, datetime.max.time()),
            )
        )
        result = await self.db.execute(txn_query)
        transactions = result.scalars().all()

        sales = [t for t in transactions if t.transaction_type == "SALE"]
        total_revenue = sum(t.amount for t in sales)
        days_in_period = (period_end - period_start).days or 1

        # Activity index (0-100)
        txn_per_day = len(sales) / days_in_period
        activity_index = min(100, round(txn_per_day * 2, 1))

        # Growth index — compare to previous period
        prev_start = period_start - timedelta(days=days_in_period)
        prev_end = period_start
        prev_txn_query = select(Transaction).where(
            and_(
                Transaction.user_id.in_(user_ids),
                Transaction.timestamp >= datetime.combine(prev_start, datetime.min.time()),
                Transaction.timestamp < datetime.combine(prev_end, datetime.min.time()),
                Transaction.transaction_type == "SALE",
            )
        )
        prev_result = await self.db.execute(prev_txn_query)
        prev_sales = prev_result.scalars().all()
        prev_revenue = sum(t.amount for t in prev_sales)

        if prev_revenue > 0:
            growth_pct = (total_revenue - prev_revenue) / prev_revenue * 100
            growth_index = min(100, max(0, 50 + growth_pct))
        else:
            growth_index = 50
            growth_pct = 0

        # Sector breakdown
        sector_counts = defaultdict(int)
        sector_revenue = defaultdict(float)
        for t in sales:
            cat = t.item_category or "other"
            sector_counts[cat] += 1
            sector_revenue[cat] += t.amount

        sector_breakdown = []
        for cat, rev in sorted(sector_revenue.items(), key=lambda x: x[1], reverse=True):
            sector_breakdown.append({
                "sector": cat,
                "activity_share_pct": round(sector_counts[cat] / max(len(sales), 1) * 100, 1),
                "revenue_share_pct": round(rev / max(total_revenue, 1) * 100, 1),
                "business_count": len(set(
                    t.user_id for t in sales if (t.item_category or "other") == cat
                )),
                "trend": "stable",  # Would need previous period per-sector
            })

        top_sectors = [s["sector"] for s in sector_breakdown[:5]]

        # M-Pesa penetration
        mpesa_count = sum(1 for t in sales if t.payment_method == "mpesa")
        mpesa_pct = round(mpesa_count / max(len(sales), 1) * 100, 1)

        # Operating days per week
        daily_active = defaultdict(set)
        for t in sales:
            dow = t.timestamp.strftime("%a")
            day = t.timestamp.strftime("%Y-%m-%d")
            daily_active[dow].add(t.user_id)

        avg_operating_days = len(daily_active) if daily_active else 0

        # Employment estimate (rough: 1-2 per business)
        estimated_employment = user_count * 2  # Conservative estimate

        # Business formation (simplified — new users in period)
        new_users_query = select(func.count(User.id)).where(
            and_(
                User.created_at >= datetime.combine(period_start, datetime.min.time()),
                User.created_at <= datetime.combine(period_end, datetime.max.time()),
                User.consent_data_sharing == True,
            )
        )
        if region != "national":
            new_users_query = new_users_query.where(
                User.location_geohash.like(f"{region}%")
            )
        new_result = await self.db.execute(new_users_query)
        new_businesses = new_result.scalar() or 0

        # Avg transaction value with DP
        avg_txn = total_revenue / max(len(sales), 1)
        dp_avg_txn = max(0, round(self.anonymizer.add_laplace_noise(avg_txn, sensitivity=200), 2))
        dp_avg_daily_rev = max(0, round(
            self.anonymizer.add_laplace_noise(
                total_revenue / max(days_in_period, 1), sensitivity=500
            ), 2
        ))

        # County rank (placeholder — would need all counties)
        county_rank = None
        vs_national = None

        response = {
            "product": "biashara_pulse",
            "version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "data_freshness": datetime.now(timezone.utc).isoformat(),
            "k_anonymity_threshold": settings.K_ANONYMITY_THRESHOLD,
            "quality_score": min(1.0, user_count / 100),
            "confidence_level": min(1.0, len(sales) / 100),
            "region": region,
            "region_type": region_type,
            "time_period": f"{period_start} to {period_end}",
            "activity_index": activity_index,
            "growth_index": round(growth_index, 1),
            "formalization_index": None,
            "estimated_businesses": user_count,
            "active_businesses": user_count,
            "business_formation": {
                "new_businesses_est": new_businesses,
                "closed_businesses_est": 0,  # Would need inactive user tracking
                "net_change": new_businesses,
                "formation_rate": round(new_businesses / max(user_count, 1) * 1000, 1),
                "survival_rate": None,
            },
            "total_transactions": len(sales),
            "total_volume_kes": round(total_revenue, 2),
            "avg_transaction_value": dp_avg_txn,
            "avg_daily_revenue_per_business": dp_avg_daily_rev,
            "sector_breakdown": sector_breakdown,
            "top_sectors": top_sectors,
            "mpesa_penetration_pct": mpesa_pct,
            "digital_payment_adoption": mpesa_pct,
            "avg_operating_hours": 10.0,  # Default estimate
            "avg_operating_days_per_week": avg_operating_days,
            "estimated_employment": estimated_employment,
            "employment_per_business": 2.0,
            "vs_previous_period_pct": round(growth_pct, 1) if prev_revenue > 0 else None,
            "vs_national_avg_pct": vs_national,
            "county_rank": county_rank,
            "users_included": user_count,
        }

        await intelligence_cache.set("biashara_pulse", response, region=region, start=str(period_start), end=str(period_end))

        logger.info("biashara_pulse_generated", region=region, k=user_count, sales=len(sales))
        return response

    @staticmethod
    def _determine_region_type(region: str) -> str:
        if region == "national":
            return "national"
        elif len(region) <= 3:
            return "county"
        elif len(region) <= 5:
            return "sub_county"
        else:
            return "ward"
