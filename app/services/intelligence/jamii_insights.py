"""
Jamii Insights — Financial Inclusion Analytics.

Architecture: arch_backend.md §7.3.4
- Financial inclusion composite index
- Savings, credit access, digital payments, insurance dimensions
- Gap analysis for underserved segments
"""
from datetime import UTC, datetime, timedelta
from typing import Optional

import numpy as np
import structlog
from sqlalchemy import select, func, and_, distinct
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction import Transaction
from app.models.user import User
from app.models.intelligence import IntelligenceProduct

logger = structlog.get_logger(__name__)


class JamiiInsightsService:
    """Jamii Insights — financial inclusion analytics for a region."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_insights(
        self,
        region: str,
        dimension: Optional[str] = None,
    ) -> dict:
        """Generate Jamii Insights for a region."""
        # Try pre-computed first
        result = await self.db.execute(
            select(IntelligenceProduct).where(
                IntelligenceProduct.product_type == "jamii_insights",
                IntelligenceProduct.region == region,
                IntelligenceProduct.status == "ready",
            ).order_by(IntelligenceProduct.created_at.desc()).limit(1)
        )
        precomputed = result.scalar_one_or_none()
        if precomputed:
            return {
                "product": "jamii-insights",
                "region": region,
                "status": "ready",
                **precomputed.data,
            }

        # Compute on-demand
        now = datetime.now(UTC)
        six_months = now - timedelta(days=180)

        # Total workers in region
        workers_result = await self.db.execute(
            select(func.count(distinct(Transaction.user_id))).where(
                Transaction.location_geohash.like(f"{region}%")
            )
        )
        total_workers = workers_result.scalar() or 0

        # Digital payment usage
        digital_result = await self.db.execute(
            select(func.count(distinct(Transaction.user_id))).where(
                and_(
                    Transaction.location_geohash.like(f"{region}%"),
                    Transaction.payment_method.in_(["mpesa", "mobile_money", "card", "bank_transfer"]),
                )
            )
        )
        digital_users = digital_result.scalar() or 0

        # Savings proxy — workers with more income than expenses
        savings_result = await self.db.execute(
            select(
                Transaction.user_id,
                func.sum(
                    func.case(
                        (Transaction.tx_type == "sale", Transaction.amount),
                        else_=-Transaction.amount,
                    )
                ).label("net_income"),
            ).where(
                and_(
                    Transaction.location_geohash.like(f"{region}%"),
                    Transaction.created_at >= six_months,
                )
            ).group_by(Transaction.user_id)
        )
        net_incomes = [float(r.net_income or 0) for r in savings_result.all()]
        savings_rate = len([x for x in net_incomes if x > 0]) / max(1, len(net_incomes))

        # Credit access proxy — workers with purchase transactions (indicating credit/spending capacity)
        credit_result = await self.db.execute(
            select(func.count(distinct(Transaction.user_id))).where(
                and_(
                    Transaction.location_geohash.like(f"{region}%"),
                    Transaction.tx_type == "purchase",
                    Transaction.amount > 1000,
                )
            )
        )
        credit_indicators = credit_result.scalar() or 0
        credit_access = credit_indicators / max(1, total_workers)

        # Business diversity (unique categories per worker)
        diversity_result = await self.db.execute(
            select(
                Transaction.user_id,
                func.count(distinct(Transaction.product_category)).label("cat_count"),
            ).where(
                and_(
                    Transaction.location_geohash.like(f"{region}%"),
                    Transaction.product_category.isnot(None),
                )
            ).group_by(Transaction.user_id)
        )
        diversities = [int(r.cat_count) for r in diversity_result.all()]
        avg_diversity = float(np.mean(diversities)) if diversities else 0

        # Composite inclusion index (0-100)
        digital_score = min(100, (digital_users / max(1, total_workers)) * 100)
        savings_score = min(100, savings_rate * 100)
        credit_score = min(100, credit_access * 100)
        diversity_score = min(100, avg_diversity * 25)

        inclusion_index = round(
            digital_score * 0.3 + savings_score * 0.25 + credit_score * 0.25 + diversity_score * 0.2,
            1,
        )

        dimensions = {
            "digital_payments": {
                "score": round(digital_score, 1),
                "users": digital_users,
                "total_workers": total_workers,
                "penetration": round(digital_users / max(1, total_workers) * 100, 1),
            },
            "savings": {
                "score": round(savings_score, 1),
                "positive_savers": len([x for x in net_incomes if x > 0]),
                "avg_net_income": round(float(np.mean(net_incomes)) if net_incomes else 0, 2),
            },
            "credit_access": {
                "score": round(credit_score, 1),
                "workers_with_credit_activity": credit_indicators,
                "penetration": round(credit_access * 100, 1),
            },
            "business_diversity": {
                "score": round(diversity_score, 1),
                "avg_categories_per_worker": round(avg_diversity, 2),
            },
        }

        result_data = {
            "inclusion_index": inclusion_index,
            "dimensions": dimensions,
            "total_workers": total_workers,
            "underserved_segments": self._identify_underserved(dimensions),
            "opportunity_score": round(max(0, 100 - inclusion_index), 1),
            "gap_analysis": {
                "biggest_gap": min(dimensions.items(), key=lambda x: x[1]["score"])[0],
                "improvement_potential": round(100 - inclusion_index, 1),
            },
            "generated_at": now.isoformat(),
        }

        return {
            "product": "jamii-insights",
            "region": region,
            "status": "ready",
            **result_data,
        }

    def _identify_underserved(self, dimensions: dict) -> list[dict]:
        """Identify underserved segments based on dimension scores."""
        segments = []
        for dim_name, dim_data in dimensions.items():
            if dim_data["score"] < 30:
                segments.append({
                    "dimension": dim_name,
                    "score": dim_data["score"],
                    "priority": "critical",
                })
            elif dim_data["score"] < 50:
                segments.append({
                    "dimension": dim_name,
                    "score": dim_data["score"],
                    "priority": "high",
                })
        return segments
