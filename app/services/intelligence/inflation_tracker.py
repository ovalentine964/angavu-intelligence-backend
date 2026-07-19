"""
Real-Time Inflation Tracker.

Theoretical Foundations (Valentine's BSc Economics & Statistics):

PRIMARY UNITS:
- ECO 203 (Economic Statistics): Index number construction — Laspeyres
  (P^L = Σp₁q₀/Σp₀q₀), Paasche (P^P = Σp₁q₁/Σp₀q₁), Fisher ideal
  (P^F = √(P^L × P^P)), Törnqvist (discrete Divisia), chain indices,
  elementary price indices, quality adjustment
- ECO 205 (Intermediate Macroeconomics): Inflation measurement,
  Phillips Curve (π = πᵉ - β(u - uⁿ) + ε), CPI vs GDP deflator,
  core vs headline inflation, cost of living indices
- STA 244 (Time Series Analysis): Seasonal adjustment for price
  series, ARIMA forecasting for inflation trajectories

SUPPORTING UNITS:
- ECO 201 (Microeconomics): Consumer theory — Laspeyres uses
  base-period quantities (upper bound on COL), Paasche uses
  current-period quantities (lower bound), Fisher is "ideal"
- STA 341 (Theory of Estimation): Confidence intervals for
  inflation rates, bootstrap for distribution-free inference
- ECO 322 (Advanced Macro): New Keynesian Phillips Curve for
  inflation expectations, Taylor rule implications

METHODOLOGY:
KNBS updates CPI monthly using a 200-item basket. Angavu
Inflation Tracker computes price indices DAILY from actual
transactions across all 47 counties. This is not a survey —
it's real prices paid by real consumers in real markets.

Four index types computed in parallel:
1. Laspeyres: Base-period weights, overstates inflation
2. Paasche: Current-period weights, understates inflation
3. Fisher: Geometric mean — "ideal" index (Diewert superlative)
4. Törnqvist: Discrete Divisia — preferred for productivity analysis

All four indices are reported so buyers can choose the most
appropriate for their use case. Fisher is the default.

Data Flow:
  Transactions → Price Extraction → Index Construction →
  Inflation Rate → Daily/Monthly/Annual → County/National

Buyers: CBK (monetary policy), Treasury, KNBS, financial institutions, media
"""

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any

import numpy as np
import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.transaction import Transaction
from app.models.user import User
from app.services.anonymizer import Anonymizer
from app.services.intelligence.biashara_pulse import (
    KENYA_COUNTIES,
    _bootstrap_ci,
    _fisher_index,
    _laspeyres_index,
    _paasche_index,
    _tornqvist_index,
)
from app.services.intelligence.cache import intelligence_cache

logger = structlog.get_logger(__name__)
settings = get_settings()


# ─────────────────────────────────────────────────────────────────────────────
# ECO 203 — Core Index Number Computation
# ─────────────────────────────────────────────────────────────────────────────

def _compute_price_indices(
    base_prices: dict[str, np.ndarray],
    current_prices: dict[str, np.ndarray],
    base_quantities: dict[str, np.ndarray],
    current_quantities: dict[str, np.ndarray],
    base_expenditure_shares: dict[str, np.ndarray],
    current_expenditure_shares: dict[str, np.ndarray],
) -> dict[str, Any]:
    """
    Compute all four price indices from sector-level data.

    ECO 203 Index Number Theory:
    - Laspeyres: P^L = Σ(p₁q₀) / Σ(p₀q₀) — base-period basket
    - Paasche: P^P = Σ(p₁q₁) / Σ(p₀q₁) — current-period basket
    - Fisher: P^F = √(P^L × P^P) — superlative, passes factor reversal
    - Törnqvist: ln(P^T) = Σ(½(s₀+s₁))·ln(p₁/p₀) — Divisia discrete

    Args:
        *_prices: Dict mapping sector → array of prices
        *_quantities: Dict mapping sector → array of quantities
        *_expenditure_shares: Dict mapping sector → array of shares

    Returns:
        Dict with all four index values plus per-sector breakdown
    """
    # Flatten to arrays across all sectors
    all_base_p = []
    all_curr_p = []
    all_base_q = []
    all_curr_q = []
    all_base_s = []
    all_curr_s = []
    sector_labels = []

    for sector in sorted(set(base_prices.keys()) & set(current_prices.keys())):
        bp = base_prices[sector]
        cp = current_prices[sector]
        if len(bp) == 0 or len(cp) == 0:
            continue

        # Use mean price per sector as representative price
        all_base_p.append(np.mean(bp))
        all_curr_p.append(np.mean(cp))
        all_base_q.append(float(len(bp)))
        all_curr_q.append(float(len(cp)))

        # Expenditure shares
        bs = base_expenditure_shares.get(sector, np.array([1.0]))
        cs = current_expenditure_shares.get(sector, np.array([1.0]))
        all_base_s.append(float(np.mean(bs)))
        all_curr_s.append(float(np.mean(cs)))
        sector_labels.append(sector)

    if len(all_base_p) < 1:
        return {"error": "Insufficient common sectors for index construction"}

    p_0 = np.array(all_base_p)
    p_t = np.array(all_curr_p)
    q_0 = np.array(all_base_q)
    q_t = np.array(all_curr_q)
    s_0 = np.array(all_base_s)
    s_t = np.array(all_curr_s)

    # Normalize expenditure shares
    s_0_sum = np.sum(s_0)
    s_t_sum = np.sum(s_t)
    if s_0_sum > 0:
        s_0 = s_0 / s_0_sum
    if s_t_sum > 0:
        s_t = s_t / s_t_sum

    # Compute all four indices
    l_idx = _laspeyres_index(p_t, p_0, q_0)
    p_idx = _paasche_index(p_t, p_0, q_t)
    f_idx = _fisher_index(l_idx, p_idx)
    t_idx = _tornqvist_index(p_t, p_0, s_t, s_0)

    # Per-sector price changes
    sector_changes = {}
    for i, sector in enumerate(sector_labels):
        if p_0[i] > 0:
            pct_change = (p_t[i] - p_0[i]) / p_0[i] * 100
            sector_changes[sector] = {
                "base_price": round(float(p_0[i]), 2),
                "current_price": round(float(p_t[i]), 2),
                "change_pct": round(float(pct_change), 2),
                "weight": round(float(s_t[i]), 4),
            }

    return {
        "laspeyres": l_idx,
        "paasche": p_idx,
        "fisher_ideal": f_idx,
        "tornqvist": t_idx,
        "sector_count": len(sector_labels),
        "sector_price_changes": sector_changes,
        "base_period_avg_price": round(float(np.mean(p_0)), 2),
        "current_period_avg_price": round(float(np.mean(p_t)), 2),
    }


def _compute_inflation_rate(
    current_index: float,
    previous_index: float,
    periods_per_year: int = 12,
) -> dict[str, float]:
    """
    Compute inflation rates from index values.

    ECO 205 — Inflation Measurement:
    - Period-on-period: π = (I_t / I_{t-1} - 1) × 100
    - Annualized: π_ann = [(I_t / I_{t-1})^n - 1] × 100
    - Year-on-year: π_yoy = (I_t / I_{t-12} - 1) × 100

    Args:
        current_index: Current period index value
        previous_index: Previous period index value
        periods_per_year: Number of periods in a year (12 for monthly)

    Returns:
        Dict with period and annualized inflation rates
    """
    if previous_index <= 0:
        return {"period_inflation_pct": 0.0, "annualized_inflation_pct": 0.0}

    period_inflation = (current_index / previous_index - 1) * 100
    annualized = ((current_index / previous_index) ** periods_per_year - 1) * 100

    return {
        "period_inflation_pct": round(float(period_inflation), 2),
        "annualized_inflation_pct": round(float(annualized), 2),
    }


class InflationTrackerService:
    """
    Real-Time Inflation Tracking Service.

    Computes daily price indices from actual transaction data
    across all 47 Kenyan counties. Unlike KNBS's monthly 200-basket
    CPI, Angavu Inflation Tracker captures real prices paid by
    real consumers in real markets — updated daily.

    Four index methods computed in parallel:
    1. Laspeyres (ECO 203) — base-period weights
    2. Paasche (ECO 203) — current-period weights
    3. Fisher Ideal (ECO 203) — superlative, "ideal" index
    4. Törnqvist (ECO 203) — discrete Divisia approximation
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.anonymizer = Anonymizer(db)

    async def compute_inflation(
        self,
        county: str,
        period: str = "daily",
        period_start: date | None = None,
        period_end: date | None = None,
        base_period_start: date | None = None,
        base_period_end: date | None = None,
        buyer_id: str | None = None,
    ) -> dict[str, Any] | None:
        """
        Compute inflation indices for a county or nationally.

        Args:
            county: County code (e.g., '047' for Nairobi) or 'national'
            period: 'daily', 'weekly', 'monthly'
            period_start: Current period start
            period_end: Current period end
            base_period_start: Base period start (default: same length, one period earlier)
            base_period_end: Base period end
            buyer_id: Buyer requesting this data

        Returns:
            Inflation dict with all four indices or None if k-anonymity not met
        """
        # Check cache
        cached = await intelligence_cache.get(
            "inflation_tracker",
            county=county,
            period=period,
            start=str(period_start),
            end=str(period_end),
        )
        if cached:
            return cached

        # Default periods
        if not period_end:
            period_end = date.today()
        if not period_start:
            if period == "daily":
                period_start = period_end
            elif period == "weekly":
                period_start = period_end - timedelta(days=7)
            else:  # monthly
                period_start = period_end - timedelta(days=30)

        period_length = (period_end - period_start).days or 1

        if not base_period_end:
            base_period_end = period_start
        if not base_period_start:
            base_period_start = base_period_end - timedelta(days=period_length)

        county_name = KENYA_COUNTIES.get(county, county)
        is_national = county == "national"

        # ── Get users ───────────────────────────────────────────────────────
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
            logger.warning("inflation_k_failed", county=county, users=user_count)
            return None

        user_ids = [u.id for u in users]

        # ── Get current period transactions ─────────────────────────────────
        curr_txn_query = select(Transaction).where(
            and_(
                Transaction.user_id.in_(user_ids),
                Transaction.timestamp >= datetime.combine(period_start, datetime.min.time()),
                Transaction.timestamp <= datetime.combine(period_end, datetime.max.time()),
                Transaction.transaction_type == "SALE",
                Transaction.unit_price > 0,
            )
        )
        curr_result = await self.db.execute(curr_txn_query)
        current_sales = curr_result.scalars().all()

        if not current_sales:
            logger.warning("inflation_no_current_sales", county=county)
            return None

        # ── Get base period transactions ────────────────────────────────────
        base_txn_query = select(Transaction).where(
            and_(
                Transaction.user_id.in_(user_ids),
                Transaction.timestamp >= datetime.combine(base_period_start, datetime.min.time()),
                Transaction.timestamp <= datetime.combine(base_period_end, datetime.max.time()),
                Transaction.transaction_type == "SALE",
                Transaction.unit_price > 0,
            )
        )
        base_result = await self.db.execute(base_txn_query)
        base_sales = base_result.scalars().all()

        if not base_sales:
            logger.warning("inflation_no_base_sales", county=county)
            return None

        # ── Build price/quantity vectors by sector ──────────────────────────
        def _build_sector_data(sales_list):
            prices = defaultdict(list)
            quantities = defaultdict(list)
            expenditures = defaultdict(list)

            for t in sales_list:
                cat = t.item_category or "other"
                prices[cat].append(t.unit_price)
                qty = t.quantity if t.quantity and t.quantity > 0 else 1.0
                quantities[cat].append(qty)
                expenditures[cat].append(t.amount)

            return (
                {k: np.array(v, dtype=float) for k, v in prices.items()},
                {k: np.array(v, dtype=float) for k, v in quantities.items()},
                {k: np.array(v, dtype=float) for k, v in expenditures.items()},
            )

        base_prices, base_quantities, base_expenditures = _build_sector_data(base_sales)
        curr_prices, curr_quantities, curr_expenditures = _build_sector_data(current_sales)

        # Compute expenditure shares
        total_base_exp = sum(np.sum(v) for v in base_expenditures.values())
        total_curr_exp = sum(np.sum(v) for v in curr_expenditures.values())

        base_shares = {
            k: v / total_base_exp if total_base_exp > 0 else v
            for k, v in base_expenditures.items()
        }
        curr_shares = {
            k: v / total_curr_exp if total_curr_exp > 0 else v
            for k, v in curr_expenditures.items()
        }

        # ── ECO 203: Compute all four indices ───────────────────────────────
        index_result = _compute_price_indices(
            base_prices, curr_prices,
            base_quantities, curr_quantities,
            base_shares, curr_shares,
        )

        if "error" in index_result:
            return None

        # ── ECO 205: Inflation rates ────────────────────────────────────────
        # Use Fisher as primary index
        fisher = index_result["fisher_ideal"]
        inflation_from_fisher = _compute_inflation_rate(fisher, 100.0, periods_per_year=12)

        # ── Core vs Headline (ECO 205) ─────────────────────────────────────
        # Core inflation excludes food (volatile) — standard practice
        food_sectors = {"food", "agriculture"}
        non_food_base_p = {k: v for k, v in base_prices.items() if k not in food_sectors}
        non_food_curr_p = {k: v for k, v in curr_prices.items() if k not in food_sectors}
        non_food_base_q = {k: v for k, v in base_quantities.items() if k not in food_sectors}
        non_food_curr_q = {k: v for k, v in curr_quantities.items() if k not in food_sectors}
        non_food_base_s = {k: v for k, v in base_shares.items() if k not in food_sectors}
        non_food_curr_s = {k: v for k, v in curr_shares.items() if k not in food_sectors}

        core_inflation = None
        if non_food_base_p and non_food_curr_p:
            core_result = _compute_price_indices(
                non_food_base_p, non_food_curr_p,
                non_food_base_q, non_food_curr_q,
                non_food_base_s, non_food_curr_s,
            )
            if "error" not in core_result:
                core_fisher = core_result["fisher_ideal"]
                core_inflation = _compute_inflation_rate(core_fisher, 100.0, periods_per_year=12)
                core_inflation["fisher_ideal"] = core_fisher

        # ── STA 341: Bootstrap CI for inflation rate ────────────────────────
        bootstrap_ci = None
        if len(current_sales) >= 30 and len(base_sales) >= 30:
            curr_price_arr = np.array([t.unit_price for t in current_sales if t.unit_price > 0])
            base_price_arr = np.array([t.unit_price for t in base_sales if t.unit_price > 0])

            if len(curr_price_arr) >= 20 and len(base_price_arr) >= 20:
                def _price_ratio_stat(data):
                    # Bootstrap from pooled prices, compute ratio
                    n = len(data) // 2
                    base_sample = data[:n]
                    curr_sample = data[n:]
                    if np.mean(base_sample) > 0:
                        return np.mean(curr_sample) / np.mean(base_sample) * 100
                    return 100.0

                pooled = np.concatenate([base_price_arr, curr_price_arr])
                _, ci_lo, ci_hi = _bootstrap_ci(pooled, _price_ratio_stat, n_bootstrap=500)
                bootstrap_ci = {
                    "fisher_index": {
                        "estimate": fisher,
                        "ci_lower": ci_lo,
                        "ci_upper": ci_hi,
                        "confidence": 0.95,
                        "method": "bootstrap_percentile",
                    },
                }

        # ── Daily price series for trend analysis ───────────────────────────
        daily_avg_prices = defaultdict(lambda: defaultdict(list))
        for t in current_sales:
            day_key = t.timestamp.strftime("%Y-%m-%d")
            cat = t.item_category or "other"
            if t.unit_price and t.unit_price > 0:
                daily_avg_prices[day_key][cat].append(t.unit_price)

        daily_price_series = {}
        for day_key in sorted(daily_avg_prices.keys()):
            day_prices = daily_avg_prices[day_key]
            all_prices_for_day = []
            for cat_prices in day_prices.values():
                all_prices_for_day.extend(cat_prices)
            if all_prices_for_day:
                daily_price_series[day_key] = round(float(np.mean(all_prices_for_day)), 2)

        # ── Top price movers ────────────────────────────────────────────────
        sector_changes = index_result.get("sector_price_changes", {})
        top_risers = sorted(
            [(s, d) for s, d in sector_changes.items() if d["change_pct"] > 0],
            key=lambda x: x[1]["change_pct"], reverse=True,
        )[:5]
        top_fallers = sorted(
            [(s, d) for s, d in sector_changes.items() if d["change_pct"] < 0],
            key=lambda x: x[1]["change_pct"],
        )[:5]

        # ── Build response ──────────────────────────────────────────────────
        dp_laspeyres = round(float(self.anonymizer.add_laplace_noise(
            index_result["laspeyres"], sensitivity=5.0
        )), 2)
        dp_fisher = round(float(self.anonymizer.add_laplace_noise(
            fisher, sensitivity=5.0
        )), 2)

        response = {
            "product": "inflation_tracker",
            "version": "1.0",
            "generated_at": datetime.now(UTC).isoformat(),
            "data_freshness": datetime.now(UTC).isoformat(),
            "k_anonymity_threshold": settings.K_ANONYMITY_THRESHOLD,
            "quality_score": min(1.0, user_count / 100),
            "confidence_level": min(1.0, len(current_sales) / 500),

            # Geography
            "county": county,
            "county_name": county_name,
            "is_national": is_national,

            # Period
            "period_type": period,
            "current_period": f"{period_start} to {period_end}",
            "base_period": f"{base_period_start} to {base_period_end}",

            # ── Four Price Indices (ECO 203) ────────────────────────────────
            "price_indices": {
                "laspeyres": dp_laspeyres,
                "paasche": round(float(index_result["paasche"]), 2),
                "fisher_ideal": dp_fisher,
                "tornqvist": round(float(index_result["tornqvist"]), 2),
                "primary_index": "fisher_ideal",
                "interpretation": "100 = no change vs base period; >100 = prices rose",
            },

            # ── Inflation Rates (ECO 205) ──────────────────────────────────
            "headline_inflation": {
                **inflation_from_fisher,
                "index_value": dp_fisher,
                "index_method": "fisher_ideal",
            },
            "core_inflation": core_inflation,

            # Sector breakdown
            "sector_price_changes": sector_changes,
            "top_price_risers": [
                {"sector": s, **d} for s, d in top_risers
            ],
            "top_price_fallers": [
                {"sector": s, **d} for s, d in top_fallers
            ],
            "sectors_tracked": index_result["sector_count"],

            # Daily price trend
            "daily_price_trend": daily_price_series,

            # Confidence intervals (STA 341)
            "bootstrap_estimates": bootstrap_ci,

            # Data quality
            "users_included": user_count,
            "current_period_transactions": len(current_sales),
            "base_period_transactions": len(base_sales),
            "total_data_points": len(current_sales) + len(base_sales),

            # Methodology
            "methodology": {
                "primary_index": "Fisher Ideal (ECO 203)",
                "all_indices": ["Laspeyres", "Paasche", "Fisher", "Törnqvist"],
                "core_excludes": "food, agriculture (volatile sectors)",
                "confidence_intervals": "Bootstrap percentile (STA 341)",
                "update_frequency": "Daily (vs KNBS monthly CPI)",
                "basket_coverage": "All observed products in transactions",
            },
        }

        await intelligence_cache.set(
            "inflation_tracker", response,
            county=county, period=period,
            start=str(period_start), end=str(period_end),
        )

        logger.info(
            "inflation_tracker_generated",
            county=county,
            period=period,
            fisher_index=fisher,
            users=user_count,
            transactions=len(current_sales),
        )
        return response

    async def get_inflation_timeseries(
        self,
        county: str,
        periods: int = 30,
        period_type: str = "daily",
    ) -> dict[str, Any] | None:
        """
        Get historical inflation time series.

        Computes indices for multiple past periods to show trend.

        Args:
            county: County code or 'national'
            periods: Number of periods to look back
            period_type: 'daily' or 'weekly'

        Returns:
            Time series of inflation indices
        """
        today = date.today()
        series = []

        for i in range(periods, 0, -1):
            if period_type == "daily":
                p_start = today - timedelta(days=i)
                p_end = p_start
                b_start = p_start - timedelta(days=1)
                b_end = p_start - timedelta(days=1)
            else:  # weekly
                p_end = today - timedelta(days=i * 7)
                p_start = p_end - timedelta(days=7)
                b_end = p_start
                b_start = b_start - timedelta(days=7)

            result = await self.compute_inflation(
                county=county,
                period=period_type,
                period_start=p_start,
                period_end=p_end,
                base_period_start=b_start if period_type == "daily" else None,
                base_period_end=b_end if period_type == "daily" else None,
            )

            if result:
                series.append({
                    "date": str(p_end),
                    "fisher_ideal": result["price_indices"]["fisher_ideal"],
                    "laspeyres": result["price_indices"]["laspeyres"],
                    "headline_inflation_pct": result["headline_inflation"]["period_inflation_pct"],
                })

        return {
            "product": "inflation_tracker_timeseries",
            "county": county,
            "period_type": period_type,
            "periods": len(series),
            "series": series,
        }
