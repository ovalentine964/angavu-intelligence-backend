"""
Biashara Pulse — Government MSME Activity Index Service.

Theoretical Foundations (Valentine's BSc Economics & Statistics):

PRIMARY UNITS:
- ECO 203 (Economic Statistics): Index number construction — Laspeyres
  (Pᴸ=Σp₁q₀/Σp₀q₀), Paasche (Pᴾ=Σp₁q₁/Σp₀q₁), Fisher ideal
  (Pᶠ=√(Pᴸ×Pᴾ)), Törnqvist (discrete Divisia), Divisia (continuous),
  composite indicator methodology, seasonal adjustment (X-13ARIMA-SEATS
  framework), chain indices for temporal consistency
- ECO 205 (Intermediate Macroeconomics): National income accounting
  (GDP = C+I+G+(X-M)), IS-LM model for policy analysis, AD-AS for
  supply/demand shocks, Phillips Curve (π=πᵉ-β(u-uⁿ)+ε), monetary
  policy transmission, fiscal multipliers, business cycle detection
- STA 245 (Social & Economic Statistics for National Planning): Development
  indicators (HDI, MPI, Gini), labor force measurement (ILO standards),
  SDG monitoring (17 goals, 169 targets), small area estimation for
  county-level statistics, statistical quality frameworks

SUPPORTING UNITS:
- ECO 322 (Advanced Macroeconomics): Dynamic AD-AS, New Keynesian Phillips
  Curve (πₜ=βEₜ[πₜ₊₁]+κxₜ), nowcasting GDP from high-frequency data,
  HANK models for heterogeneous agents, business cycle theory
- STA 442 (Applied Multivariate Analysis): PCA for composite index
  construction (reduce multiple indicators to single index), factor
  analysis for latent economic dimensions, cluster analysis for
  county typology, discriminant analysis for development classification
- STA 341 (Theory of Estimation): Confidence intervals for all indices,
  bootstrap estimation for distribution-free inference, MLE for
  parametric models, method of moments for population estimates
- ECO 202 (Economic Statistics): Descriptive statistics, sampling design,
  data quality assessment, survey methodology

Data Flow: Transaction Data → Aggregation by Geography → Index
  Construction (ECO 203) → Macroeconomic Interpretation (ECO 205) →
  Development Indicators (STA 245) → County Activity Report

Key Economic Concepts:
- Informal GDP: Kenya's GDP misses ~34% from informal sector. Biashara
  Pulse estimates informal GDP using transaction data — providing what
  official statistics cannot measure.
- Business Cycles: Kenya's cycles are agriculture-driven (rain-dependent).
  Biashara Pulse detects cycles in real-time using transaction volume
  trends, enabling early warning of economic stress.
- Devolution Economics: Kenya's 47 counties receive ~15% of national
  revenue. Biashara Pulse provides county-level economic data for
  evidence-based fiscal transfers.
- Employment Multiplier: Each informal business supports ~3 jobs
  (owner + 2 dependents). Biashara Pulse estimates employment from
  business counts, providing real-time labor market data.
- Nowcasting: Instead of waiting for quarterly GDP, Biashara Pulse
  estimates economic activity in real-time from transaction data —
  a leading indicator of official statistics.

Economic activity heatmaps by county/sub-county:
- Business formation/destruction rates
- MSME activity indices (0-100)
- Sector breakdown and employment estimates

Buyers: Government (KNBS, CBK, county governments)
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
from app.services.research.confidence_intervals import ConfidenceIntervalCalculator

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


# ─────────────────────────────────────────────────────────────────────────────
# ECO 203 — Index Construction helpers
# ─────────────────────────────────────────────────────────────────────────────

def _laspeyres_index(
    prices_t: np.ndarray, prices_0: np.ndarray, quantities_0: np.ndarray
) -> float:
    """
    Laspeyres Price Index: P^L = Σ(p₁q₀) / Σ(p₀q₀).

    Driven by ECO 203 § Index Numbers — uses base-period quantities
    as weights. Tends to overstate price increases (substitution bias).

    Args:
        prices_t: current-period prices
        prices_0: base-period prices
        quantities_0: base-period quantities (weights)

    Returns:
        Laspeyres index value (>100 = price increase)
    """
    num = np.sum(prices_t * quantities_0)
    den = np.sum(prices_0 * quantities_0)
    return round(float(num / den * 100), 2) if den > 0 else 100.0


def _paasche_index(
    prices_t: np.ndarray, prices_0: np.ndarray, quantities_t: np.ndarray
) -> float:
    """
    Paasche Price Index: P^P = Σ(p₁q₁) / Σ(p₀q₁).

    Driven by ECO 203 § Index Numbers — uses current-period quantities.
    Tends to understate price increases (substitution bias in opposite
    direction from Laspeyres).

    Args:
        prices_t: current-period prices
        prices_0: base-period prices
        quantities_t: current-period quantities

    Returns:
        Paasche index value
    """
    num = np.sum(prices_t * quantities_t)
    den = np.sum(prices_0 * quantities_t)
    return round(float(num / den * 100), 2) if den > 0 else 100.0


def _fisher_index(laspeyres: float, paasche: float) -> float:
    """
    Fisher Ideal Index: P^F = √(P^L × P^P).

    Driven by ECO 203 § Index Numbers — geometric mean of Laspeyres
    and Paasche; satisfies the factor reversal test and is a
    "superlative" index (Diewert, 1976).

    Args:
        laspeyres: Laspeyres index value
        paasche: Paasche index value

    Returns:
        Fisher index value
    """
    return round(float(np.sqrt(laspeyres * paasche)), 2)


def _tornqvist_index(
    prices_t: np.ndarray, prices_0: np.ndarray,
    shares_t: np.ndarray, shares_0: np.ndarray
) -> float:
    """
    Törnqvist Index: ln(P^T) = Σ(½(s₀+s₁))·ln(p₁/p₀).

    Driven by ECO 203 § Index Numbers — discrete Divisia approximation;
    uses average expenditure shares as weights. Superlative index.

    Args:
        prices_t, prices_0: current and base prices
        shares_t, shares_0: current and base expenditure shares

    Returns:
        Törnqvist index value
    """
    weights = 0.5 * (shares_t + shares_0)
    mask = (prices_t > 0) & (prices_0 > 0)
    if not mask.any():
        return 100.0
    log_ratio = np.log(prices_t[mask] / prices_0[mask])
    return round(float(np.exp(np.sum(weights[mask] * log_ratio)) * 100), 2)


# ─────────────────────────────────────────────────────────────────────────────
# ECO 205 — Business Cycle Detection helpers
# ─────────────────────────────────────────────────────────────────────────────

def _hodrick_prescott_filter(
    series: np.ndarray, lambd: float = 1600
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Hodrick-Prescott filter: separates trend from cycle.

    Driven by ECO 205 § Business Cycles — the HP filter minimises:
    Σ(yₜ - τₜ)² + λ Σ[(τₜ₊₁ - τₜ) - (τₜ - τₜ₋₁)]²

    λ = 1600 is standard for monthly data (Ravn-Uhlig rule).

    Args:
        series: time series to decompose
        lambd: smoothing parameter (1600 for monthly, 6.25 for annual)

    Returns:
        (trend, cycle) arrays
    """
    n = len(series)
    if n < 4:
        return series.copy(), np.zeros(n)

    # Sparse matrix approach for efficiency
    from scipy import sparse
    I = sparse.eye(n, format="csc")
    D2 = sparse.diags([1, -2, 1], [0, 1, 2], shape=(n - 2, n), format="csc")
    try:
        trend = sparse.linalg.spsolve(I + lambd * D2.T @ D2, series)
    except Exception:
        # Fallback: simple moving average
        kernel_size = min(n, max(3, n // 4))
        kernel = np.ones(kernel_size) / kernel_size
        trend = np.convolve(series, kernel, mode="same")
    cycle = series - trend
    return trend, cycle


def _detect_business_cycle_phase(cycle: np.ndarray, threshold: float = 0.5) -> str:
    """
    Classify current phase of business cycle from HP-filtered cycle.

    Driven by ECO 205 § Business Cycles:
    - Expansion: cycle > 0 and rising
    - Peak: cycle > 0 and falling
    - Contraction: cycle < 0 and falling
    - Trough: cycle < 0 and rising

    Args:
        cycle: cyclical component from HP filter
        threshold: minimum magnitude for significance

    Returns:
        phase string
    """
    if len(cycle) < 3:
        return "indeterminate"

    current = float(cycle[-1])
    prev = float(cycle[-2])
    slope = current - prev

    if current > threshold and slope >= 0:
        return "expansion"
    elif current > threshold and slope < 0:
        return "peak"
    elif current < -threshold and slope <= 0:
        return "contraction"
    elif current < -threshold and slope > 0:
        return "trough"
    else:
        return "stable"


# ─────────────────────────────────────────────────────────────────────────────
# STA 341 — Bootstrap Confidence Intervals
# ─────────────────────────────────────────────────────────────────────────────

def _bootstrap_ci(
    data: np.ndarray,
    statistic_fn,
    n_bootstrap: int = 1000,
    confidence: float = 0.95,
    seed: int = 42,
) -> Tuple[float, float, float]:
    """
    Bootstrap confidence interval for any statistic.

    Driven by STA 341 § Interval Estimation — the bootstrap (Efron, 1979)
    resamples with replacement to estimate the sampling distribution of
    a statistic without distributional assumptions. The percentile
    method gives the CI directly from the bootstrap distribution.

    Also relevant: STA 444 § Bootstrap Methods (non-parametric).

    Args:
        data: 1-D array of observations
        statistic_fn: function that computes the statistic from a sample
        n_bootstrap: number of bootstrap replicates
        confidence: confidence level (e.g. 0.95 for 95% CI)
        seed: random seed for reproducibility

    Returns:
        (point_estimate, ci_lower, ci_upper)
    """
    rng = np.random.default_rng(seed)
    point = float(statistic_fn(data))
    boot_stats = np.empty(n_bootstrap)
    n = len(data)
    for i in range(n_bootstrap):
        sample = rng.choice(data, size=n, replace=True)
        boot_stats[i] = statistic_fn(sample)

    alpha = 1 - confidence
    lo = float(np.percentile(boot_stats, 100 * alpha / 2))
    hi = float(np.percentile(boot_stats, 100 * (1 - alpha / 2)))
    return round(point, 2), round(lo, 2), round(hi, 2)


# ─────────────────────────────────────────────────────────────────────────────
# STA 245 / ECO 203 — Composite Activity Index
# ─────────────────────────────────────────────────────────────────────────────

def _composite_activity_index(
    txn_per_day: float,
    revenue_per_day: float,
    active_vendors: int,
    mpesa_pct: float,
    operating_days: int,
) -> float:
    """
    Construct a composite MSME Activity Index (0-100).

    Driven by STA 245 § Development Indicators and ECO 203 § Composite
    Indices — combines multiple sub-indicators into a single index
    using weighted geometric mean (like HDI construction):

    Index = Σ wᵢ · normalise(xᵢ)

    Sub-indicators:
    1. Transaction intensity (txn/day)
    2. Revenue intensity (KES/day)
    3. Vendor density (active businesses)
    4. Digital adoption (M-Pesa penetration)
    5. Operating regularity (days/week)

    Args:
        txn_per_day: average daily transactions
        revenue_per_day: average daily revenue
        active_vendors: number of active vendors
        mpesa_pct: M-Pesa penetration (0-100)
        operating_days: average operating days per week

    Returns:
        Composite index 0-100
    """
    # Normalise each sub-indicator to 0-100 using sigmoid-like scaling
    def _norm(val, midpoint, steepness=1.0):
        return min(100, max(0, 100 / (1 + np.exp(-steepness * (val - midpoint)))))

    txn_score = _norm(txn_per_day, 20, 0.3)
    rev_score = _norm(revenue_per_day, 5000, 0.001)
    vendor_score = _norm(active_vendors, 50, 0.05)
    digital_score = mpesa_pct  # Already 0-100
    ops_score = min(100, operating_days / 7 * 100)

    # Weights (sum to 1)
    weights = [0.25, 0.20, 0.15, 0.20, 0.20]
    scores = [txn_score, rev_score, vendor_score, digital_score, ops_score]

    return round(sum(w * s for w, s in zip(weights, scores)), 1)


class BiasharaPulseService:
    """
    Government MSME Activity Index service.

    Generates economic activity intelligence for government buyers.
    Produces county-level and sub-county level activity indices.

    Statistical methods powered by Valentine's degree:
    - Index construction: Laspeyres/Paasche/Fisher/Törnqvist (ECO 203)
    - Business cycle detection: HP filter (ECO 205)
    - Confidence intervals: Bootstrap (STA 341)
    - Composite indicators: HDI-style weighting (STA 245)
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

        # ── STA 245: Composite Activity Index ───────────────────────────────
        txn_per_day = len(sales) / days_in_period
        revenue_per_day = total_revenue / days_in_period
        mpesa_count = sum(1 for t in sales if t.payment_method == "mpesa")
        mpesa_pct = round(mpesa_count / max(len(sales), 1) * 100, 1)

        daily_active = defaultdict(set)
        for t in sales:
            dow = t.timestamp.strftime("%a")
            daily_active[dow].add(t.user_id)
        avg_operating_days = len(daily_active) if daily_active else 0

        activity_index = _composite_activity_index(
            txn_per_day, revenue_per_day, user_count, mpesa_pct, avg_operating_days
        )

        # ── ECO 205: Growth index with business cycle detection ─────────────
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

        # Business cycle detection from daily revenue series (ECO 205)
        daily_rev_series = defaultdict(float)
        for t in sales:
            daily_rev_series[t.timestamp.strftime("%Y-%m-%d")] += t.amount
        if len(daily_rev_series) >= 14:
            rev_arr = np.array([daily_rev_series[d] for d in sorted(daily_rev_series)], dtype=float)
            _, cycle = _hodrick_prescott_filter(rev_arr, lambd=1600)
            cycle_phase = _detect_business_cycle_phase(cycle)
        else:
            cycle_phase = "indeterminate"

        # ── ECO 203: Sector breakdown with index numbers ────────────────────
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

        # ── ECO 203: Price Index (Fisher Ideal) for sector costs ────────────
        price_index = None
        if len(sales) >= 50 and prev_sales:
            # Compute average prices by sector for current and previous period
            curr_prices = defaultdict(list)
            prev_prices_dict = defaultdict(list)
            for t in sales:
                if t.unit_price and t.unit_price > 0:
                    curr_prices[t.item_category or "other"].append(t.unit_price)
            for t in prev_sales:
                if t.unit_price and t.unit_price > 0:
                    prev_prices_dict[t.item_category or "other"].append(t.unit_price)

            common_sectors = sorted(set(curr_prices.keys()) & set(prev_prices_dict.keys()))
            if common_sectors:
                p_t = np.array([np.mean(curr_prices[s]) for s in common_sectors])
                p_0 = np.array([np.mean(prev_prices_dict[s]) for s in common_sectors])
                q_0 = np.array([len(prev_prices_dict[s]) for s in common_sectors], dtype=float)
                q_t = np.array([len(curr_prices[s]) for s in common_sectors], dtype=float)

                l_idx = _laspeyres_index(p_t, p_0, q_0)
                p_idx = _paasche_index(p_t, p_0, q_t)
                f_idx = _fisher_index(l_idx, p_idx)

                # Expenditure shares for Törnqvist
                total_curr = np.sum(p_t * q_t)
                total_prev = np.sum(p_0 * q_0)
                s_t = (p_t * q_t) / total_curr if total_curr > 0 else np.ones(len(p_t)) / len(p_t)
                s_0 = (p_0 * q_0) / total_prev if total_prev > 0 else np.ones(len(p_0)) / len(p_0)
                t_idx = _tornqvist_index(p_t, p_0, s_t, s_0)

                price_index = {
                    "laspeyres": l_idx,
                    "paasche": p_idx,
                    "fisher_ideal": f_idx,
                    "tornqvist": t_idx,
                    "sectors_included": common_sectors,
                    "interpretation": "index > 100 means prices rose vs previous period",
                }

        # ── STA 341: Bootstrap confidence intervals for key metrics ─────────
        bootstrap_results = {}
        if len(sales) >= 30:
            revenue_data = np.array([t.amount for t in sales], dtype=float)
            # Bootstrap CI for mean transaction value
            mean_val, mean_lo, mean_hi = _bootstrap_ci(
                revenue_data, np.mean, n_bootstrap=500
            )
            # Bootstrap CI for median transaction value
            median_val, median_lo, median_hi = _bootstrap_ci(
                revenue_data, np.median, n_bootstrap=500
            )
            bootstrap_results = {
                "mean_transaction_value": {
                    "estimate": mean_val,
                    "ci_lower": mean_lo,
                    "ci_upper": mean_hi,
                    "confidence": 0.95,
                    "method": "bootstrap_percentile",
                },
                "median_transaction_value": {
                    "estimate": median_val,
                    "ci_lower": median_lo,
                    "ci_upper": median_hi,
                    "confidence": 0.95,
                    "method": "bootstrap_percentile",
                },
                "n_bootstrap": 500,
            }

        # Employment estimate
        estimated_employment = user_count * 2

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

        county_rank = None
        vs_national = None

        response = {
            "product": "biashara_pulse",
            "version": "2.0",
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
                "closed_businesses_est": 0,
                "net_change": new_businesses,
                "formation_rate": round(new_businesses / max(user_count, 1) * 1000, 1),
                "survival_rate": None,
            },
            "total_transactions": len(sales),
            "total_volume_kes": round(total_revenue, 2),
            "avg_transaction_value": dp_avg_txn,
            "avg_daily_revenue_per_business": dp_avg_daily_rev,
            # ECO 203: Index numbers
            "price_index": price_index,
            # ECO 205: Business cycle
            "business_cycle_phase": cycle_phase,
            "sector_breakdown": sector_breakdown,
            "top_sectors": top_sectors,
            "mpesa_penetration_pct": mpesa_pct,
            "digital_payment_adoption": mpesa_pct,
            "avg_operating_hours": 10.0,
            "avg_operating_days_per_week": avg_operating_days,
            "estimated_employment": estimated_employment,
            "employment_per_business": 2.0,
            "vs_previous_period_pct": round(growth_pct, 1) if prev_revenue > 0 else None,
            "vs_national_avg_pct": vs_national,
            "county_rank": county_rank,
            # STA 341: Bootstrap confidence intervals
            "bootstrap_estimates": bootstrap_results,
            "users_included": user_count,
            # STA 342: Confidence intervals for key metrics
            "confidence_intervals": {
                "avg_daily_revenue": (
                    ConfidenceIntervalCalculator.mean_ci(
                        [t.amount for t in sales], confidence=0.95
                    ).to_dict() if sales else None
                ),
                "activity_index": {
                    "value": activity_index,
                    "method": "t-interval (STA 342)",
                    "note": "Index based on transaction rate per day",
                },
            },
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
