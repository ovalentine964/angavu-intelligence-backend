"""
Angavu Pulse — MSME Activity Index.

Architecture: arch_backend.md §7.3.3
- Aggregated MSME economic activity metrics
- Transaction velocity, revenue trends, sector growth
- Employment signal estimation
"""
from datetime import UTC, datetime, date, timedelta
from typing import Optional

import numpy as np
import structlog
from sqlalchemy import select, func, and_, distinct
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction import Transaction
from app.models.user import User
from app.models.intelligence import IntelligenceProduct

logger = structlog.get_logger(__name__)


class AngavuPulseService:
    """Angavu Pulse — MSME economic activity index."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_pulse(
        self,
        region: str,
        period: str = "weekly",
        sector: Optional[str] = None,
    ) -> dict:
        """Generate Angavu Pulse for a region."""
        # Try pre-computed first
        result = await self.db.execute(
            select(IntelligenceProduct).where(
                IntelligenceProduct.product_type == "angavu_pulse",
                IntelligenceProduct.region == region,
                IntelligenceProduct.status == "ready",
            ).order_by(IntelligenceProduct.created_at.desc()).limit(1)
        )
        precomputed = result.scalar_one_or_none()
        if precomputed:
            return {
                "product": "angavu-pulse",
                "region": region,
                "period": period,
                "status": "ready",
                **precomputed.data,
            }

        # Compute on-demand
        now = datetime.now(UTC)
        lookback = timedelta(days=7 if period == "weekly" else 30 if period == "monthly" else 90)
        start = now - lookback

        # Active workers
        active_result = await self.db.execute(
            select(func.count(distinct(Transaction.user_id))).where(
                and_(
                    Transaction.location_geohash.like(f"{region}%"),
                    Transaction.created_at >= start,
                )
            )
        )
        active_msme_count = active_result.scalar() or 0

        # Transaction volume
        tx_result = await self.db.execute(
            select(
                func.count().label("tx_count"),
                func.sum(Transaction.amount).label("total_revenue"),
                func.avg(Transaction.amount).label("avg_transaction"),
            ).where(
                and_(
                    Transaction.location_geohash.like(f"{region}%"),
                    Transaction.created_at >= start,
                )
            )
        )
        tx_row = tx_result.one()

        tx_count = int(tx_row.tx_count or 0)
        total_revenue = float(tx_row.total_revenue or 0)
        avg_transaction = float(tx_row.avg_transaction or 0)

        # Transaction velocity (avg tx per worker per period)
        velocity = tx_count / max(1, active_msme_count)

        # Sector breakdown
        sector_result = await self.db.execute(
            select(
                Transaction.product_category,
                func.count().label("count"),
                func.sum(Transaction.amount).label("revenue"),
            ).where(
                and_(
                    Transaction.location_geohash.like(f"{region}%"),
                    Transaction.created_at >= start,
                    Transaction.product_category.isnot(None),
                )
            ).group_by(Transaction.product_category)
        )
        sectors = {}
        for row in sector_result.all():
            if row.product_category:
                sectors[row.product_category] = {
                    "transaction_count": int(row.count),
                    "revenue": float(row.revenue or 0),
                }

        # Growth trajectory (compare current period to previous)
        prev_start = start - lookback
        prev_result = await self.db.execute(
            select(func.count()).where(
                and_(
                    Transaction.location_geohash.like(f"{region}%"),
                    Transaction.created_at >= prev_start,
                    Transaction.created_at < start,
                )
            )
        )
        prev_count = prev_result.scalar() or 0
        if prev_count > 0:
            growth_pct = ((tx_count - prev_count) / prev_count) * 100
        else:
            growth_pct = 100 if tx_count > 0 else 0

        if growth_pct > 10:
            growth_direction = "accelerating"
        elif growth_pct > 0:
            growth_direction = "growing"
        elif growth_pct > -10:
            growth_direction = "stable"
        else:
            growth_direction = "declining"

        # Activity index (0-100, 50 = baseline)
        # Composite of velocity, revenue, and growth
        velocity_score = min(100, velocity * 10)
        revenue_score = min(100, total_revenue / 1000000 * 100)
        growth_score = min(100, max(0, 50 + growth_pct))
        activity_index = round((velocity_score * 0.4 + revenue_score * 0.3 + growth_score * 0.3), 1)

        result_data = {
            "activity_index": activity_index,
            "active_msme_count": active_msme_count,
            "transaction_velocity": round(velocity, 2),
            "total_revenue": round(total_revenue, 2),
            "average_transaction_value": round(avg_transaction, 2),
            "growth_trajectory": {
                "direction": growth_direction,
                "percentage": round(growth_pct, 2),
            },
            "sector_breakdown": sectors,
            "employment_signal": {
                "estimated_workers": active_msme_count,
                "activity_level": "high" if activity_index > 60 else "medium" if activity_index > 40 else "low",
            },
            "generated_at": now.isoformat(),
            "data_points": tx_count,
        }

        return {
            "product": "angavu-pulse",
            "region": region,
            "period": period,
            "status": "ready",
            **result_data,
        }

    async def compare_regions(self, regions: list[str], sector: Optional[str] = None) -> list[dict]:
        """Compare MSME activity across multiple regions."""
        results = []
        for region in regions:
            pulse = await self.generate_pulse(region, sector=sector)
            results.append({
                "region": region,
                "activity_index": pulse.get("activity_index"),
                "active_msme_count": pulse.get("active_msme_count"),
                "growth": pulse.get("growth_trajectory"),
            })
        return results
