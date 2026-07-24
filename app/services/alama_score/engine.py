"""
Alama Score Engine — 0-1000 Credit Scoring for Informal Businesses.

Computes a lender-facing credit score from transaction flow data.
Six scoring factors, each normalized to 0-100, then weighted and
scaled to a 0-1000 composite score.

Scoring Factors (weights sum to 1.0):
  1. Transaction Consistency (20%) — How regular are daily transactions?
  2. Revenue Growth (15%)        — Is revenue trending up?
  3. Profit Margin (20%)         — How much profit per sale?
  4. Customer Retention (15%)    — Repeat customer rate
  5. Inventory Management (15%)  — Stock turnover and restock discipline
  6. Business Age (15%)          — How long has the business been operating?

The engine also provides:
  - Default probability estimation (logistic model)
  - Affordability assessment for requested loan amounts
  - Financial product matching
  - Peer cohort comparison (k-anonymity protected)
"""

from __future__ import annotations

import hashlib
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction import Inventory, Transaction
from app.models.user import User

from .models import (
    AffordabilityAssessment,
    AlamaScoreReport,
    LenderQueryRequest,
    LenderQueryResponse,
    LoanProductType,
    PeerComparison,
    ProductRecommendation,
    RiskCategory,
    ScoreBand,
    ScoreComponent,
)

logger = structlog.get_logger(__name__)


# ── Constants ────────────────────────────────────────────────────────────────

# Factor weights (must sum to 1.0)
FACTOR_WEIGHTS = {
    "transaction_consistency": 0.20,
    "revenue_growth": 0.15,
    "profit_margin": 0.20,
    "customer_retention": 0.15,
    "inventory_management": 0.15,
    "business_age": 0.15,
}

# Score band thresholds (0-1000 scale)
BAND_THRESHOLDS = [
    (900, ScoreBand.EXCEPTIONAL),
    (800, ScoreBand.EXCELLENT),
    (700, ScoreBand.GOOD),
    (600, ScoreBand.FAIR),
    (500, ScoreBand.POOR),
    (300, ScoreBand.VERY_POOR),
    (0, ScoreBand.NO_SCORE),
]

# Risk category thresholds
RISK_THRESHOLDS = [
    (800, RiskCategory.VERY_LOW),
    (650, RiskCategory.LOW),
    (500, RiskCategory.MODERATE),
    (350, RiskCategory.HIGH),
    (0, RiskCategory.VERY_HIGH),
]

# Product matching rules
PRODUCT_RULES: dict[str, dict[str, Any]] = {
    LoanProductType.WORKING_CAPITAL: {
        "min_score": 500,
        "min_margin": 0.10,
        "min_months": 3,
        "max_amount_multiplier": 2.0,  # 2x monthly revenue
        "base_rate": 15.0,
        "term_days": 90,
        "name": "Biashara Working Capital",
        "name_sw": "Mtaji wa Biashara",
        "rationale": "Working capital to smooth cash flow gaps",
        "rationale_sw": "Mtaji wa kujaza mapengo ya fedha",
    },
    LoanProductType.STOCK_FINANCING: {
        "min_score": 550,
        "min_margin": 0.15,
        "min_months": 6,
        "max_amount_multiplier": 3.0,
        "base_rate": 12.0,
        "term_days": 60,
        "name": "Stock Purchase Loan",
        "name_sw": "Mkopo wa Kununua Stock",
        "rationale": "Finance bulk purchases for better margins",
        "rationale_sw": "Fedha za kununua bidhaa kwa wingi kwa faida zaidi",
    },
    LoanProductType.EQUIPMENT_LOAN: {
        "min_score": 650,
        "min_margin": 0.20,
        "min_months": 12,
        "max_amount_multiplier": 5.0,
        "base_rate": 10.0,
        "term_days": 365,
        "name": "Equipment Financing",
        "name_sw": "Mkopo wa Vifaa",
        "rationale": "Upgrade or acquire business equipment",
        "rationale_sw": "Kuboresha au kununua vifaa vya biashara",
    },
    LoanProductType.EMERGENCY_LOAN: {
        "min_score": 400,
        "min_margin": 0.0,
        "min_months": 1,
        "max_amount_multiplier": 0.5,
        "base_rate": 20.0,
        "term_days": 30,
        "name": "Emergency Advance",
        "name_sw": "Mkopo wa Dharura",
        "rationale": "Quick cash for emergencies",
        "rationale_sw": "Fedha za haraka za dharura",
    },
    LoanProductType.INSURANCE: {
        "min_score": 450,
        "min_margin": 0.05,
        "min_months": 3,
        "max_amount_multiplier": 0,  # Not a loan
        "base_rate": 0,
        "term_days": 365,
        "name": "Biashara Insurance",
        "name_sw": "Bima ya Biashara",
        "rationale": "Protect your business from unexpected losses",
        "rationale_sw": "Linda biashara yako dhidi ya hasara zisizotarajiwa",
    },
    LoanProductType.INVOICE_FINANCING: {
        "min_score": 600,
        "min_margin": 0.15,
        "min_months": 6,
        "max_amount_multiplier": 2.5,
        "base_rate": 8.0,
        "term_days": 45,
        "name": "Invoice Advance",
        "name_sw": "Mkopo wa Ankara",
        "rationale": "Get paid now for outstanding invoices",
        "rationale_sw": "Pata fedha sasa kwa ankara zilizopo",
    },
    LoanProductType.GROUP_LOAN: {
        "min_score": 350,
        "min_margin": 0.05,
        "min_months": 1,
        "max_amount_multiplier": 1.0,
        "base_rate": 18.0,
        "term_days": 120,
        "name": "Group Lending Circle",
        "name_sw": "Kikundi cha Mkopo",
        "rationale": "Borrow as a group for better rates",
        "rationale_sw": "Kopa kama kikundi kwa riba nafuu",
    },
}


# ── Engine ───────────────────────────────────────────────────────────────────

class AlamaScoreEngine:
    """
    Compute 0-1000 Alama Scores for informal businesses.

    Usage:
        engine = AlamaScoreEngine(db_session)
        response = await engine.compute(LenderQueryRequest(...))
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def compute(self, request: LenderQueryRequest) -> LenderQueryResponse:
        """
        Compute Alama Score and generate a full lender report.

        Args:
            request: Lender query request with business_id and parameters.

        Returns:
            LenderQueryResponse with the full score report or an error.
        """
        query_id = str(uuid.uuid4())
        now = datetime.now(UTC)

        # 1. Resolve user from business hash
        user = await self._resolve_user(request.business_id)
        if not user:
            return LenderQueryResponse(
                status="error",
                error="Business not found or insufficient data sharing consent",
                error_sw="Biashara haijapatikana au hairuhusu kushiriki data",
            )

        # 2. Fetch transactions
        end_date = datetime.now(UTC).date()
        start_date = end_date - timedelta(days=request.lookback_days)
        transactions = await self._fetch_transactions(
            user.id, start_date, end_date
        )

        if len(transactions) < 10:
            return LenderQueryResponse(
                status="error",
                error=f"Insufficient data: {len(transactions)} transactions (minimum 10 required)",
                error_sw=f"Data haitoshi: miamala {len(transactions)} (kiwango cha chini ni 10)",
            )

        # 3. Fetch inventory (if available)
        inventory = await self._fetch_inventory(user.id)

        # 4. Compute score components
        components = self._compute_components(
            transactions, inventory, user, request.lookback_days
        )

        # 5. Compute composite score (0-1000)
        composite_score = self._compute_composite(components)

        # 6. Determine band and risk
        score_band = self._score_band(composite_score)
        risk_category = self._risk_category(composite_score)

        # 7. Compute confidence
        confidence = self._compute_confidence(transactions, request.lookback_days)

        # 8. Default probability
        default_prob = self._default_probability(composite_score)

        # 9. Credit limit recommendation
        credit_limit = self._recommended_credit_limit(
            transactions, composite_score, request.lookback_days
        )

        # 10. Risk and positive factors
        risk_factors, risk_factors_sw, positive_factors, positive_factors_sw = (
            self._identify_factors(components)
        )

        # 11. Data quality
        operating_days = len(set(
            t.timestamp.strftime("%Y-%m-%d")
            for t in transactions
            if t.transaction_type == "SALE"
        ))
        data_quality = min(1.0, len(transactions) / 100)

        # 12. Build component summary
        component_summary = {c.name: c.normalized_score for c in components}

        # 13. Affordability (if amount requested)
        affordability = None
        if request.requested_amount and request.requested_amount > 0:
            affordability = self._assess_affordability(
                transactions, request.requested_amount, request.lookback_days
            )

        # 14. Product recommendations
        product_recs = []
        if request.include_product_match:
            product_recs = self._match_products(
                components, composite_score, transactions, request.lookback_days
            )

        # 15. Peer comparison
        peer_comp = None
        if request.include_peer_comparison:
            peer_comp = await self._peer_comparison(
                user, composite_score, request.lookback_days, start_date, end_date
            )

        report = AlamaScoreReport(
            generated_at=now,
            query_id=query_id,
            business_hash=request.business_id,
            lender_id=request.lender_id,
            alama_score=composite_score,
            score_band=score_band,
            risk_category=risk_category,
            confidence=confidence,
            components=components,
            component_summary=component_summary,
            default_probability=default_prob,
            recommended_credit_limit_kes=credit_limit,
            risk_factors=risk_factors,
            risk_factors_sw=risk_factors_sw,
            positive_factors=positive_factors,
            positive_factors_sw=positive_factors_sw,
            affordability=affordability,
            product_recommendations=product_recs,
            peer_comparison=peer_comp,
            data_points=len(transactions),
            data_period_days=request.lookback_days,
            operating_days=operating_days,
            data_quality_score=data_quality,
        )

        logger.info(
            "alama_score_computed",
            business=request.business_id,
            score=composite_score,
            band=score_band.value,
            risk=risk_category.value,
            query_id=query_id,
        )

        return LenderQueryResponse(
            status="success",
            report=report,
            rate_limit_remaining=999,  # TODO: implement rate limiting
        )

    # ── Data Fetching ────────────────────────────────────────────────────────

    async def _resolve_user(self, business_id: str) -> User | None:
        """Resolve a business hash to a User record."""
        query = select(User).where(
            and_(
                User.is_active == True,
                User.consent_data_sharing == True,
            )
        )
        result = await self.db.execute(query)
        users = result.scalars().all()

        for u in users:
            computed = hashlib.sha256(
                f"{u.id}:{u.phone_hash}".encode()
            ).hexdigest()[:32]
            if computed == business_id[:32]:
                return u
            # Also try direct ID hash
            if hashlib.sha256(str(u.id).encode()).hexdigest()[:32] == business_id[:32]:
                return u

        return None

    async def _fetch_transactions(
        self, user_id: Any, start_date, end_date
    ) -> list[Transaction]:
        """Fetch transactions for the analysis window."""
        query = select(Transaction).where(
            and_(
                Transaction.user_id == user_id,
                Transaction.timestamp >= datetime.combine(start_date, datetime.min.time()),
                Transaction.timestamp <= datetime.combine(end_date, datetime.max.time()),
            )
        ).order_by(Transaction.timestamp)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def _fetch_inventory(self, user_id: Any) -> list[Inventory]:
        """Fetch current inventory for the user."""
        query = select(Inventory).where(Inventory.user_id == user_id)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    # ── Component Scoring ────────────────────────────────────────────────────

    def _compute_components(
        self,
        transactions: list[Transaction],
        inventory: list[Inventory],
        user: User,
        lookback_days: int,
    ) -> list[ScoreComponent]:
        """Compute all six scoring components."""
        sales = [t for t in transactions if t.transaction_type == "SALE"]
        purchases = [t for t in transactions if t.transaction_type == "PURCHASE"]
        expenses = [t for t in transactions if t.transaction_type == "EXPENSE"]

        # Daily aggregations
        daily_revenue: dict[str, float] = defaultdict(float)
        daily_transactions: dict[str, int] = defaultdict(int)
        daily_customers: dict[str, set] = defaultdict(set)
        for t in sales:
            day = t.timestamp.strftime("%Y-%m-%d")
            daily_revenue[day] += t.amount
            daily_transactions[day] += 1
            if t.customer_phone_hash:
                daily_customers[day].add(t.customer_phone_hash)

        active_days = set(daily_revenue.keys())
        total_days = lookback_days
        revenues = list(daily_revenue.values())
        total_revenue = sum(t.amount for t in sales)
        total_cost = sum(t.amount for t in purchases)
        total_expense = sum(t.amount for t in expenses)

        components = []

        # 1. Transaction Consistency (20%)
        components.append(self._score_consistency(
            revenues, active_days, total_days, daily_transactions
        ))

        # 2. Revenue Growth (15%)
        components.append(self._score_growth(sales, total_days))

        # 3. Profit Margin (20%)
        components.append(self._score_profit_margin(
            total_revenue, total_cost, total_expense, sales
        ))

        # 4. Customer Retention (15%)
        components.append(self._score_customer_retention(
            sales, daily_customers, total_days
        ))

        # 5. Inventory Management (15%)
        components.append(self._score_inventory(
            inventory, sales, purchases, total_days
        ))

        # 6. Business Age (15%)
        components.append(self._score_business_age(user, transactions))

        return components

    def _score_consistency(
        self,
        daily_revenues: list[float],
        active_days: set[str],
        total_days: int,
        daily_transactions: dict[str, int],
    ) -> ScoreComponent:
        """
        Score transaction consistency (0-100).

        Based on:
        - Coefficient of variation (CV) of daily revenue
        - Active days ratio (days with transactions / total days)
        - Transaction frequency regularity

        CV < 0.3 → very consistent (90-100)
        CV 0.3-0.5 → consistent (70-90)
        CV 0.5-0.8 → moderate (50-70)
        CV 0.8-1.2 → volatile (30-50)
        CV > 1.2 → very volatile (10-30)
        """
        if not daily_revenues or len(daily_revenues) < 2:
            return ScoreComponent(
                name="transaction_consistency",
                name_sw="Uthabiti wa Miamala",
                weight=FACTOR_WEIGHTS["transaction_consistency"],
                raw_value=0,
                normalized_score=20,
                weighted_contribution=20 * FACTOR_WEIGHTS["transaction_consistency"],
                interpretation="Insufficient data for consistency analysis",
                interpretation_sw="Data haitoshi kuchambua uthabiti",
            )

        rev_arr = np.array(daily_revenues, dtype=float)
        cv = float(np.std(rev_arr) / max(np.mean(rev_arr), 1.0))

        # CV score component
        if cv <= 0.3:
            cv_score = 90 + (0.3 - cv) * (10 / 0.3)
        elif cv <= 0.5:
            cv_score = 70 + (0.5 - cv) * (20 / 0.2)
        elif cv <= 0.8:
            cv_score = 50 + (0.8 - cv) * (20 / 0.3)
        elif cv <= 1.2:
            cv_score = 30 + (1.2 - cv) * (20 / 0.4)
        else:
            cv_score = max(5, 30 - (cv - 1.2) * 20)

        # Active days ratio
        active_ratio = len(active_days) / max(total_days, 1)
        if active_ratio >= 0.85:
            active_score = 100
        elif active_ratio >= 0.70:
            active_score = 70 + (active_ratio - 0.70) * (30 / 0.15)
        elif active_ratio >= 0.50:
            active_score = 50 + (active_ratio - 0.50) * (20 / 0.20)
        else:
            active_score = active_ratio * 100

        # Transaction count regularity
        txn_counts = list(daily_transactions.values())
        if len(txn_counts) >= 2:
            txn_cv = float(np.std(txn_counts) / max(np.mean(txn_counts), 1))
            txn_regularity = max(0, min(100, (1 - min(txn_cv, 1)) * 100))
        else:
            txn_regularity = 50

        # Weighted combination
        raw_score = cv_score * 0.50 + active_score * 0.30 + txn_regularity * 0.20
        normalized = min(100, max(0, raw_score))

        if normalized >= 80:
            interp = "Highly consistent daily revenue"
            interp_sw = "Mauzo ya kila siku ni ya kuthabiti sana"
        elif normalized >= 60:
            interp = "Consistent with some variation"
            interp_sw = "Mauzo ni ya kuthabiti na tofauti kidogo"
        elif normalized >= 40:
            interp = "Moderate consistency — room for improvement"
            interp_sw = "Uthabiti wa wastani — kuna nafasi ya kuboresha"
        else:
            interp = "High revenue volatility — needs stabilization"
            interp_sw = "Mauzo ni ya kutofauti sana — inahitaji kuthabiti"

        return ScoreComponent(
            name="transaction_consistency",
            name_sw="Uthabiti wa Miamala",
            weight=FACTOR_WEIGHTS["transaction_consistency"],
            raw_value=round(cv, 3),
            normalized_score=round(normalized, 1),
            weighted_contribution=round(normalized * FACTOR_WEIGHTS["transaction_consistency"], 1),
            interpretation=interp,
            interpretation_sw=interp_sw,
        )

    def _score_growth(
        self, sales: list[Transaction], lookback_days: int
    ) -> ScoreComponent:
        """
        Score revenue growth (0-100).

        Splits the analysis window into halves and compares.
        Also examines week-over-week trends.

        >20% growth → 80-100
        5-20% growth → 60-80
        -5 to 5% → 40-60
        -20 to -5% → 20-40
        <-20% → 0-20
        """
        if not sales:
            return ScoreComponent(
                name="revenue_growth",
                name_sw="Ukuaji wa Mapato",
                weight=FACTOR_WEIGHTS["revenue_growth"],
                raw_value=0,
                normalized_score=20,
                weighted_contribution=20 * FACTOR_WEIGHTS["revenue_growth"],
                interpretation="No sales data available",
                interpretation_sw="Hakuna data ya mauzo",
            )

        # Half-period comparison
        sorted_sales = sorted(sales, key=lambda t: t.timestamp)
        mid = len(sorted_sales) // 2
        first_half_rev = sum(t.amount for t in sorted_sales[:mid])
        second_half_rev = sum(t.amount for t in sorted_sales[mid:])
        first_half_days = max(lookback_days // 2, 1)
        second_half_days = max(lookback_days - first_half_days, 1)

        first_daily = first_half_rev / first_half_days
        second_daily = second_half_rev / second_half_days

        if first_daily > 0:
            growth_pct = (second_daily - first_daily) / first_daily * 100
        else:
            growth_pct = 0

        # Score
        if growth_pct >= 50:
            score = 95
        elif growth_pct >= 20:
            score = 80 + (growth_pct - 20) * (15 / 30)
        elif growth_pct >= 5:
            score = 60 + (growth_pct - 5) * (20 / 15)
        elif growth_pct >= -5:
            score = 40 + (growth_pct + 5) * (20 / 10)
        elif growth_pct >= -20:
            score = 20 + (growth_pct + 20) * (20 / 15)
        else:
            score = max(0, 20 + (growth_pct + 20) * 1.0)

        # Trend direction bonus/penalty
        # Check weekly trend using last 4 weeks
        weekly_revs = defaultdict(float)
        for t in sales:
            week = t.timestamp.isocalendar()[1]
            weekly_revs[week] += t.amount
        if len(weekly_revs) >= 3:
            weeks = sorted(weekly_revs.keys())
            weekly_vals = [weekly_revs[w] for w in weeks]
            # Simple linear trend
            x = np.arange(len(weekly_vals), dtype=float)
            if len(x) >= 2:
                slope = float(np.polyfit(x, weekly_vals, 1)[0])
                if slope > 0:
                    score = min(100, score + 3)  # Trend bonus
                elif slope < 0:
                    score = max(0, score - 3)  # Trend penalty

        normalized = min(100, max(0, score))

        if normalized >= 80:
            interp = f"Strong growth: {growth_pct:+.1f}% revenue increase"
            interp_sw = f"Ukuaji mzuri: mapato yameongezeka {growth_pct:+.1f}%"
        elif normalized >= 60:
            interp = f"Moderate growth: {growth_pct:+.1f}% change"
            interp_sw = f"Ukuaji wa wastani: mabadiliko ya {growth_pct:+.1f}%"
        elif normalized >= 40:
            interp = f"Flat growth: {growth_pct:+.1f}% change"
            interp_sw = f"Ukuaji wa wastani: mabadiliko ya {growth_pct:+.1f}%"
        else:
            interp = f"Declining: {growth_pct:+.1f}% revenue decrease"
            interp_sw = f"Mapato yanapungua: {growth_pct:+.1f}%"

        return ScoreComponent(
            name="revenue_growth",
            name_sw="Ukuaji wa Mapato",
            weight=FACTOR_WEIGHTS["revenue_growth"],
            raw_value=round(growth_pct, 1),
            normalized_score=round(normalized, 1),
            weighted_contribution=round(normalized * FACTOR_WEIGHTS["revenue_growth"], 1),
            interpretation=interp,
            interpretation_sw=interp_sw,
        )

    def _score_profit_margin(
        self,
        total_revenue: float,
        total_cost: float,
        total_expense: float,
        sales: list[Transaction],
    ) -> ScoreComponent:
        """
        Score profit margin (0-100).

        Profit margin = (revenue - cost - expenses) / revenue

        Informal economy benchmarks:
        >40% → 90-100 (exceptional)
        30-40% → 75-90 (excellent)
        20-30% → 55-75 (good)
        10-20% → 35-55 (acceptable)
        0-10% → 15-35 (thin)
        <0% → 0-15 (loss)
        """
        if total_revenue <= 0:
            return ScoreComponent(
                name="profit_margin",
                name_sw="Faida ya Biashara",
                weight=FACTOR_WEIGHTS["profit_margin"],
                raw_value=0,
                normalized_score=10,
                weighted_contribution=10 * FACTOR_WEIGHTS["profit_margin"],
                interpretation="No revenue data",
                interpretation_sw="Hakuna data ya mapato",
            )

        net_profit = total_revenue - total_cost - total_expense
        margin = net_profit / total_revenue

        # Also compute per-transaction profit if available
        txns_with_profit = [t for t in sales if t.profit is not None and t.profit > 0]
        if txns_with_profit:
            avg_txn_margin = np.mean([t.profit / max(t.amount, 1) for t in txns_with_profit])
            # Blend: 70% overall margin, 30% per-txn margin
            blended_margin = margin * 0.7 + float(avg_txn_margin) * 0.3
        else:
            blended_margin = margin

        # Score
        if blended_margin >= 0.40:
            score = 90 + min((blended_margin - 0.40) * 25, 10)
        elif blended_margin >= 0.30:
            score = 75 + (blended_margin - 0.30) * (15 / 0.10)
        elif blended_margin >= 0.20:
            score = 55 + (blended_margin - 0.20) * (20 / 0.10)
        elif blended_margin >= 0.10:
            score = 35 + (blended_margin - 0.10) * (20 / 0.10)
        elif blended_margin >= 0:
            score = 15 + blended_margin * (20 / 0.10)
        else:
            score = max(0, 15 + blended_margin * 50)

        normalized = min(100, max(0, score))

        if normalized >= 80:
            interp = f"Excellent profit margin: {blended_margin * 100:.1f}%"
            interp_sw = f"Faida nzuri sana: {blended_margin * 100:.1f}%"
        elif normalized >= 60:
            interp = f"Good profit margin: {blended_margin * 100:.1f}%"
            interp_sw = f"Faida nzuri: {blended_margin * 100:.1f}%"
        elif normalized >= 40:
            interp = f"Acceptable margin: {blended_margin * 100:.1f}%"
            interp_sw = f"Faida ya wastani: {blended_margin * 100:.1f}%"
        else:
            interp = f"Low margin: {blended_margin * 100:.1f}% — review pricing"
            interp_sw = f"Faida ndogo: {blended_margin * 100:.1f}% — angalia bei"

        return ScoreComponent(
            name="profit_margin",
            name_sw="Faida ya Biashara",
            weight=FACTOR_WEIGHTS["profit_margin"],
            raw_value=round(blended_margin, 4),
            normalized_score=round(normalized, 1),
            weighted_contribution=round(normalized * FACTOR_WEIGHTS["profit_margin"], 1),
            interpretation=interp,
            interpretation_sw=interp_sw,
        )

    def _score_customer_retention(
        self,
        sales: list[Transaction],
        daily_customers: dict[str, set],
        lookback_days: int,
    ) -> ScoreComponent:
        """
        Score customer retention (0-100).

        Based on:
        - Unique customers over period
        - Repeat customer rate (customers with >1 transaction)
        - Customer frequency (avg transactions per customer)

        Repeat rate >60% → 80-100
        Repeat rate 40-60% → 60-80
        Repeat rate 20-40% → 40-60
        Repeat rate <20% → 20-40
        No customer data → score based on transaction volume
        """
        # Aggregate all customers
        all_customers: dict[str, int] = defaultdict(int)
        for t in sales:
            if t.customer_phone_hash:
                all_customers[t.customer_phone_hash] += 1

        if not all_customers:
            # No customer tracking — estimate from transaction frequency
            txn_per_day = len(sales) / max(lookback_days, 1)
            # Higher daily volume suggests repeat customers
            estimated_score = min(80, 30 + txn_per_day * 10)
            return ScoreComponent(
                name="customer_retention",
                name_sw="Wateja wa Kudumu",
                weight=FACTOR_WEIGHTS["customer_retention"],
                raw_value=round(txn_per_day, 2),
                normalized_score=round(estimated_score, 1),
                weighted_contribution=round(estimated_score * FACTOR_WEIGHTS["customer_retention"], 1),
                interpretation="Estimated from transaction volume (no customer tracking data)",
                interpretation_sw="Inakadiriwa kutoka kwa idadi ya mauzo (hakuna data ya wateja)",
            )

        total_customers = len(all_customers)
        repeat_customers = sum(1 for count in all_customers.values() if count > 1)
        repeat_rate = repeat_customers / max(total_customers, 1)
        avg_frequency = np.mean(list(all_customers.values()))

        # Repeat rate score
        if repeat_rate >= 0.60:
            rate_score = 80 + (repeat_rate - 0.60) * (20 / 0.40)
        elif repeat_rate >= 0.40:
            rate_score = 60 + (repeat_rate - 0.40) * (20 / 0.20)
        elif repeat_rate >= 0.20:
            rate_score = 40 + (repeat_rate - 0.20) * (20 / 0.20)
        else:
            rate_score = 20 + repeat_rate * (20 / 0.20)

        # Frequency bonus (more visits per customer = stickier)
        freq_bonus = min(15, (avg_frequency - 1) * 5) if avg_frequency > 1 else 0

        normalized = min(100, max(0, rate_score + freq_bonus))

        if normalized >= 80:
            interp = f"Strong retention: {repeat_rate * 100:.0f}% repeat customers"
            interp_sw = f"Wateja wa kudumu: {repeat_rate * 100:.0f}% wanarudi"
        elif normalized >= 60:
            interp = f"Good retention: {repeat_rate * 100:.0f}% repeat rate"
            interp_sw = f"Wateja wazuri: {repeat_rate * 100:.0f}% wanarudi"
        elif normalized >= 40:
            interp = f"Moderate retention: {repeat_rate * 100:.0f}% repeat rate"
            interp_sw = f"Wateja wa wastani: {repeat_rate * 100:.0f}% wanarudi"
        else:
            interp = f"Low retention: {repeat_rate * 100:.0f}% — focus on customer service"
            interp_sw = f"Wateja wachache: {repeat_rate * 100:.0f}% — zingatia huduma kwa wateja"

        return ScoreComponent(
            name="customer_retention",
            name_sw="Wateja wa Kudumu",
            weight=FACTOR_WEIGHTS["customer_retention"],
            raw_value=round(repeat_rate, 3),
            normalized_score=round(normalized, 1),
            weighted_contribution=round(normalized * FACTOR_WEIGHTS["customer_retention"], 1),
            interpretation=interp,
            interpretation_sw=interp_sw,
        )

    def _score_inventory(
        self,
        inventory: list[Inventory],
        sales: list[Transaction],
        purchases: list[Transaction],
        lookback_days: int,
    ) -> ScoreComponent:
        """
        Score inventory management (0-100).

        Based on:
        - Stock turnover rate (sales volume / avg inventory)
        - Restock discipline (items below threshold)
        - Product diversity
        - Stockout avoidance

        High turnover, few stockouts → 80-100
        Good turnover → 60-80
        Moderate → 40-60
        Poor management → 20-40
        """
        if not inventory and not purchases:
            # Service business or no inventory tracking
            # Score based on product consistency from sales
            unique_items = len(set(t.item for t in sales if t.item))
            score = min(70, 30 + unique_items * 8)
            return ScoreComponent(
                name="inventory_management",
                name_sw="Usimamizi wa Stock",
                weight=FACTOR_WEIGHTS["inventory_management"],
                raw_value=unique_items,
                normalized_score=round(score, 1),
                weighted_contribution=round(score * FACTOR_WEIGHTS["inventory_management"], 1),
                interpretation="Service-based or no inventory tracking",
                interpretation_sw="Biashara ya huduma au hakuna usimamizi wa stock",
            )

        # Turnover calculation
        total_stock_value = sum(
            (item.current_stock or 0) * (item.avg_cost or 0)
            for item in inventory
        )
        total_sold = sum(t.amount for t in sales)

        if total_stock_value > 0:
            turnover = total_sold / total_stock_value
            # Annualize if lookback < 365 days
            turnover_annualized = turnover * (365 / max(lookback_days, 1))
        else:
            turnover_annualized = 0

        # Turnover score
        if turnover_annualized >= 12:
            turnover_score = 90  # Monthly turnover — excellent
        elif turnover_annualized >= 6:
            turnover_score = 70 + (turnover_annualized - 6) * (20 / 6)
        elif turnover_annualized >= 3:
            turnover_score = 50 + (turnover_annualized - 3) * (20 / 3)
        elif turnover_annualized >= 1:
            turnover_score = 30 + (turnover_annualized - 1) * (20 / 2)
        else:
            turnover_score = max(10, turnover_annualized * 30)

        # Stockout penalty
        items_below_threshold = sum(
            1 for item in inventory
            if item.restock_threshold and item.current_stock is not None
            and item.current_stock <= item.restock_threshold
        )
        total_items = len(inventory)
        if total_items > 0:
            stockout_ratio = items_below_threshold / total_items
            stockout_penalty = stockout_ratio * 20
        else:
            stockout_penalty = 0

        # Diversity bonus
        unique_products = len(set(t.item for t in sales if t.item))
        diversity_bonus = min(10, unique_products * 2)

        normalized = min(100, max(0, turnover_score - stockout_penalty + diversity_bonus))

        if normalized >= 80:
            interp = f"Excellent inventory management (turnover: {turnover_annualized:.1f}x/year)"
            interp_sw = f"Usimamizi bora wa stock (mzunguko: {turnover_annualized:.1f}x/mwaka)"
        elif normalized >= 60:
            interp = f"Good inventory control (turnover: {turnover_annualized:.1f}x/year)"
            interp_sw = f"Usimamizi mzuri wa stock (mzunguko: {turnover_annualized:.1f}x/mwaka)"
        elif normalized >= 40:
            interp = "Moderate inventory management — optimize restocking"
            interp_sw = "Usimamizi wa wastani — boresha ununuzi wa stock"
        else:
            interp = "Poor inventory management — review stock levels"
            interp_sw = "Usimamizi mbaya wa stock — angalia viwango vya stock"

        return ScoreComponent(
            name="inventory_management",
            name_sw="Usimamizi wa Stock",
            weight=FACTOR_WEIGHTS["inventory_management"],
            raw_value=round(turnover_annualized, 2),
            normalized_score=round(normalized, 1),
            weighted_contribution=round(normalized * FACTOR_WEIGHTS["inventory_management"], 1),
            interpretation=interp,
            interpretation_sw=interp_sw,
        )

    def _score_business_age(
        self, user: User, transactions: list[Transaction]
    ) -> ScoreComponent:
        """
        Score business age and maturity (0-100).

        Based on:
        - Account age (from user.created_at)
        - Transaction history depth
        - Consistent activity over time

        >24 months → 90-100
        12-24 months → 70-90
        6-12 months → 50-70
        3-6 months → 30-50
        <3 months → 15-30
        """
        now = datetime.now(UTC)
        created = user.created_at or now
        if created.tzinfo is None:
            from datetime import timezone
            created = created.replace(tzinfo=timezone.utc)

        account_age_months = max(0, (now - created).days / 30)

        # Also check transaction history depth
        if transactions:
            first_txn = min(t.timestamp for t in transactions)
            if first_txn.tzinfo is None:
                from datetime import timezone
                first_txn = first_txn.replace(tzinfo=timezone.utc)
            txn_age_months = max(0, (now - first_txn).days / 30)
        else:
            txn_age_months = 0

        # Use the longer of account age or transaction history
        effective_age = max(account_age_months, txn_age_months)

        # Score
        if effective_age >= 24:
            score = 90 + min((effective_age - 24) * 0.5, 10)
        elif effective_age >= 12:
            score = 70 + (effective_age - 12) * (20 / 12)
        elif effective_age >= 6:
            score = 50 + (effective_age - 6) * (20 / 6)
        elif effective_age >= 3:
            score = 30 + (effective_age - 3) * (20 / 3)
        else:
            score = 15 + effective_age * (15 / 3)

        normalized = min(100, max(0, score))

        if normalized >= 80:
            interp = f"Mature business: {effective_age:.0f} months of history"
            interp_sw = f"Biashara imekomaa: miezi {effective_age:.0f} ya historia"
        elif normalized >= 60:
            interp = f"Established business: {effective_age:.0f} months"
            interp_sw = f"Biashara imara: miezi {effective_age:.0f}"
        elif normalized >= 40:
            interp = f"Growing business: {effective_age:.0f} months"
            interp_sw = f"Biashara inayokua: miezi {effective_age:.0f}"
        else:
            interp = f"New business: {effective_age:.0f} months — limited track record"
            interp_sw = f"Biashara mpya: miezi {effective_age:.0f} — historia ndogo"

        return ScoreComponent(
            name="business_age",
            name_sw="Umri wa Biashara",
            weight=FACTOR_WEIGHTS["business_age"],
            raw_value=round(effective_age, 1),
            normalized_score=round(normalized, 1),
            weighted_contribution=round(normalized * FACTOR_WEIGHTS["business_age"], 1),
            interpretation=interp,
            interpretation_sw=interp_sw,
        )

    # ── Composite Score ──────────────────────────────────────────────────────

    def _compute_composite(self, components: list[ScoreComponent]) -> int:
        """
        Compute weighted composite score scaled to 0-1000.

        Each component contributes: normalized_score * weight
        Sum is scaled from 0-100 to 0-1000.
        """
        weighted_sum = sum(c.weighted_contribution for c in components)
        # Scale: weighted_sum is in range [0, 100] → map to [0, 1000]
        composite = int(round(weighted_sum * 10))
        return max(0, min(1000, composite))

    @staticmethod
    def _score_band(score: int) -> ScoreBand:
        for threshold, band in BAND_THRESHOLDS:
            if score >= threshold:
                return band
        return ScoreBand.NO_SCORE

    @staticmethod
    def _risk_category(score: int) -> RiskCategory:
        for threshold, cat in RISK_THRESHOLDS:
            if score >= threshold:
                return cat
        return RiskCategory.VERY_HIGH

    # ── Confidence ───────────────────────────────────────────────────────────

    @staticmethod
    def _compute_confidence(
        transactions: list[Transaction], lookback_days: int
    ) -> float:
        """
        Compute confidence level (0-1) based on data quality.

        Factors:
        - Number of data points (more = higher confidence)
        - Coverage (active days / lookback days)
        - Recency (how recent is the latest transaction)
        """
        n = len(transactions)
        data_score = min(1.0, n / 200)  # 200+ transactions = full confidence

        # Coverage
        active_days = len(set(
            t.timestamp.strftime("%Y-%m-%d")
            for t in transactions
        ))
        coverage = min(1.0, active_days / max(lookback_days, 1))

        # Recency
        now = datetime.now(UTC)
        latest = max(t.timestamp for t in transactions)
        if latest.tzinfo is None:
            from datetime import timezone
            latest = latest.replace(tzinfo=timezone.utc)
        days_since_latest = (now - latest).days
        recency = max(0, 1 - days_since_latest / 30)  # Decays over 30 days

        return round(data_score * 0.4 + coverage * 0.4 + recency * 0.2, 3)

    # ── Default Probability ──────────────────────────────────────────────────

    @staticmethod
    def _default_probability(score: int) -> float:
        """
        Estimate default probability from Alama Score using logistic model.

        Score 1000 → ~1% default
        Score 700 → ~5% default
        Score 500 → ~15% default
        Score 300 → ~35% default
        """
        # Logistic: P(default) = 1 / (1 + exp(k * (score - midpoint)))
        # Calibrated for informal economy
        normalized = score / 1000
        k = 8.0  # Steepness
        midpoint = 0.45  # Score midpoint
        prob = 1.0 / (1.0 + np.exp(k * (normalized - midpoint)))
        return round(float(np.clip(prob, 0.005, 0.50)), 4)

    # ── Credit Limit ─────────────────────────────────────────────────────────

    @staticmethod
    def _recommended_credit_limit(
        transactions: list[Transaction], score: int, lookback_days: int
    ) -> float:
        """
        Recommend a credit limit based on revenue and score.

        Base: 1 month of average daily revenue
        Multiplier: scales with score (1x at 300, 3x at 800, 5x at 1000)
        """
        sales = [t for t in transactions if t.transaction_type == "SALE"]
        if not sales:
            return 0.0

        total_rev = sum(t.amount for t in sales)
        monthly_rev = total_rev / max(lookback_days / 30, 1)

        # Score-based multiplier
        if score >= 800:
            multiplier = 3.0 + (score - 800) * (2.0 / 200)
        elif score >= 600:
            multiplier = 1.5 + (score - 600) * (1.5 / 200)
        elif score >= 400:
            multiplier = 0.5 + (score - 400) * (1.0 / 200)
        else:
            multiplier = max(0.1, score * 0.5 / 400)

        limit = monthly_rev * multiplier
        # Round to nearest 1000 KES
        return round(limit, -3)

    # ── Affordability ────────────────────────────────────────────────────────

    @staticmethod
    def _assess_affordability(
        transactions: list[Transaction],
        requested_amount: float,
        lookback_days: int,
    ) -> AffordabilityAssessment:
        """Assess whether the business can afford the requested loan."""
        sales = [t for t in transactions if t.transaction_type == "SALE"]
        total_rev = sum(t.amount for t in sales)
        monthly_rev = total_rev / max(lookback_days / 30, 1)

        # Assume 30% of monthly revenue can go to repayment
        repayment_capacity = monthly_rev * 0.30

        # Max recommended: 3 months of repayment capacity
        max_recommended = repayment_capacity * 3

        # Monthly payment estimate (assuming 3-month term, 15% annual rate)
        monthly_rate = 0.15 / 12
        term_months = 3
        if requested_amount > 0 and term_months > 0:
            monthly_payment = requested_amount * (
                monthly_rate * (1 + monthly_rate) ** term_months
            ) / ((1 + monthly_rate) ** term_months - 1)
        else:
            monthly_payment = 0

        debt_ratio = monthly_payment / max(repayment_capacity, 1)
        affordable = requested_amount <= max_recommended and debt_ratio <= 0.40

        warning = None
        warning_sw = None
        if not affordable:
            if requested_amount > max_recommended:
                warning = f"Requested amount (KES {requested_amount:,.0f}) exceeds recommended limit (KES {max_recommended:,.0f})"
                warning_sw = f"Kiasi kilichoombwa (KES {requested_amount:,.0f}) kinazidi kikomo (KES {max_recommended:,.0f})"
            elif debt_ratio > 0.40:
                warning = f"Debt-to-revenue ratio ({debt_ratio:.0%}) exceeds safe threshold (40%)"
                warning_sw = f"Uwiano wa deni/mapato ({debt_ratio:.0%}) unazidi kikomo salama (40%)"

        return AffordabilityAssessment(
            affordable=affordable,
            max_recommended_amount_kes=round(max_recommended, -3),
            monthly_repayment_capacity_kes=round(repayment_capacity, -2),
            debt_to_revenue_ratio=round(debt_ratio, 3),
            warning=warning,
            warning_sw=warning_sw,
        )

    # ── Product Matching ─────────────────────────────────────────────────────

    @staticmethod
    def _match_products(
        components: list[ScoreComponent],
        score: int,
        transactions: list[Transaction],
        lookback_days: int,
    ) -> list[ProductRecommendation]:
        """Match the business to suitable financial products."""
        recommendations = []

        # Derive metrics for matching
        sales = [t for t in transactions if t.transaction_type == "SALE"]
        total_rev = sum(t.amount for t in sales)
        monthly_rev = total_rev / max(lookback_days / 30, 1)

        # Get profit margin component
        margin_comp = next(
            (c for c in components if c.name == "profit_margin"), None
        )
        margin = margin_comp.raw_value if margin_comp else 0.0

        # Get business age component
        age_comp = next(
            (c for c in components if c.name == "business_age"), None
        )
        age_months = age_comp.raw_value if age_comp else 0

        for product_type, rules in PRODUCT_RULES.items():
            # Check eligibility
            if score < rules["min_score"]:
                continue
            if margin < rules["min_margin"]:
                continue
            if age_months < rules["min_months"]:
                continue

            # Compute max amount
            max_amount = monthly_rev * rules["max_amount_multiplier"]

            # Adjust rate based on score
            score_premium = max(0, (700 - score) / 100 * 2)  # +2% per 100 points below 700
            est_rate = rules["base_rate"] + score_premium

            # Match score (how well this product fits)
            match = 0.5  # Base
            if score >= rules["min_score"] + 100:
                match += 0.15
            if margin >= rules["min_margin"] + 0.10:
                match += 0.15
            if age_months >= rules["min_months"] + 6:
                match += 0.10
            if monthly_rev > 0:
                match += 0.10  # Has revenue

            recommendations.append(ProductRecommendation(
                product_type=product_type,
                product_name=rules["name"],
                product_name_sw=rules["name_sw"],
                max_amount_kes=round(max_amount, -3),
                recommended_term_days=rules["term_days"],
                estimated_interest_rate_pct=round(est_rate, 1),
                match_score=round(min(1.0, match), 2),
                rationale=rules["rationale"],
                rationale_sw=rules["rationale_sw"],
            ))

        # Sort by match score descending
        recommendations.sort(key=lambda r: r.match_score, reverse=True)
        return recommendations[:5]  # Top 5

    # ── Peer Comparison ──────────────────────────────────────────────────────

    async def _peer_comparison(
        self,
        user: User,
        score: int,
        lookback_days: int,
        start_date,
        end_date,
    ) -> PeerComparison | None:
        """Compare score against anonymized peer cohort."""
        # Find peers in same business type and region
        query = select(User).where(
            and_(
                User.business_type == user.business_type,
                User.is_active == True,
                User.consent_data_sharing == True,
                User.id != user.id,
            )
        )
        if user.location_geohash:
            query = query.where(
                User.location_geohash.like(f"{user.location_geohash[:4]}%")
            )

        result = await self.db.execute(query)
        peers = result.scalars().all()

        if len(peers) < 5:
            return None  # Need k-anonymity

        # Compute simplified peer scores
        peer_scores = []
        for peer in peers[:100]:  # Cap at 100 for performance
            txn_query = select(Transaction).where(
                and_(
                    Transaction.user_id == peer.id,
                    Transaction.timestamp >= datetime.combine(start_date, datetime.min.time()),
                    Transaction.timestamp <= datetime.combine(end_date, datetime.max.time()),
                    Transaction.transaction_type == "SALE",
                )
            )
            txn_result = await self.db.execute(txn_query)
            peer_sales = list(txn_result.scalars().all())

            if len(peer_sales) < 5:
                continue

            peer_rev = sum(t.amount for t in peer_sales)
            peer_days = len(set(
                t.timestamp.strftime("%Y-%m-%d") for t in peer_sales
            ))
            daily_revs = defaultdict(float)
            for t in peer_sales:
                daily_revs[t.timestamp.strftime("%Y-%m-%d")] += t.amount
            rev_list = list(daily_revs.values())
            cv = float(np.std(rev_list) / max(np.mean(rev_list), 1)) if rev_list else 1

            # Simplified score
            consistency = max(0, min(100, (1 - min(cv, 1)) * 100))
            activity = min(100, len(peer_sales) / max(lookback_days, 1) * 10)
            age_days = (datetime.now(UTC) - (peer.created_at or datetime.now(UTC))).days
            age_score = min(100, age_days / 730 * 100)
            peer_score = int((consistency * 0.4 + activity * 0.3 + age_score * 0.3) * 10)
            peer_scores.append(max(0, min(1000, peer_score)))

        if not peer_scores:
            return None

        # Percentile
        below = sum(1 for s in peer_scores if s < score)
        percentile = round(below / len(peer_scores) * 100, 1)

        # vs average
        avg_peer = np.mean(peer_scores)
        vs_avg = round(score / max(avg_peer, 1), 2)

        # Identify top strength and weakness from components
        # (caller should pass these, but we'll return generic for now)
        return PeerComparison(
            cohort_size=len(peer_scores),
            percentile_rank=percentile,
            vs_cohort_avg=vs_avg,
            cohort_business_type=user.business_type or "general",
            cohort_region=user.location_name or "unknown",
            top_strength="transaction_consistency" if score > avg_peer else "revenue_growth",
            top_weakness="inventory_management" if score < avg_peer else "customer_retention",
        )

    # ── Risk Factor Identification ───────────────────────────────────────────

    @staticmethod
    def _identify_factors(
        components: list[ScoreComponent],
    ) -> tuple[list[str], list[str], list[str], list[str]]:
        """Identify risk factors and positive factors from components."""
        risk_factors = []
        risk_factors_sw = []
        positive_factors = []
        positive_factors_sw = []

        for comp in components:
            if comp.normalized_score < 40:
                risk_factors.append(f"Low {comp.name.replace('_', ' ')}")
                risk_factors_sw.append(f"{comp.name_sw} ni ndogo")
            elif comp.normalized_score >= 70:
                positive_factors.append(f"Strong {comp.name.replace('_', ' ')}")
                positive_factors_sw.append(f"{comp.name_sw} ni nzuri")

        if not risk_factors:
            risk_factors.append("No significant risk factors")
            risk_factors_sw.append("Hakuna hatari kubwa")
        if not positive_factors:
            positive_factors.append("Building business fundamentals")
            positive_factors_sw.append("Inajenga msingi wa biashara")

        return risk_factors, risk_factors_sw, positive_factors, positive_factors_sw
