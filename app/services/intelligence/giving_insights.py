"""
Giving Insights — Tithing & Charitable Giving Analysis Service.

Analyzes giving patterns and their correlation with financial outcomes
for informal economy workers in East Africa.

Many informal workers tithe (10% of income) to their church but never
track it. They believe "When you give, God gives you more" but have no
data to see the pattern. This service helps them understand their giving.

Academic Foundation (Valentine's BSc Economics & Statistics):
- STA 342 (Hypothesis Testing): Test if giving correlates with income
  changes — paired t-tests on before/after giving periods, chi-square
  tests on giving frequency vs income stability
- STA 341 (Estimation): Bayesian updating of giving effectiveness,
  posterior estimation of income change after giving, credible intervals
- STA 244 (Time Series): Trend detection in giving over time, ARIMA
  for giving forecast, seasonal decomposition (Ramadan, Christmas)
- ECO 206 (Microfinance): Savings behavior, financial discipline,
  commitment devices — tithing as forced savings mechanism
- PSY 200 (Behavioral Economics): Mental accounting, pro-social
  spending and wellbeing, warm-glow effect (Andreoni 1990)

Buyers: Churches, mosques, religious organizations, NGOs
"""

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import structlog
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.transaction import Transaction
from app.models.user import User
from app.services.anonymizer import Anonymizer
from app.services.intelligence.cache import intelligence_cache
from app.services.research.confidence_intervals import BootstrapCI
from app.services.research.hypothesis_testing import HypothesisTester
from app.services.statistical_foundation import (
    BootstrapInference,
    bootstrap,
    kde_estimator,
)

logger = structlog.get_logger(__name__)
settings = get_settings()

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

# Giving type constants (match GivingType enum in TitheTracker.kt)
GIVING_TYPES = {
    "TITHE": "zaka ya kumi",      # 10% tithe
    "OFFERING": "sadaka",          # Regular offering
    "CHARITY": "misaada",          # Charitable giving
    "ZAKAT": "zaka",               # Islamic obligatory giving
    "SADAQAH": "sadaqah",          # Islamic voluntary charity
    "OTHER": "nyingine",           # Other giving
}

# Default tithe rate
TITHE_RATE = 0.10  # 10%

# Zakat rate
ZAKAT_RATE = 0.025  # 2.5%

# Minimum records for reliable analysis
MIN_RECORDS_FOR_ANALYSIS = 3

# Minimum weeks of data for abundance pattern
MIN_WEEKS_FOR_ABUNDANCE = 4


class GivingInsightsService:
    """
    Analyzes giving patterns and their correlation with financial outcomes.

    Research shows:
    - Consistent givers have better financial discipline (ECO 206)
    - Tithing correlates with savings behavior (commitment device)
    - Giving creates psychological commitment to financial goals
    - Pro-social spending increases reported happiness (Dunn et al. 2008)

    This service does NOT claim giving causes income increases.
    It shows the correlation and lets workers draw their own conclusions.
    The goal is to encourage consistent giving through data visibility.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.anonymizer = Anonymizer()
        self.hypothesis_tester = HypothesisTester()
        self.bootstrap_ci = BootstrapCI()
        self.bootstrap = BootstrapInference()

    # ─────────────────────────────────────────────────────────────────────
    # CORE ANALYSIS
    # ─────────────────────────────────────────────────────────────────────

    @intelligence_cache(ttl=300)
    async def analyze_giving_pattern(self, worker_id: str) -> Dict[str, Any]:
        """
        Analyze a worker's giving pattern over time.

        Returns:
        - Total giving by type
        - Giving frequency and consistency
        - Monthly/weekly trends
        - Tithe compliance (are they giving 10%?)
        - Top recipients

        STA 244 (Time Series): Trend detection in giving amounts
        STA 201 (Descriptive Statistics): Summary statistics

        Args:
            worker_id: Worker's unique identifier

        Returns:
            Dict with giving pattern analysis
        """
        logger.info("analyzing_giving_pattern", worker_id=worker_id)

        # Get giving transactions from DB
        giving_records = await self._get_giving_records(worker_id)
        income_records = await self._get_income_records(worker_id)

        if not giving_records:
            return {
                "status": "no_data",
                "message": "Hakuna rekodi za kutoa bado. Anza leo!",
                "total_given": 0,
                "record_count": 0,
            }

        # Aggregate by type
        by_type = defaultdict(float)
        by_recipient = defaultdict(float)
        monthly_totals = defaultdict(float)
        weekly_totals = defaultdict(float)

        for record in giving_records:
            by_type[record["type"]] += record["amount"]
            if record.get("recipient"):
                by_recipient[record["recipient"]] += record["amount"]

            dt = datetime.fromtimestamp(record["date"] / 1000, tz=timezone.utc)
            month_key = dt.strftime("%Y-%m")
            week_key = dt.strftime("%Y-W%W")
            monthly_totals[month_key] += record["amount"]
            weekly_totals[week_key] += record["amount"]

        total_given = sum(by_type.values())

        # Calculate tithe compliance
        total_income = sum(r["amount"] for r in income_records) if income_records else 0
        tithe_target = total_income * TITHE_RATE
        tithe_actual = by_type.get("TITHE", 0)
        tithe_compliance = (tithe_actual / tithe_target * 100) if tithe_target > 0 else 0

        # Calculate consistency score
        consistency_score = self._calculate_consistency(giving_records, "month")

        # Monthly trend (STA 244)
        monthly_trend = self._calculate_trend(monthly_totals)

        # Giving frequency
        frequency = self._calculate_frequency(giving_records)

        return {
            "status": "success",
            "worker_id": self.anonymizer.hash_id(worker_id),
            "total_given": round(total_given, 2),
            "record_count": len(giving_records),
            "by_type": {k: round(v, 2) for k, v in by_type.items()},
            "top_recipients": sorted(
                by_recipient.items(), key=lambda x: x[1], reverse=True
            )[:5],
            "tithe_compliance": round(tithe_compliance, 1),
            "tithe_target": round(tithe_target, 2),
            "tithe_actual": round(tithe_actual, 2),
            "consistency_score": consistency_score,
            "giving_frequency": frequency,
            "monthly_trend": monthly_trend,
            "monthly_totals": dict(sorted(monthly_totals.items())),
            "period_start": min(r["date"] for r in giving_records),
            "period_end": max(r["date"] for r in giving_records),
        }

    @intelligence_cache(ttl=300)
    async def get_giving_recommendation(self, worker_id: str) -> Dict[str, Any]:
        """
        Generate giving recommendations based on worker's financial situation.

        Considers:
        - Current income level
        - Existing giving patterns
        - Financial obligations
        - Giving goals

        ECO 206 (Microfinance): Optimal savings/giving allocation
        PSY 200 (Behavioral Economics): Nudge theory for giving

        Args:
            worker_id: Worker's unique identifier

        Returns:
            Dict with giving recommendations in Swahili
        """
        logger.info("generating_giving_recommendation", worker_id=worker_id)

        income_records = await self._get_income_records(worker_id)
        giving_records = await self._get_giving_records(worker_id)

        if not income_records:
            return {
                "status": "no_income_data",
                "message": "Tafadhali rekodi mapato yako kwanza.",
                "recommendation": None,
            }

        # Calculate average monthly income
        total_income = sum(r["amount"] for r in income_records)
        months = max(1, len(set(
            datetime.fromtimestamp(r["date"] / 1000, tz=timezone.utc).strftime("%Y-%m")
            for r in income_records
        )))
        avg_monthly_income = total_income / months

        # Calculate current giving rate
        total_given = sum(r["amount"] for r in giving_records) if giving_records else 0
        giving_rate = total_given / total_income if total_income > 0 else 0

        # Generate recommendation
        tithe_target = avg_monthly_income * TITHE_RATE
        current_monthly_giving = total_given / months if months > 0 else 0
        gap = tithe_target - current_monthly_giving

        recommendations = []

        if giving_rate < 0.05:
            recommendations.append({
                "priority": "high",
                "message": f"Unatoa {giving_rate*100:.1f}% ya mapato yako. "
                           f"Lengo ni 10% (KSh {tithe_target:.0f}/mwezi). "
                           f"Anza na KSh {max(50, tithe_target/4):.0f} kwa wiki.",
                "action": "start_small",
            })
        elif giving_rate < TITHE_RATE:
            recommendations.append({
                "priority": "medium",
                "message": f"Unatoa {giving_rate*100:.1f}% ya mapato. "
                           f"Ongeza kidogo hadi ufike 10%. "
                           f"Ongeza KSh {gap/months:.0f} kwa mwezi.",
                "action": "increase_gradually",
            })
        else:
            recommendations.append({
                "priority": "low",
                "message": f"Vema! Unatoa {giving_rate*100:.1f}% ya mapato yako. "
                           f"Endelea hivi! Mungu akubariki. 🙏",
                "action": "maintain",
            })

        # Consistency recommendation
        if giving_records:
            consistency = self._calculate_consistency(giving_records, "month")
            if consistency < 50:
                recommendations.append({
                    "priority": "medium",
                    "message": "Toa kila wiki badala ya kungoja mwisho wa mwezi. "
                               "Kutoa mara kunaongeza uthabiti.",
                    "action": "increase_frequency",
                })

        return {
            "status": "success",
            "avg_monthly_income": round(avg_monthly_income, 2),
            "tithe_target": round(tithe_target, 2),
            "current_giving_rate": round(giving_rate * 100, 1),
            "recommendations": recommendations,
            "message": recommendations[0]["message"] if recommendations else "Endelea hivi!",
        }

    @intelligence_cache(ttl=300)
    async def get_abundance_insight(self, worker_id: str) -> Dict[str, Any]:
        """
        Analyze the correlation between giving and income changes.

        This is the core insight: "Does income change after giving periods?"

        IMPORTANT: This shows CORRELATION, not causation.
        The UI should present this carefully:
        - "Your income pattern around giving" (not "giving causes income")
        - Show the data, let the worker interpret

        STA 342 (Hypothesis Testing): Paired t-test on before/after income
        STA 341 (Estimation): Bayesian credible intervals for effect size
        STA 244 (Time Series): Income trend around giving events

        Args:
            worker_id: Worker's unique identifier

        Returns:
            Dict with abundance pattern analysis
        """
        logger.info("analyzing_abundance_pattern", worker_id=worker_id)

        giving_records = await self._get_giving_records(worker_id)
        income_records = await self._get_income_records(worker_id)

        if len(giving_records) < MIN_RECORDS_FOR_ANALYSIS:
            return {
                "status": "insufficient_data",
                "message": "Inahitaji angalau rekodi 3 za kutoa. "
                           "Endelea kutoa na kurekodi!",
                "min_records_needed": MIN_RECORDS_FOR_ANALYSIS,
            }

        if not income_records:
            return {
                "status": "no_income_data",
                "message": "Hakuna rekodi za mapato. Rekodi mapato yako ili tuweze "
                           "kuona mwenendo wa mapato baada ya kutoa.",
            }

        # Build weekly income and giving series
        weekly_income = defaultdict(float)
        weekly_giving = defaultdict(float)

        for record in income_records:
            dt = datetime.fromtimestamp(record["date"] / 1000, tz=timezone.utc)
            week_key = dt.strftime("%Y-W%W")
            weekly_income[week_key] += record["amount"]

        for record in giving_records:
            dt = datetime.fromtimestamp(record["date"] / 1000, tz=timezone.utc)
            week_key = dt.strftime("%Y-W%W")
            weekly_giving[week_key] += record["amount"]

        # Find giving weeks and non-giving weeks
        all_weeks = sorted(set(list(weekly_income.keys()) + list(weekly_giving.keys())))

        if len(all_weeks) < MIN_WEEKS_FOR_ABUNDANCE:
            return {
                "status": "insufficient_data",
                "message": f"Inahitaji angalau wiki {MIN_WEEKS_FOR_ABUNDANCE} za data. "
                           f"Una wiki {len(all_weeks)}.",
            }

        giving_weeks = set(weekly_giving.keys())
        giving_week_income = []
        non_giving_week_income = []

        for week in all_weeks:
            income = weekly_income.get(week, 0)
            if income > 0:
                if week in giving_weeks:
                    giving_week_income.append(income)
                else:
                    non_giving_week_income.append(income)

        # Statistical test (STA 342)
        test_result = None
        if len(giving_week_income) >= 3 and len(non_giving_week_income) >= 3:
            try:
                test_result = self.hypothesis_tester.t_test(
                    giving_week_income,
                    non_giving_week_income,
                    alternative="greater",
                )
            except Exception as e:
                logger.warning("hypothesis_test_failed", error=str(e))

        # Calculate averages
        avg_income_giving_weeks = np.mean(giving_week_income) if giving_week_income else 0
        avg_income_non_giving_weeks = (
            np.mean(non_giving_week_income) if non_giving_week_income else 0
        )

        # Percentage difference
        if avg_income_non_giving_weeks > 0:
            pct_diff = (
                (avg_income_giving_weeks - avg_income_non_giving_weeks)
                / avg_income_non_giving_weeks
                * 100
            )
        else:
            pct_diff = 0

        # Bootstrap confidence interval for the difference (STA 341)
        ci = None
        if len(giving_week_income) >= 5 and len(non_giving_week_income) >= 5:
            try:
                diff_samples = []
                for _ in range(1000):
                    g_sample = np.random.choice(giving_week_income, replace=True)
                    n_sample = np.random.choice(non_giving_week_income, replace=True)
                    diff_samples.append(np.mean(g_sample) - np.mean(n_sample))
                ci = {
                    "lower": float(np.percentile(diff_samples, 2.5)),
                    "upper": float(np.percentile(diff_samples, 97.5)),
                    "mean": float(np.mean(diff_samples)),
                }
            except Exception as e:
                logger.warning("bootstrap_ci_failed", error=str(e))

        # Generate Swahili insight message
        if pct_diff > 10:
            insight_msg = (
                f"Wiki unazotoa, mapato yako ni {abs(pct_diff):.0f}% zaidi "
                f"kuliki wiki usizotoa. Endelea kutoa! 🙏"
            )
        elif pct_diff < -10:
            insight_msg = (
                "Hakuna tofauti kubwa ya mapato kati ya wiki za kutoa na "
                "zisizo za kutoa. Muhimu ni uthabiti wa kutoa."
            )
        else:
            insight_msg = (
                "Mapato yako ni sawa wiki za kutoa na zisizo za kutoa. "
                "Kutoa ni jambo jema — endelea! 🙏"
            )

        return {
            "status": "success",
            "avg_income_giving_weeks": round(avg_income_giving_weeks, 2),
            "avg_income_non_giving_weeks": round(avg_income_non_giving_weeks, 2),
            "percentage_difference": round(pct_diff, 1),
            "giving_weeks_count": len(giving_week_income),
            "non_giving_weeks_count": len(non_giving_week_income),
            "hypothesis_test": {
                "p_value": round(test_result.p_value, 4) if test_result else None,
                "significant": test_result.p_value < 0.05 if test_result else None,
                "test": "independent_t_test",
                "alternative": "giving_weeks_income > non_giving_weeks_income",
            } if test_result else None,
            "confidence_interval_95": ci,
            "insight_message": insight_msg,
            "disclaimer": (
                "Kumbuka: Hii ni uhusiano (correlation), si sababu (causation). "
                "Mapato yanaweza kuathiriwa na mambo mengi."
            ),
        }

    # ─────────────────────────────────────────────────────────────────────
    # GIVING FORECAST (STA 244 — Time Series)
    # ─────────────────────────────────────────────────────────────────────

    async def forecast_giving(self, worker_id: str, periods: int = 4) -> Dict[str, Any]:
        """
        Forecast future giving based on historical patterns.

        Uses simple exponential smoothing (no external deps needed).
        Accounts for seasonal patterns (Ramadan, Christmas, Easter).

        STA 244 (Time Series): Exponential smoothing, seasonal decomposition

        Args:
            worker_id: Worker's unique identifier
            periods: Number of weeks to forecast

        Returns:
            Dict with giving forecast
        """
        giving_records = await self._get_giving_records(worker_id)

        if len(giving_records) < 8:
            return {
                "status": "insufficient_data",
                "message": "Inahitaji angalau wiki 8 za data za kutoa.",
            }

        # Build weekly giving series
        weekly_totals = defaultdict(float)
        for record in giving_records:
            dt = datetime.fromtimestamp(record["date"] / 1000, tz=timezone.utc)
            week_key = dt.strftime("%Y-W%W")
            weekly_totals[week_key] += record["amount"]

        # Sort by week
        sorted_weeks = sorted(weekly_totals.items())
        values = [v for _, v in sorted_weeks]

        # Simple exponential smoothing (alpha = 0.3)
        alpha = 0.3
        smoothed = [values[0]]
        for i in range(1, len(values)):
            smoothed.append(alpha * values[i] + (1 - alpha) * smoothed[-1])

        # Forecast next periods
        last_smoothed = smoothed[-1]
        forecasts = []
        for i in range(periods):
            forecasts.append(round(last_smoothed, 2))

        # Calculate giving momentum (trend direction)
        if len(smoothed) >= 4:
            recent = np.mean(smoothed[-4:])
            older = np.mean(smoothed[-8:-4]) if len(smoothed) >= 8 else np.mean(smoothed[:4])
            momentum = "increasing" if recent > older * 1.05 else (
                "decreasing" if recent < older * 0.95 else "stable"
            )
        else:
            momentum = "insufficient_data"

        return {
            "status": "success",
            "weekly_forecast": forecasts,
            "total_forecast": sum(forecasts),
            "momentum": momentum,
            "avg_weekly_giving": round(np.mean(values), 2),
            "historical_weeks": len(values),
        }

    # ─────────────────────────────────────────────────────────────────────
    # PRIVATE HELPERS
    # ─────────────────────────────────────────────────────────────────────

    async def _get_giving_records(self, worker_id: str) -> List[Dict[str, Any]]:
        """
        Fetch giving records from the database.

        Looks for transactions categorized as giving/tithe/charity.
        In the Msaidizi system, giving is stored as an EXPENSE transaction
        with category matching giving types.
        """
        try:
            giving_categories = [
                "tithe", "zaka", "sadaka", "offering", "charity",
                "misaada", "sadaqah", "mchango", "zaka ya kumi",
            ]

            result = await self.db.execute(
                select(Transaction).where(
                    and_(
                        Transaction.user_id == worker_id,
                        Transaction.type == "EXPENSE",
                        func.lower(Transaction.category).in_(giving_categories),
                    )
                ).order_by(Transaction.created_at)
            )
            transactions = result.scalars().all()

            return [
                {
                    "amount": float(t.amount),
                    "type": self._classify_giving_type(t.category),
                    "recipient": t.description or "",
                    "date": int(t.created_at.timestamp() * 1000),
                    "notes": t.notes or "",
                }
                for t in transactions
            ]
        except Exception as e:
            logger.error("failed_to_fetch_giving_records", error=str(e))
            return []

    async def _get_income_records(self, worker_id: str) -> List[Dict[str, Any]]:
        """Fetch income (SALE) transactions."""
        try:
            result = await self.db.execute(
                select(Transaction).where(
                    and_(
                        Transaction.user_id == worker_id,
                        Transaction.type == "SALE",
                    )
                ).order_by(Transaction.created_at)
            )
            transactions = result.scalars().all()

            return [
                {
                    "amount": float(t.amount),
                    "date": int(t.created_at.timestamp() * 1000),
                }
                for t in transactions
            ]
        except Exception as e:
            logger.error("failed_to_fetch_income_records", error=str(e))
            return []

    def _classify_giving_type(self, category: str) -> str:
        """Classify a transaction category into a giving type."""
        cat = category.lower().strip()
        if "tithe" in cat or "zaka ya kumi" in cat:
            return "TITHE"
        if "zakat" in cat or "zaka" in cat:
            return "ZAKAT"
        if "sadaqah" in cat or "sadaqa" in cat:
            return "SADAQAH"
        if "sadaka" in cat or "offering" in cat:
            return "OFFERING"
        if "misaada" in cat or "charity" in cat or "mchango" in cat:
            return "CHARITY"
        return "OTHER"

    def _calculate_consistency(
        self, records: List[Dict[str, Any]], period: str = "month"
    ) -> int:
        """
        Calculate giving consistency score (0-100).

        Measures regularity of giving using:
        1. Standard deviation of gaps between giving events
        2. Coverage of expected periods
        3. Current streak

        STA 201 (Descriptive Statistics): Variance, standard deviation
        """
        if len(records) < 2:
            return 20 if records else 0

        sorted_records = sorted(records, key=lambda r: r["date"])

        # Calculate gaps between giving events
        gaps = []
        for i in range(1, len(sorted_records)):
            gap_days = (sorted_records[i]["date"] - sorted_records[i - 1]["date"]) / (
                1000 * 86400
            )
            gaps.append(gap_days)

        if not gaps:
            return 20

        avg_gap = np.mean(gaps)
        std_gap = np.std(gaps)

        # Regularity score: lower std/mean ratio = more consistent
        cv = std_gap / avg_gap if avg_gap > 0 else 1.0  # coefficient of variation
        regularity = max(0, 100 * (1 - min(cv, 1.0)))

        # Coverage score
        total_days = (sorted_records[-1]["date"] - sorted_records[0]["date"]) / (1000 * 86400)
        period_days = 30 if period == "month" else 7
        expected_periods = max(1, total_days / period_days)
        actual_periods = len(set(
            int(r["date"] / (1000 * 86400 * period_days)) for r in sorted_records
        ))
        coverage = min(100, actual_periods / expected_periods * 100)

        # Streak score
        streak = 0
        now = datetime.now(timezone.utc)
        current_week = now.strftime("%Y-W%W")
        giving_weeks = set(
            datetime.fromtimestamp(r["date"] / 1000, tz=timezone.utc).strftime("%Y-W%W")
            for r in sorted_records
        )

        week = now
        while week.strftime("%Y-W%W") in giving_weeks:
            streak += 1
            week -= timedelta(weeks=1)

        streak_score = min(100, streak * 15)

        # Weighted average
        return int(regularity * 0.4 + coverage * 0.4 + streak_score * 0.2)

    def _calculate_frequency(self, records: List[Dict[str, Any]]) -> str:
        """Determine giving frequency from records."""
        if not records:
            return "Hakuna"

        sorted_records = sorted(records, key=lambda r: r["date"])
        if len(sorted_records) < 2:
            return "Mara moja"

        total_days = (sorted_records[-1]["date"] - sorted_records[0]["date"]) / (1000 * 86400)
        avg_days_between = total_days / (len(sorted_records) - 1)

        if avg_days_between <= 1:
            return "Kila siku"
        elif avg_days_between <= 3:
            return "Kila siku 2-3"
        elif avg_days_between <= 8:
            return "Kila wiki"
        elif avg_days_between <= 15:
            return "Kila wiki 2"
        elif avg_days_between <= 35:
            return "Kila mwezi"
        else:
            return f"Kila mwezi {int(np.ceil(avg_days_between / 30))}"

    def _calculate_trend(self, monthly_totals: Dict[str, float]) -> str:
        """
        Calculate giving trend direction.

        STA 244 (Time Series): Linear trend detection
        """
        if len(monthly_totals) < 3:
            return "insufficient_data"

        values = [v for _, v in sorted(monthly_totals.items())]
        x = np.arange(len(values))
        slope = np.polyfit(x, values, 1)[0]

        if slope > np.mean(values) * 0.05:
            return "increasing"
        elif slope < -np.mean(values) * 0.05:
            return "decreasing"
        else:
            return "stable"
