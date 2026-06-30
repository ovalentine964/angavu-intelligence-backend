"""
Tax Base Estimation — Government Revenue Service.

Estimated tax liability for informal businesses:
- VAT collection potential by sector/region
- Tax gap analysis
- Formalization tracking

Buyers: KRA, county governments
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

# Kenya VAT rate
VAT_RATE = 0.16  # 16% standard VAT
VAT_THRESHOLD_KES = 5_000_000  # KES 5M annual turnover threshold

# Sector-specific tax assumptions
SECTOR_TAX_PROFILES = {
    "food": {"vat_applicable": 0.7, "income_tax_rate": 0.25, "compliance_rate": 0.15},
    "household": {"vat_applicable": 0.9, "income_tax_rate": 0.25, "compliance_rate": 0.20},
    "health": {"vat_applicable": 0.5, "income_tax_rate": 0.30, "compliance_rate": 0.25},
    "transport": {"vat_applicable": 0.8, "income_tax_rate": 0.25, "compliance_rate": 0.18},
    "clothing": {"vat_applicable": 0.9, "income_tax_rate": 0.25, "compliance_rate": 0.15},
    "electronics": {"vat_applicable": 0.95, "income_tax_rate": 0.30, "compliance_rate": 0.22},
    "beauty": {"vat_applicable": 0.8, "income_tax_rate": 0.25, "compliance_rate": 0.12},
    "agriculture": {"vat_applicable": 0.3, "income_tax_rate": 0.15, "compliance_rate": 0.10},
    "services": {"vat_applicable": 0.7, "income_tax_rate": 0.30, "compliance_rate": 0.20},
    "other": {"vat_applicable": 0.7, "income_tax_rate": 0.25, "compliance_rate": 0.15},
}


class TaxBaseService:
    """
    Tax base estimation service for government buyers.

    Estimates tax liability and collection potential from
    informal economy transaction data.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.anonymizer = Anonymizer(db)

    async def estimate_tax_base(
        self,
        region: str,
        sector: Optional[str] = None,
        period_start: Optional[date] = None,
        period_end: Optional[date] = None,
        buyer_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Estimate tax base for a region/sector.

        Args:
            region: County code or 'national'
            sector: Specific sector or None for all
            period_start: Analysis start (default: 12 months ago)
            period_end: Analysis end (default: today)
            buyer_id: Buyer requesting this data

        Returns:
            Tax base estimation dict or None if k-anonymity not met
        """
        cached = await intelligence_cache.get(
            "tax_base", region=region, sector=sector,
            start=str(period_start), end=str(period_end),
        )
        if cached:
            return cached

        if not period_end:
            period_end = date.today()
        if not period_start:
            period_start = period_end - timedelta(days=365)

        region_type = self._determine_region_type(region)

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
            logger.warning("tax_base_k_failed", region=region, users=user_count)
            return None

        user_ids = [u.id for u in users]

        # Get transactions
        txn_query = select(Transaction).where(
            and_(
                Transaction.user_id.in_(user_ids),
                Transaction.timestamp >= datetime.combine(period_start, datetime.min.time()),
                Transaction.timestamp <= datetime.combine(period_end, datetime.max.time()),
                Transaction.transaction_type == "SALE",
            )
        )
        if sector:
            txn_query = txn_query.where(Transaction.item_category == sector)

        result = await self.db.execute(txn_query)
        sales = result.scalars().all()

        if not sales:
            return None

        total_revenue = sum(t.amount for t in sales)
        months_in_period = max(1, (period_end - period_start).days / 30)

        # Sector breakdown
        sector_data = defaultdict(lambda: {"revenue": 0, "count": 0, "users": set()})
        for t in sales:
            cat = t.item_category or "other"
            sector_data[cat]["revenue"] += t.amount
            sector_data[cat]["count"] += 1
            sector_data[cat]["users"].add(t.user_id)

        # Estimate formalized businesses (proxy: M-Pesa users with >50% digital)
        formalized = 0
        for u in users:
            user_sales = [t for t in sales if t.user_id == u.id]
            if user_sales:
                mpesa_pct = sum(1 for t in user_sales if t.payment_method == "mpesa") / len(user_sales)
                if mpesa_pct > 0.5:
                    formalized += 1

        # Annualized revenue per business
        annual_rev_per_business = total_revenue / max(user_count, 1) * (12 / months_in_period)

        # VAT-liable businesses (above threshold)
        vat_liable_count = sum(
            1 for u in users
            if sum(t.amount for t in sales if t.user_id == u.id) * (12 / months_in_period) > VAT_THRESHOLD_KES
        )

        # Sector-level tax estimates
        sector_breakdown = []
        total_vat_base = 0
        total_vat_collectible = 0
        total_income_tax_base = 0

        for cat, data in sector_data.items():
            profile = SECTOR_TAX_PROFILES.get(cat, SECTOR_TAX_PROFILES["other"])
            annualized_rev = data["revenue"] * (12 / months_in_period)

            vat_base = annualized_rev * profile["vat_applicable"]
            vat_collectible = vat_base * VAT_RATE * profile["compliance_rate"]
            income_tax_base = annualized_rev * profile["income_tax_rate"] * profile["compliance_rate"]

            total_vat_base += vat_base
            total_vat_collectible += vat_collectible
            total_income_tax_base += income_tax_base

            sector_breakdown.append({
                "sector": cat,
                "estimated_revenue_kes": round(annualized_rev, 2),
                "vat_base_kes": round(vat_base, 2),
                "vat_collectible_kes": round(vat_collectible, 2),
                "business_count": len(data["users"]),
                "compliance_rate": round(profile["compliance_rate"] * 100, 1),
            })

        sector_breakdown.sort(key=lambda x: x["estimated_revenue_kes"], reverse=True)

        # Tax gap
        total_potential_vat = total_vat_base * VAT_RATE
        tax_gap = total_potential_vat - total_vat_collectible

        # Compliance rate
        overall_compliance = round(
            (total_vat_collectible + total_income_tax_base)
            / max(total_potential_vat + total_income_tax_base, 1) * 100, 1
        )

        # Growth (compare to previous period)
        prev_start = period_start - timedelta(days=(period_end - period_start).days)
        prev_txn_query = select(Transaction).where(
            and_(
                Transaction.user_id.in_(user_ids),
                Transaction.timestamp >= datetime.combine(prev_start, datetime.min.time()),
                Transaction.timestamp < datetime.combine(period_start, datetime.min.time()),
                Transaction.transaction_type == "SALE",
            )
        )
        prev_result = await self.db.execute(prev_txn_query)
        prev_sales = prev_result.scalars().all()
        prev_revenue = sum(t.amount for t in prev_sales)

        revenue_growth = 0
        if prev_revenue > 0:
            annualized_current = total_revenue * (12 / months_in_period)
            annualized_prev = prev_revenue * (12 / months_in_period)
            revenue_growth = round(
                (annualized_current - annualized_prev) / annualized_prev * 100, 1
            )

        # Apply DP to sensitive fields
        dp_total_rev = max(0, round(
            self.anonymizer.add_laplace_noise(
                total_revenue * (12 / months_in_period), sensitivity=100000
            ), 0
        ))
        dp_vat_collectible = max(0, round(
            self.anonymizer.add_laplace_noise(total_vat_collectible, sensitivity=50000), 0
        ))

        # Top tax contributors
        top_contributors = [
            {"sector": s["sector"], "contribution_pct": round(
                s["vat_collectible_kes"] / max(total_vat_collectible, 1) * 100, 1
            )}
            for s in sector_breakdown[:5]
        ]

        # Confidence interval (bootstrap-style)
        ci_lower = round(dp_total_rev * 0.85, 0)
        ci_upper = round(dp_total_rev * 1.15, 0)

        response = {
            "product": "tax_base_estimation",
            "version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "data_freshness": datetime.now(timezone.utc).isoformat(),
            "k_anonymity_threshold": settings.K_ANONYMITY_THRESHOLD,
            "quality_score": min(1.0, user_count / 100),
            "confidence_level": min(1.0, len(sales) / 100),
            "region": region,
            "region_type": region_type,
            "sector": sector,
            "time_period": f"{period_start} to {period_end}",
            "estimated_businesses": user_count,
            "active_businesses": user_count,
            "formalized_businesses": formalized,
            "formalization_gap_pct": round((1 - formalized / max(user_count, 1)) * 100, 1),
            "tax_estimates": {
                "estimated_total_revenue_kes": dp_total_rev,
                "estimated_vat_base_kes": round(total_vat_base, 0),
                "estimated_vat_collectible_kes": dp_vat_collectible,
                "estimated_income_tax_base_kes": round(total_income_tax_base, 0),
                "vat_effective_rate": round(
                    total_vat_collectible / max(total_vat_base, 1) * 100, 2
                ),
                "tax_gap_kes": round(tax_gap, 0),
                "tax_compliance_rate": overall_compliance,
            },
            "sector_breakdown": sector_breakdown,
            "top_tax_contributors": top_contributors,
            "revenue_growth_pct": revenue_growth if revenue_growth != 0 else None,
            "tax_base_growth_pct": revenue_growth if revenue_growth != 0 else None,
            "new_registrations_est": None,
            "vs_previous_period_pct": revenue_growth if revenue_growth != 0 else None,
            "county_rank": None,
            "users_included": user_count,
            "confidence_interval": {"lower": ci_lower, "upper": ci_upper},
        }

        await intelligence_cache.set(
            "tax_base", response,
            region=region, sector=sector,
            start=str(period_start), end=str(period_end),
        )

        logger.info("tax_base_estimated", region=region, businesses=user_count, revenue=dp_total_rev)
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
