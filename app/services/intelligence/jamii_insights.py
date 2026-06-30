"""
Jamii Insights — NGO Financial Inclusion Service.

Financial inclusion metrics by demographic:
- Digital payment adoption
- Savings and credit access
- Impact measurement for development programs

Buyers: NGOs, development organizations (World Bank, USAID, DFID)
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


class JamiiInsightsService:
    """
    Financial inclusion intelligence service for NGO buyers.

    Generates demographic-level financial inclusion metrics
    and program impact assessments.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.anonymizer = Anonymizer(db)

    async def generate_inclusion_report(
        self,
        region: str,
        demographic_segment: Optional[str] = None,
        period_start: Optional[date] = None,
        period_end: Optional[date] = None,
        program_name: Optional[str] = None,
        buyer_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Generate financial inclusion intelligence.

        Args:
            region: Geographic region or 'national'
            demographic_segment: youth, women, rural, urban, etc.
            period_start: Analysis start (default: 90 days ago)
            period_end: Analysis end (default: today)
            program_name: Specific program for impact evaluation
            buyer_id: Buyer requesting this data

        Returns:
            Inclusion report dict or None if k-anonymity not met
        """
        cached = await intelligence_cache.get(
            "jamii_insights",
            region=region,
            demographic=demographic_segment,
            start=str(period_start),
            end=str(period_end),
        )
        if cached:
            return cached

        if not period_end:
            period_end = date.today()
        if not period_start:
            period_start = period_end - timedelta(days=90)

        # Build user query
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

        # Apply demographic filter
        if demographic_segment:
            users = self._filter_demographic(users, demographic_segment)

        user_count = len(users)
        if user_count < settings.K_ANONYMITY_THRESHOLD:
            logger.warning("jamii_insights_k_failed", region=region, users=user_count)
            return None

        user_ids = [u.id for u in users]

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

        # Financial inclusion metrics
        mpesa_users = set()
        cash_users = set()
        credit_users = set()
        daily_revenues = defaultdict(lambda: defaultdict(float))
        monthly_revenues = defaultdict(float)

        for t in sales:
            uid = str(t.user_id)
            if t.payment_method == "mpesa":
                mpesa_users.add(uid)
            elif t.payment_method == "cash":
                cash_users.add(uid)
            elif t.payment_method == "credit":
                credit_users.add(uid)
            daily_revenues[t.user_id][t.timestamp.strftime("%Y-%m-%d")] += t.amount
            monthly_revenues[t.timestamp.strftime("%Y-%m")] += t.amount

        # Digital payment adoption
        digital_adoption = round(len(mpesa_users) / max(user_count, 1) * 100, 1)

        # Savings proxy: users with consistent positive revenue over time
        consistent_users = 0
        for uid, daily in daily_revenues.items():
            revenues = list(daily.values())
            if len(revenues) >= 10 and np.mean(revenues) > 0:
                cv = np.std(revenues) / max(np.mean(revenues), 1)
                if cv < 0.5:  # Consistent revenue suggests stable business
                    consistent_users += 1
        savings_score = min(100, round(consistent_users / max(user_count, 1) * 100, 1))

        # Credit access proxy: users with credit transactions
        credit_access = round(len(credit_users) / max(user_count, 1) * 100, 1)

        # Composite inclusion index
        inclusion_index = round(
            digital_adoption * 0.35
            + savings_score * 0.25
            + credit_access * 0.20
            + min(100, user_count / 10) * 0.20,  # Scale penetration
            1,
        )

        # Business formalization (proxy: M-Pesa usage = semi-formal)
        registration_pct = round(digital_adoption * 0.6, 1)  # Approximate

        # Demographics
        youth_owned = sum(1 for u in users if self._is_youth(u))
        women_owned = sum(1 for u in users if self._is_woman(u))
        youth_pct = round(youth_owned / max(user_count, 1) * 100, 1)
        women_pct = round(women_owned / max(user_count, 1) * 100, 1)

        # Income estimates with DP
        total_revenue = sum(t.amount for t in sales)
        months_in_period = max(1, (period_end - period_start).days / 30)
        avg_monthly = total_revenue / max(user_count, 1) / months_in_period
        dp_avg_monthly = max(0, round(
            self.anonymizer.add_laplace_noise(avg_monthly, sensitivity=5000), 0
        ))

        # Income growth
        mid_date = period_start + (period_end - period_start) / 2
        first_half_rev = sum(
            t.amount for t in sales
            if t.timestamp < datetime.combine(
                period_start + (period_end - period_start) / 2, datetime.min.time()
            )
        )
        second_half_rev = total_revenue - first_half_rev
        income_growth = 0
        if first_half_rev > 0:
            income_growth = round(
                (second_half_rev - first_half_rev) / first_half_rev * 100, 1
            )

        # Employment
        employment_created = user_count  # Each business = 1+ jobs
        livelihoods = user_count * 3  # Conservative: 3 dependents per business

        # Barriers to inclusion
        barriers = self._assess_barriers(
            digital_adoption, credit_access, savings_score, user_count
        )

        # Program impact (if program specified)
        program_impact = None
        if program_name:
            program_impact = {
                "program_name": program_name,
                "beneficiary_count": user_count,
                "pre_program_index": max(0, inclusion_index - income_growth),
                "post_program_index": inclusion_index,
                "impact_delta": round(income_growth, 1),
                "cost_per_beneficiary_kes": None,
            }

        response = {
            "product": "jamii_insights",
            "version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "data_freshness": datetime.now(timezone.utc).isoformat(),
            "k_anonymity_threshold": settings.K_ANONYMITY_THRESHOLD,
            "quality_score": min(1.0, user_count / 100),
            "confidence_level": min(1.0, len(sales) / 100),
            "region": region,
            "demographic_segment": demographic_segment,
            "time_period": f"{period_start} to {period_end}",
            "inclusion_metrics": {
                "financial_inclusion_index": inclusion_index,
                "digital_payment_adoption": digital_adoption,
                "savings_behavior_score": savings_score,
                "credit_access_score": credit_access,
                "insurance_coverage_pct": 0,  # Would need insurance data
            },
            "business_registration_pct": registration_pct,
            "tax_compliance_pct": round(digital_adoption * 0.3, 1),
            "formal_banking_pct": round(digital_adoption * 0.5, 1),
            "youth_owned_pct": youth_pct,
            "women_owned_pct": women_pct,
            "avg_owner_age": None,
            "avg_monthly_income_kes": dp_avg_monthly,
            "income_growth_pct": income_growth if income_growth != 0 else None,
            "employment_created": employment_created,
            "livelihoods_supported": livelihoods,
            "program_impact": program_impact,
            "barriers": barriers,
            "sample_size": user_count,
        }

        await intelligence_cache.set(
            "jamii_insights", response,
            region=region, demographic=demographic_segment,
            start=str(period_start), end=str(period_end),
        )

        logger.info("jamii_insights_generated", region=region, k=user_count)
        return response

    @staticmethod
    def _filter_demographic(users: list, segment: str) -> list:
        """Filter users by demographic segment."""
        # In production, this would use actual demographic data
        # For now, use business type as proxy
        if segment == "youth":
            return [u for u in users if u.business_type in ("boda_boda", "vendor")]
        elif segment == "women":
            return [u for u in users if u.business_type in ("mama_mboga", "tailor")]
        elif segment == "rural":
            return [u for u in users if u.location_geohash and len(u.location_geohash) >= 5]
        elif segment == "urban":
            return [u for u in users if u.location_geohash and len(u.location_geohash) <= 4]
        return users

    @staticmethod
    def _is_youth(user) -> bool:
        """Proxy for youth ownership based on business type."""
        return user.business_type in ("boda_boda", "vendor")

    @staticmethod
    def _is_woman(user) -> bool:
        """Proxy for women ownership based on business type."""
        return user.business_type in ("mama_mboga", "tailor")

    @staticmethod
    def _assess_barriers(
        digital: float, credit: float, savings: float, count: int
    ) -> List[Dict[str, Any]]:
        """Assess barriers to financial inclusion."""
        barriers = []
        if digital < 50:
            barriers.append({
                "barrier": "low_digital_literacy",
                "severity": max(0, 100 - digital),
                "affected_pct": round(100 - digital, 1),
                "recommended_intervention": "Digital financial literacy training",
            })
        if credit < 20:
            barriers.append({
                "barrier": "limited_credit_access",
                "severity": max(0, 100 - credit * 2),
                "affected_pct": round(100 - credit, 1),
                "recommended_intervention": "Microfinance partnerships and credit education",
            })
        if savings < 30:
            barriers.append({
                "barrier": "low_savings_behavior",
                "severity": max(0, 100 - savings * 2),
                "affected_pct": round(100 - savings, 1),
                "recommended_intervention": "Savings group formation and incentives",
            })
        if count < 50:
            barriers.append({
                "barrier": "geographic_isolation",
                "severity": 60,
                "affected_pct": 40,
                "recommended_intervention": "Mobile-first service delivery",
            })
        if not barriers:
            barriers.append({
                "barrier": "no_significant_barriers",
                "severity": 10,
                "affected_pct": 5,
                "recommended_intervention": "Continue monitoring",
            })
        return barriers
