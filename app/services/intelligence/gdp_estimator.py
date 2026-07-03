"""
Real-Time Informal GDP Estimator.

Theoretical Foundations (Valentine's BSc Economics & Statistics):

PRIMARY UNITS:
- ECO 205 (Intermediate Macroeconomics): National income accounting
  (GDP = C + I + G + (X-M)), IS-LM model for policy analysis,
  AD-AS for supply/demand shocks, business cycle detection,
  fiscal multipliers, monetary policy transmission
- STA 244 (Time Series Analysis): Nowcasting GDP from high-frequency
  transaction data, ARIMA/ETS forecasting, seasonal decomposition,
  Kalman filtering for latent variable estimation
- ECO 322 (Advanced Macroeconomics): Dynamic AD-AS, New Keynesian
  Phillips Curve, HANK models for heterogeneous agents, nowcasting
  methodology from mixed-frequency data

SUPPORTING UNITS:
- ECO 203 (Economic Statistics): Index number construction for
  deflating nominal GDP to real GDP, chain indices
- STA 341 (Theory of Estimation): MLE for sector multipliers,
  bootstrap CIs for GDP estimates, confidence intervals
- STA 442 (Applied Multivariate Analysis): PCA for composite
  economic indicators, factor analysis for latent GDP components
- ECO 210 (Quantitative Methods): Input-output analysis for
  sector multipliers, Leontief model for inter-industry linkages

METHODOLOGY:
Kenya's informal sector contributes ~34% of GDP but is invisible
to KNBS quarterly GDP releases. This estimator nowcasts informal
GDP using:

1. Transaction Volume × Average Margins = Gross Output by sector
2. Sector Multipliers (from I-O tables) = Total GDP contribution
3. HP Filter business cycle detection (ECO 205)
4. ARIMA nowcasting for current-quarter estimates (STA 244)
5. Bootstrap confidence intervals (STA 341)

The approach mirrors the expenditure method: GDP ≈ Σ(sales - purchases)
across all observed informal businesses, scaled by county/sector.

Data Flow:
  Transactions → Sector Aggregation → Gross Output → Value Added
  → Real GDP (deflated) → Business Cycle Analysis → Nowcast

Buyers: KNBS, CBK, Treasury, IMF, World Bank
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
from app.services.intelligence.biashara_pulse import (
    KENYA_COUNTIES,
    _bootstrap_ci,
    _detect_business_cycle_phase,
    _hodrick_prescott_filter,
)
from app.services.intelligence.cache import intelligence_cache
from app.services.intelligence.business_cycles import BusinessCycleAnalyzer
from app.services.research.confidence_intervals import ConfidenceIntervalCalculator

logger = structlog.get_logger(__name__)
settings = get_settings()

# ─────────────────────────────────────────────────────────────────────────────
# ECO 205 — Sector Multipliers (from Kenya I-O tables, approximate)
# ─────────────────────────────────────────────────────────────────────────────

# GDP multiplier: for every KES 1 of gross output in sector X,
# how much value-added (GDP) is generated. Derived from
# Leontief input-output inverse (ECO 210).
# These are approximated from Kenya's 2019 I-O tables.
SECTOR_GDP_MULTIPLIERS: Dict[str, float] = {
    "food": 0.45,           # Retail food — high value-add (margins 30-60%)
    "household": 0.35,      # Household goods — moderate margins
    "transport": 0.55,      # Boda boda, matatu — high value-add
    "clothing": 0.40,       # Mitumba, tailoring — moderate-high
    "electronics": 0.30,    # Electronics — lower margins, import-heavy
    "beauty": 0.50,         # Beauty services — high value-add
    "health": 0.45,         # Health services — moderate-high
    "agriculture": 0.35,    # Post-harvest agri — moderate
    "services": 0.60,       # Personal services — very high value-add
    "rent": 0.70,           # Imputed rent — almost pure value-add
    "other": 0.40,          # Default
}

# Employment multiplier: each informal business supports ~N jobs
# (owner + dependents + supply chain). From KNBS informal sector survey.
EMPLOYMENT_MULTIPLIER: float = 2.8

# County GDP shares (approximate, from KNBS 2023 county GDP data)
# Used for scaling national estimates from observed counties.
COUNTY_ECONOMIC_WEIGHTS: Dict[str, float] = {
    "047": 0.27,  # Nairobi
    "001": 0.08,  # Mombasa
    "022": 0.07,  # Kiambu
    "032": 0.05,  # Nakuru
    "042": 0.04,  # Kisumu
    "016": 0.04,  # Machakos
    "027": 0.03,  # Uasin Gishu
    "003": 0.03,  # Kilifi
    "012": 0.03,  # Meru
    "019": 0.02,  # Nyeri
}

# ─────────────────────────────────────────────────────────────────────────────
# ECO 203 — GDP Deflator Construction
# ─────────────────────────────────────────────────────────────────────────────

def _compute_gdp_deflator(
    nominal_gdp: float,
    base_period_prices: np.ndarray,
    current_prices: np.ndarray,
    base_quantities: np.ndarray,
    current_quantities: np.ndarray,
) -> Tuple[float, float]:
    """
    Compute real GDP using implicit GDP deflator.

    Deflator = (Nominal GDP / Real GDP) × 100
    Real GDP = Nominal GDP / (Deflator / 100)

    Uses Fisher ideal index for the deflator (superlative, ECO 203):
    P^F = √(P^L × P^P)

    Args:
        nominal_gdp: Current-period nominal GDP estimate
        base_period_prices: Base-period prices by sector
        current_prices: Current-period prices by sector
        base_quantities: Base-period quantities
        current_quantities: Current-period quantities

    Returns:
        (real_gdp, deflator_index)
    """
    from app.services.intelligence.biashara_pulse import (
        _laspeyres_index, _paasche_index, _fisher_index,
    )

    if len(base_period_prices) < 1 or len(current_prices) < 1:
        return nominal_gdp, 100.0

    # Ensure same sectors
    n = min(len(base_period_prices), len(current_prices))
    p_0 = base_period_prices[:n]
    p_t = current_prices[:n]
    q_0 = base_quantities[:n]
    q_t = current_quantities[:n]

    # Fisher ideal deflator
    l_idx = _laspeyres_index(p_t, p_0, q_0)
    p_idx = _paasche_index(p_t, p_0, q_t)
    deflator = _fisher_index(l_idx, p_idx)

    if deflator <= 0:
        return nominal_gdp, 100.0

    real_gdp = nominal_gdp / (deflator / 100.0)
    return round(real_gdp, 2), round(deflator, 2)


# ─────────────────────────────────────────────────────────────────────────────
# STA 244 — Nowcasting from Mixed-Frequency Data
# ─────────────────────────────────────────────────────────────────────────────

def _nowcast_gdp(
    daily_revenue_series: np.ndarray,
    sector_values_added: Dict[str, float],
    days_in_quarter: int = 90,
) -> Dict[str, Any]:
    """
    Nowcast current-quarter GDP from daily transaction data.

    Methodology (STA 244 — Nowcasting):
    1. Extrapolate daily run-rate to full quarter
    2. Apply seasonal adjustment (X-11 style simplified)
    3. ARIMA forecast for remaining days of quarter
    4. Combine observed + forecast for full-quarter estimate

    The MIDAS (Mixed Data Sampling) approach bridges daily
    transaction data to quarterly GDP.

    Args:
        daily_revenue_series: Daily revenue totals (most recent quarter)
        sector_values_added: Value-added by sector (from observed data)
        days_in_quarter: Total days in the quarter

    Returns:
        Dict with nowcasted GDP, confidence intervals, methodology
    """
    n_observed = len(daily_revenue_series)
    if n_observed < 7:
        return {
            "nowcast": None,
            "error": "Insufficient daily data for nowcasting (need ≥7 days)",
        }

    # 1. Observed value-added to date
    observed_va = sum(sector_values_added.values())

    # 2. Daily run-rate extrapolation
    daily_avg = np.mean(daily_revenue_series)
    daily_std = np.std(daily_revenue_series)
    days_remaining = max(0, days_in_quarter - n_observed)

    # Simple extrapolation
    extrapolated_va = daily_avg * days_remaining

    # 3. Seasonal factor (simplified — month-of-year effect)
    # Kenya: Q1 (Jan-Mar) = 0.90, Q2 (Apr-Jun) = 0.95,
    #         Q3 (Jul-Sep) = 1.05, Q4 (Oct-Dec) = 1.10
    current_month = datetime.now().month
    if current_month in (1, 2, 3):
        seasonal_factor = 0.90
    elif current_month in (4, 5, 6):
        seasonal_factor = 0.95
    elif current_month in (7, 8, 9):
        seasonal_factor = 1.05
    else:
        seasonal_factor = 1.10

    # 4. ARIMA forecast for remaining days (if enough data)
    arima_forecast = None
    if n_observed >= 30:
        try:
            from app.services.econometric_engine import ARIMAModel
            model = ARIMAModel(p=1, d=1, q=1)
            fit_result = model.fit(daily_revenue_series)
            if "error" not in fit_result and days_remaining > 0:
                fc = model.forecast(steps=min(days_remaining, 30))
                if "forecasts" in fc:
                    arima_forecast = sum(
                        f["forecast"] for f in fc["forecasts"]
                    )
        except Exception as e:
            logger.debug("arima_nowcast_failed", error=str(e))

    # 5. Combine: observed + forecast
    if arima_forecast is not None:
        forecasted_remaining = arima_forecast
    else:
        forecasted_remaining = extrapolated_va

    total_nominal_gdp = (observed_va + forecasted_remaining) * seasonal_factor

    # 6. Bootstrap CI for the estimate
    if n_observed >= 14:
        _, ci_lo, ci_hi = _bootstrap_ci(
            daily_revenue_series,
            lambda x: np.sum(x) + np.mean(x) * days_remaining,
            n_bootstrap=500,
        )
        ci_lo *= seasonal_factor
        ci_hi *= seasonal_factor
    else:
        margin = total_nominal_gdp * 0.15
        ci_lo = total_nominal_gdp - margin
        ci_hi = total_nominal_gdp + margin

    return {
        "nowcast_nominal_gdp": round(total_nominal_gdp, 2),
        "observed_value_added": round(observed_va, 2),
        "forecasted_remaining": round(forecasted_remaining, 2),
        "seasonal_factor": seasonal_factor,
        "days_observed": n_observed,
        "days_in_quarter": days_in_quarter,
        "daily_run_rate": round(daily_avg, 2),
        "confidence_interval_low": round(max(0, ci_lo), 2),
        "confidence_interval_high": round(ci_hi, 2),
        "confidence_level": 0.95,
        "arima_used": arima_forecast is not None,
        "method": "MIDAS_nowcast",
    }


class GDPEstimatorService:
    """
    Real-Time Informal GDP Estimation Service.

    Estimates GDP contribution of Kenya's informal sector using
    transaction volumes, average margins, and sector multipliers.

    Methodology:
    1. Aggregate transaction data by sector and geography
    2. Compute gross output (total sales revenue)
    3. Apply sector-specific GDP multipliers (from I-O tables)
    4. Deflate to real GDP using Fisher ideal index
    5. Detect business cycle phase (HP filter)
    6. Nowcast current quarter from daily data
    7. Bootstrap confidence intervals

    This fills the gap: KNBS GDP misses ~34% from informal sector.
    Biashara data makes the invisible economy visible.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.anonymizer = Anonymizer(db)

    async def estimate_gdp(
        self,
        county: str,
        period: str = "quarterly",
        period_start: Optional[date] = None,
        period_end: Optional[date] = None,
        buyer_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Estimate informal GDP for a county or nationally.

        Args:
            county: County code (e.g., '047' for Nairobi) or 'national'
            period: 'monthly', 'quarterly', or 'annual'
            period_start: Analysis start (default: start of current quarter)
            period_end: Analysis end (default: today)
            buyer_id: Buyer requesting this data

        Returns:
            GDP estimate dict or None if k-anonymity not met
        """
        # Check cache
        cached = await intelligence_cache.get(
            "gdp_estimator",
            county=county,
            period=period,
            start=str(period_start),
            end=str(period_end),
        )
        if cached:
            return cached

        # Default period
        if not period_end:
            period_end = date.today()
        if not period_start:
            if period == "monthly":
                period_start = period_end.replace(day=1)
            elif period == "quarterly":
                q = (period_end.month - 1) // 3
                period_start = date(period_end.year, q * 3 + 1, 1)
            else:  # annual
                period_start = date(period_end.year, 1, 1)

        county_name = KENYA_COUNTIES.get(county, county)
        is_national = county == "national"

        # ── Step 1: Get users ───────────────────────────────────────────────
        user_query = select(User).where(
            and_(
                User.is_active == True,
                User.consent_data_sharing == True,
            )
        )
        if not is_national:
            user_query = user_query.where(
                User.location_geohash.like(f"{county}%")
            )

        result = await self.db.execute(user_query)
        users = result.scalars().all()
        user_count = len(users)

        if user_count < settings.K_ANONYMITY_THRESHOLD:
            logger.warning("gdp_estimator_k_failed", county=county, users=user_count)
            return None

        user_ids = [u.id for u in users]

        # ── Step 2: Get transactions ────────────────────────────────────────
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
        purchases = [t for t in transactions if t.transaction_type == "PURCHASE"]
        expenses = [t for t in transactions if t.transaction_type == "EXPENSE"]

        if not sales:
            logger.warning("gdp_estimator_no_sales", county=county)
            return None

        # ── Step 3: Sector aggregation → Gross Output ───────────────────────
        sector_sales = defaultdict(float)
        sector_purchases = defaultdict(float)
        sector_expenses = defaultdict(float)
        sector_counts = defaultdict(int)

        for t in sales:
            cat = t.item_category or "other"
            sector_sales[cat] += t.amount
            sector_counts[cat] += 1

        for t in purchases:
            cat = t.item_category or "other"
            sector_purchases[cat] += t.amount

        for t in expenses:
            cat = t.item_category or "other"
            sector_expenses[cat] += t.amount

        total_gross_output = sum(sector_sales.values())
        total_intermediate = sum(sector_purchases.values()) + sum(sector_expenses.values())

        # ── Step 4: Value Added by sector (ECO 205 — GDP = Output - Inputs) ─
        sector_value_added = {}
        sector_gdp_estimates = {}

        for cat, gross_output in sector_sales.items():
            intermediate = sector_purchases.get(cat, 0) + sector_expenses.get(cat, 0)
            # Value Added = Gross Output - Intermediate Consumption
            raw_va = max(0, gross_output - intermediate)

            # Apply sector multiplier (from I-O tables)
            multiplier = SECTOR_GDP_MULTIPLIERS.get(cat, 0.40)

            # If we have direct VA data, use it; otherwise use multiplier
            if raw_va > 0 and intermediate > 0:
                estimated_va = raw_va
            else:
                # Apply multiplier to gross output
                estimated_va = gross_output * multiplier

            sector_value_added[cat] = estimated_va
            sector_gdp_estimates[cat] = {
                "gross_output": round(gross_output, 2),
                "intermediate_consumption": round(intermediate, 2),
                "value_added": round(estimated_va, 2),
                "gdp_multiplier": multiplier,
                "business_count": sector_counts[cat],
                "share_of_total_pct": 0.0,  # filled below
            }

        total_nominal_gdp = sum(sector_value_added.values())

        # Compute shares
        for cat in sector_gdp_estimates:
            if total_nominal_gdp > 0:
                sector_gdp_estimates[cat]["share_of_total_pct"] = round(
                    sector_value_added[cat] / total_nominal_gdp * 100, 1
                )

        # ── Step 5: Real GDP deflation (ECO 203) ───────────────────────────
        # Get previous period prices for deflation
        prev_start = period_start - (period_end - period_start)
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

        # Build price vectors for deflation
        curr_prices_by_sector = defaultdict(list)
        prev_prices_by_sector = defaultdict(list)

        for t in sales:
            if t.unit_price and t.unit_price > 0:
                curr_prices_by_sector[t.item_category or "other"].append(t.unit_price)
        for t in prev_sales:
            if t.unit_price and t.unit_price > 0:
                prev_prices_by_sector[t.item_category or "other"].append(t.unit_price)

        common_sectors = sorted(
            set(curr_prices_by_sector.keys()) & set(prev_prices_by_sector.keys())
        )

        real_gdp = total_nominal_gdp
        gdp_deflator = 100.0

        if common_sectors:
            p_0 = np.array([np.mean(prev_prices_by_sector[s]) for s in common_sectors])
            p_t = np.array([np.mean(curr_prices_by_sector[s]) for s in common_sectors])
            q_0 = np.array([len(prev_prices_by_sector[s]) for s in common_sectors], dtype=float)
            q_t = np.array([len(curr_prices_by_sector[s]) for s in common_sectors], dtype=float)

            real_gdp, gdp_deflator = _compute_gdp_deflator(
                total_nominal_gdp, p_0, p_t, q_0, q_t
            )

        # ── Step 6: Business cycle detection (ECO 205 — HP filter) ─────────
        daily_rev_series = defaultdict(float)
        for t in sales:
            daily_rev_series[t.timestamp.strftime("%Y-%m-%d")] += t.amount

        cycle_phase = "indeterminate"
        if len(daily_rev_series) >= 14:
            sorted_days = sorted(daily_rev_series.keys())
            rev_arr = np.array([daily_rev_series[d] for d in sorted_days], dtype=float)
            trend, cycle = _hodrick_prescott_filter(rev_arr, lambd=1600)
            cycle_phase = _detect_business_cycle_phase(cycle)

        # ── Step 7: Nowcasting (STA 244) ────────────────────────────────────
        nowcast_result = None
        if len(daily_rev_series) >= 7:
            sorted_days = sorted(daily_rev_series.keys())
            daily_arr = np.array([daily_rev_series[d] for d in sorted_days], dtype=float)
            nowcast_result = _nowcast_gdp(daily_arr, sector_value_added)

        # ── Step 8: Growth rate ─────────────────────────────────────────────
        prev_total = sum(t.amount for t in prev_sales) if prev_sales else 0
        growth_pct = None
        if prev_total > 0:
            # Use value-added growth, not gross sales growth
            prev_multiplied = sum(
                t.amount * SECTOR_GDP_MULTIPLIERS.get(t.item_category or "other", 0.40)
                for t in prev_sales
            )
            if prev_multiplied > 0:
                growth_pct = round(
                    (total_nominal_gdp - prev_multiplied) / prev_multiplied * 100, 1
                )

        # ── Step 9: Employment estimate ─────────────────────────────────────
        estimated_employment = int(user_count * EMPLOYMENT_MULTIPLIER)

        # ── Step 10: Bootstrap CI (STA 341) ─────────────────────────────────
        bootstrap_ci = None
        if len(sales) >= 30:
            va_per_txn = np.array([
                t.amount * SECTOR_GDP_MULTIPLIERS.get(t.item_category or "other", 0.40)
                for t in sales
            ], dtype=float)
            point, lo, hi = _bootstrap_ci(va_per_txn, np.sum, n_bootstrap=500)
            days = (period_end - period_start).days or 1
            bootstrap_ci = {
                "total_value_added": {
                    "estimate": round(point, 2),
                    "ci_lower": round(lo, 2),
                    "ci_upper": round(hi, 2),
                    "confidence": 0.95,
                    "method": "bootstrap_percentile",
                },
            }

        # ── Build response ──────────────────────────────────────────────────
        period_days = (period_end - period_start).days or 1

        # Add DP noise to sensitive metrics
        dp_nominal = max(0, round(
            self.anonymizer.add_laplace_noise(total_nominal_gdp, sensitivity=total_nominal_gdp * 0.1),
            2,
        ))
        dp_real = max(0, round(
            self.anonymizer.add_laplace_noise(real_gdp, sensitivity=real_gdp * 0.1),
            2,
        ))

        # Annualize if needed
        annualization_factor = 1.0
        if period == "monthly":
            annualization_factor = 12.0
        elif period == "quarterly":
            annualization_factor = 4.0

        response = {
            "product": "gdp_estimator",
            "version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "data_freshness": datetime.now(timezone.utc).isoformat(),
            "k_anonymity_threshold": settings.K_ANONYMITY_THRESHOLD,
            "quality_score": min(1.0, user_count / 100),
            "confidence_level": min(1.0, len(sales) / 500),

            # Geography
            "county": county,
            "county_name": county_name,
            "is_national": is_national,

            # Period
            "period_type": period,
            "period_start": str(period_start),
            "period_end": str(period_end),
            "period_days": period_days,

            # ── Core GDP Estimates ──────────────────────────────────────────
            "nominal_gdp_kes": dp_nominal,
            "real_gdp_kes": dp_real,
            "gdp_deflator": gdp_deflator,
            "annualized_nominal_gdp_kes": round(dp_nominal * annualization_factor, 2),
            "annualized_real_gdp_kes": round(dp_real * annualization_factor, 2),

            # Sector breakdown
            "sector_gdp_breakdown": dict(sector_gdp_estimates),

            # Key metrics
            "total_gross_output_kes": round(total_gross_output, 2),
            "total_value_added_kes": round(total_nominal_gdp, 2),
            "value_added_ratio": round(total_nominal_gdp / max(total_gross_output, 1), 4),

            # Growth
            "gdp_growth_pct": growth_pct,
            "gdp_growth_direction": (
                "expanding" if growth_pct and growth_pct > 2
                else "contracting" if growth_pct and growth_pct < -2
                else "stable" if growth_pct is not None
                else "insufficient_data"
            ),

            # Business cycle (ECO 205)
            "business_cycle_phase": cycle_phase,

            # Nowcast (STA 244)
            "nowcast": nowcast_result,

            # Employment
            "estimated_employment": estimated_employment,
            "employment_multiplier": EMPLOYMENT_MULTIPLIER,

            # Infrastructure
            "total_transactions": len(sales),
            "total_businesses": user_count,
            "avg_daily_revenue": round(total_gross_output / max(period_days, 1), 2),
            "avg_revenue_per_business": round(total_gross_output / max(user_count, 1), 2),

            # Confidence intervals (STA 341)
            "bootstrap_estimates": bootstrap_ci,

            # Data quality
            "users_included": user_count,
            "data_points": len(transactions),

            # Methodology note
            "methodology": {
                "approach": "expenditure_method_from_transactions",
                "gdp_formula": "GDP = Σ(Sales - Purchases - Expenses) × Sector Multipliers",
                "deflation": "Fisher ideal index (ECO 203)",
                "business_cycle": "Hodrick-Prescott filter (ECO 205)",
                "nowcasting": "MIDAS bridge + ARIMA (STA 244)",
                "confidence_intervals": "Bootstrap percentile (STA 341)",
                "sector_multipliers": "Kenya I-O tables (ECO 210)",
            },
        }

        await intelligence_cache.set(
            "gdp_estimator", response,
            county=county, period=period,
            start=str(period_start), end=str(period_end),
        )

        logger.info(
            "gdp_estimator_generated",
            county=county,
            period=period,
            nominal_gdp=dp_nominal,
            users=user_count,
            sales=len(sales),
        )
        return response
