"""
Soko Pulse — FMCG Demand Forecasting Service.

Theoretical Foundations (Valentine's BSc Economics & Statistics):

PRIMARY UNITS:
- STA 244 (Time Series Analysis & Forecasting): ARIMA/SARIMA price
  forecasting (Box-Jenkins methodology), exponential smoothing (Holt-Winters
  for level+trend+seasonality), seasonal decomposition (additive: Y=T+S+C+I
  and multiplicative: Y=T×S×C×I), ACF/PACF for model identification,
  unit root tests (ADF, Phillips-Perron) for stationarity, cointegration
  (Engle-Granger) for market integration, Granger causality for price
  transmission, VAR models for inter-market dynamics
- ECO 424 (Econometrics): Price determination models (log-log regression
  for elasticity), instrumental variables for causal price effects,
  heteroskedasticity-robust inference (White SE), panel data methods
  for multi-market analysis, structural breaks (Chow test)
- ECO 201 (Intermediate Microeconomics): Supply-demand equilibrium,
  price elasticity (PED = %ΔQd/%ΔP), income elasticity (YED),
  cross-price elasticity (XED = %ΔQd_A/%ΔP_B), consumer surplus
  (∫D(Q)dQ - P*Q*), producer surplus, Slutsky decomposition
  (substitution + income effects), revealed preference theory

SUPPORTING UNITS:
- ECO 203 (Economic Statistics): Index numbers — Laspeyres (Pᴸ=Σp₁q₀/Σp₀q₀),
  Paasche (Pᴾ=Σp₁q₁/Σp₀q₁), Fisher ideal (Pᶠ=√(Pᴸ×Pᴾ)), Törnqvist
  for cost-of-living, Divisia for continuous indices
- STA 241 (Probability): Price distribution modeling (log-normal for prices,
  gamma for quantities), extreme value analysis for price spikes,
  Poisson process for customer arrivals
- ECO 210 (Quantitative Methods): Optimization for inventory management,
  break-even analysis, linear programming for supply chain routing
- ECO 305/313 (International Economics): Cross-border price intelligence,
  exchange rate pass-through, gravity model for trade flows

Data Flow: Raw Transaction → Price Distribution (STA 241) → Seasonal
  Decomposition (STA 244) → Time Series Model (STA 244) → Elasticity
  Estimation (ECO 201) → Price Index (ECO 203) → Demand Forecast

Key Economic Concepts:
- Law of Demand: As P↑, Qd↓ (ceteris paribus) — downward-sloping demand
- Cobweb Model: Farmers decide planting based on LAST season's price →
  price cycles. Soko Pulse breaks this cycle with forward-looking forecasts.
- Search and Matching (Diamond-Mortensen-Pissarides, 2010 Nobel): Informal
  markets have HIGH search costs. Soko Pulse reduces these costs by
  providing real-time price information across markets.
- Market Efficiency: If informal markets are efficient, prices reflect all
  available information (martingale property). Price dispersion across
  markets measures inefficiency — Soko Pulse quantifies this.
- Welfare Analysis: Consumer surplus from better price information =
  ∫(P_max - P_actual)dQ. This is the economic value of Soko Pulse.

Real-time demand patterns from informal markets:
- What sells, where, when, seasonal trends
- Price intelligence across markets
- Demand forecasting with confidence intervals

Buyers: FMCG companies (Unilever, Coca-Cola, P&G, EABL, etc.)
"""

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import structlog
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.intelligence_products import SokoPulseReport
from app.models.transaction import Transaction
from app.models.user import User
from app.services.anonymizer import Anonymizer
from app.services.intelligence.cache import intelligence_cache
from app.services.research.confidence_intervals import ConfidenceIntervalCalculator
from app.services.research.hypothesis_testing import HypothesisTester

logger = structlog.get_logger(__name__)
settings = get_settings()


# ─────────────────────────────────────────────────────────────────────────────
# STA 244 — Time Series Analysis & Forecasting helpers
# ─────────────────────────────────────────────────────────────────────────────

def _seasonal_decompose_additive(
    series: np.ndarray, period: int = 7
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Additive seasonal decomposition: Y = T + S + I.

    Driven by STA 244 § Time Series Components:
    - Trend extracted via centered moving average
    - Seasonal component averaged over detrended residuals
    - Irregular = residual after removing trend + seasonal

    Args:
        series: 1-D time series array
        period: seasonal period (7 for weekly, 12 for monthly)

    Returns:
        (trend, seasonal, irregular) arrays
    """
    n = len(series)
    if n < 2 * period:
        # Not enough data — return zeros
        z = np.zeros(n)
        return z.copy(), z.copy(), series.copy()

    # Trend: centered moving average
    kernel = np.ones(2 * period + 1) / (2 * period + 1)
    trend = np.convolve(series, kernel, mode="same")
    # Trim edges
    trend[:period] = np.nan
    trend[-period:] = np.nan

    # Detrended
    detrended = series - trend

    # Seasonal: average per position in cycle
    seasonal = np.zeros(n)
    for pos in range(period):
        vals = detrended[pos::period]
        vals = vals[~np.isnan(vals)]
        seasonal[pos::period] = np.nanmean(vals) if len(vals) else 0.0

    # Normalize seasonal to sum to 0
    seasonal -= np.nanmean(seasonal[:period])

    # Irregular
    irregular = series - trend - seasonal
    irregular[np.isnan(irregular)] = 0.0
    trend = np.nan_to_num(trend, nan=np.nanmean(series))

    return trend, seasonal, irregular


def _holt_winters_forecast(
    series: np.ndarray,
    seasonal_period: int = 7,
    alpha: float = 0.3,
    beta: float = 0.1,
    gamma: float = 0.2,
    n_forecast: int = 4,
    additive: bool = True,
) -> Dict[str, Any]:
    """
    Holt-Winters triple exponential smoothing (additive or multiplicative).

    Driven by STA 244 § Exponential Smoothing — Holt-Winters method
    captures level (α), trend (β), and seasonality (γ) simultaneously.

    Args:
        series: observed time series
        seasonal_period: number of periods in a full seasonal cycle
        alpha, beta, gamma: smoothing parameters in [0, 1]
        n_forecast: number of periods ahead to forecast
        additive: True for additive, False for multiplicative seasonality

    Returns:
        dict with forecasted values, fitted values, and residual std
    """
    n = len(series)
    if n < 2 * seasonal_period:
        # Fall back to simple exponential smoothing
        smoothed = series[0]
        for v in series[1:]:
            smoothed = alpha * v + (1 - alpha) * smoothed
        residuals = series - smoothed
        std = float(np.std(residuals)) if len(residuals) > 1 else smoothed * 0.1
        return {
            "forecast": [round(smoothed, 2)] * n_forecast,
            "fitted": np.full(n, smoothed),
            "residual_std": std,
        }

    # Initialise level, trend, seasonal
    level = float(np.mean(series[:seasonal_period]))
    trend_val = float(
        (np.mean(series[seasonal_period : 2 * seasonal_period])
         - np.mean(series[:seasonal_period]))
        / seasonal_period
    )
    seasonal = np.zeros(seasonal_period)
    for i in range(seasonal_period):
        if additive:
            seasonal[i] = series[i] - level
        else:
            seasonal[i] = series[i] / level if level else 1.0

    fitted = np.zeros(n)
    for t in range(n):
        s_idx = t % seasonal_period
        if additive:
            fitted[t] = level + trend_val + seasonal[s_idx]
            new_level = alpha * (series[t] - seasonal[s_idx]) + (1 - alpha) * (level + trend_val)
            seasonal[s_idx] = gamma * (series[t] - new_level) + (1 - gamma) * seasonal[s_idx]
        else:
            fitted[t] = (level + trend_val) * seasonal[s_idx]
            safe_seasonal = seasonal[s_idx] if seasonal[s_idx] else 1.0
            new_level = alpha * (series[t] / safe_seasonal) + (1 - alpha) * (level + trend_val)
            seasonal[s_idx] = gamma * (series[t] / (level + trend_val if (level + trend_val) else 1.0)) + (1 - gamma) * seasonal[s_idx]

        new_trend = beta * (new_level - level) + (1 - beta) * trend_val
        level = new_level
        trend_val = new_trend

    # Forecast
    forecasts = []
    for h in range(1, n_forecast + 1):
        s_idx = (n + h - 1) % seasonal_period
        if additive:
            forecasts.append(round(level + h * trend_val + seasonal[s_idx], 2))
        else:
            forecasts.append(round((level + h * trend_val) * seasonal[s_idx], 2))

    residuals = series - fitted
    std = float(np.std(residuals)) if len(residuals) > 1 else level * 0.1

    return {
        "forecast": forecasts,
        "fitted": fitted,
        "residual_std": std,
    }


def _simple_arima_forecast(
    series: np.ndarray, order: Tuple[int, int, int] = (1, 1, 0), n_forecast: int = 4
) -> Dict[str, Any]:
    """
    Lightweight ARIMA(p,d,q) forecast using OLS for AR and MA components.

    Driven by STA 244 § ARIMA Models — Box-Jenkins methodology:
    1. Identify order via ACF/PACF patterns
    2. Estimate parameters via conditional least squares
    3. Diagnostic checking via Ljung-Box test

    This is a simplified implementation for the MVP; production
    would use statsmodels or pmdarima.

    Args:
        series: 1-D time series
        order: (p, d, q) — autoregressive, differencing, moving-average orders
        n_forecast: steps ahead to forecast

    Returns:
        dict with forecasts, AIC approximation, and residual diagnostics
    """
    p, d, q = order
    y = series.copy().astype(float)
    for _ in range(d):
        y = np.diff(y)

    n = len(y)
    if n <= p + q:
        return {"forecast": [float(y[-1])] * n_forecast, "aic": None}

    # Build regressors: AR(p) + MA(q) approximated via iterative residuals
    max_lag = max(p, q)
    X_rows = []
    y_vals = []
    residuals_est = np.zeros(n)

    for t in range(max_lag, n):
        row = []
        for i in range(1, p + 1):
            row.append(y[t - i])
        for j in range(1, q + 1):
            row.append(residuals_est[t - j])
        X_rows.append(row)
        y_vals.append(y[t])

    X = np.array(X_rows)
    y_arr = np.array(y_vals)

    # OLS
    if X.shape[0] <= X.shape[1]:
        return {"forecast": [float(y[-1])] * n_forecast, "aic": None}

    try:
        beta_hat = np.linalg.lstsq(X, y_arr, rcond=None)[0]
    except np.linalg.LinAlgError:
        return {"forecast": [float(y[-1])] * n_forecast, "aic": None}

    fitted = X @ beta_hat
    residuals = y_arr - fitted

    # AIC approximation: 2k + n*ln(RSS/n)
    k = p + q
    rss = float(np.sum(residuals**2))
    n_obs = len(y_arr)
    aic = 2 * k + n_obs * np.log(rss / n_obs) if rss > 0 else None

    # Recursive forecast
    history = list(y)
    forecasts = []
    res_history = list(residuals[-q:]) if q > 0 else []
    for _ in range(n_forecast):
        row = []
        for i in range(1, p + 1):
            row.append(history[-i] if i <= len(history) else 0)
        for j in range(1, q + 1):
            row.append(res_history[-j] if j <= len(res_history) else 0)
        pred = float(np.dot(beta_hat, row))
        forecasts.append(pred)
        history.append(pred)
        res_history.append(0)  # Unknown future residual

    # If differenced, integrate back
    if d > 0:
        base = series[-1]
        integrated = []
        cumulative = base
        for f in forecasts:
            cumulative += f
            integrated.append(round(cumulative, 2))
        forecasts = integrated
    else:
        forecasts = [round(f, 2) for f in forecasts]

    # Ljung-Box Q-statistic (lag 5)
    if len(residuals) > 5:
        n_r = len(residuals)
        acf_vals = []
        for lag in range(1, 6):
            if lag < n_r:
                acf_vals.append(
                    float(np.corrcoef(residuals[:-lag], residuals[lag:])[0, 1])
                )
        lb_q = n_r * (n_r + 2) * sum(
            c**2 / (n_r - k) for k, c in enumerate(acf_vals, 1)
        )
    else:
        lb_q = None

    return {
        "forecast": forecasts,
        "aic": round(aic, 2) if aic else None,
        "ljung_box_q": round(lb_q, 2) if lb_q else None,
    }


def _estimate_price_elasticity(
    prices: np.ndarray, quantities: np.ndarray
) -> Dict[str, float]:
    """
    Estimate price elasticity of demand via log-log regression.

    Driven by ECO 201 § Elasticity and ECO 424 § Regression Analysis:
    ln(Q) = α + ε·ln(P) + u
    where ε = price elasticity of demand (constant elasticity model).

    Uses OLS with heteroskedasticity-robust standard errors (White/HC1)
    per ECO 424 § Heteroskedasticity.

    Args:
        prices: array of observed prices
        quantities: array of observed quantities

    Returns:
        dict with elasticity estimate, standard error, R², and interpretation
    """
    mask = (prices > 0) & (quantities > 0)
    p = prices[mask]
    q = quantities[mask]
    if len(p) < 10:
        return {"elasticity": None, "std_error": None, "r_squared": None}

    ln_p = np.log(p)
    ln_q = np.log(q)

    # OLS: ln_q = a + b * ln_p
    X = np.column_stack([np.ones(len(ln_p)), ln_p])
    try:
        beta = np.linalg.lstsq(X, ln_q, rcond=None)[0]
    except np.linalg.LinAlgError:
        return {"elasticity": None, "std_error": None, "r_squared": None}

    residuals = ln_q - X @ beta
    n, k = X.shape
    if n <= k:
        return {"elasticity": None, "std_error": None, "r_squared": None}

    sigma2 = float(np.sum(residuals**2) / (n - k))

    # Heteroskedasticity-robust (HC1) variance
    bread = np.linalg.inv(X.T @ X)
    meat = X.T @ np.diag(residuals**2) @ X
    robust_var = bread @ meat @ bread * (n / (n - k))
    se = np.sqrt(np.diag(robust_var))

    elasticity = float(beta[1])
    se_elasticity = float(se[1])

    # R²
    ss_res = np.sum(residuals**2)
    ss_tot = np.sum((ln_q - np.mean(ln_q)) ** 2)
    r_sq = 1 - ss_res / ss_tot if ss_tot > 0 else 0

    # Interpretation
    abs_e = abs(elasticity)
    if abs_e > 1:
        interp = "elastic"
    elif abs_e < 1:
        interp = "inelastic"
    else:
        interp = "unit_elastic"

    return {
        "elasticity": round(elasticity, 4),
        "std_error": round(se_elasticity, 4),
        "r_squared": round(float(r_sq), 4),
        "interpretation": interp,
        "sample_size": int(n),
    }


def _compute_consumer_surplus(
    demand_intercept: float, demand_slope: float,
    equilibrium_price: float, equilibrium_quantity: float
) -> float:
    """
    Consumer surplus = area below demand curve, above equilibrium price.

    Driven by ECO 201 § Welfare Economics:
    CS = ∫₀^Q* D(Q)dQ − P*Q*
    For linear demand P = a − bQ:
    CS = ½ · (a − P*) · Q*

    Args:
        demand_intercept: 'a' in P = a - bQ
        demand_slope: 'b' in P = a - bQ
        equilibrium_price: observed market-clearing price
        equilibrium_quantity: observed market-clearing quantity

    Returns:
        estimated consumer surplus
    """
    max_price = demand_intercept  # price at Q=0
    cs = 0.5 * (max_price - equilibrium_price) * equilibrium_quantity
    return max(0, round(cs, 2))


class SokoPulseService:
    """
    FMCG demand forecasting service.

    Generates demand intelligence from anonymized transaction data.
    Enforces k-anonymity (k≥10) on all outputs.

    Statistical methods powered by Valentine's degree:
    - Price forecasting: Holt-Winters & ARIMA (STA 244)
    - Demand analysis: Price elasticity via log-log regression (ECO 201/424)
    - Seasonal decomposition: Additive decomposition (STA 244)
    - Welfare measurement: Consumer surplus (ECO 201)
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.anonymizer = Anonymizer(db)

    async def generate_demand_forecast(
        self,
        product_category: str,
        product_name: Optional[str] = None,
        region: Optional[str] = None,
        period_start: Optional[date] = None,
        period_end: Optional[date] = None,
        tier: str = "standard",
        buyer_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Generate FMCG demand forecasting intelligence.

        Args:
            product_category: Category to analyze (food, household, etc.)
            product_name: Specific product or None for category-level
            region: Geographic region or None for national
            period_start: Analysis start (default: 90 days ago)
            period_end: Analysis end (default: today)
            tier: Pricing tier (standard/premium/enterprise)
            buyer_id: Buyer requesting this data

        Returns:
            Intelligence dict or None if k-anonymity not met
        """
        # Check cache
        cached = await intelligence_cache.get(
            "soko_pulse",
            category=product_category,
            product=product_name,
            region=region,
            start=str(period_start),
            end=str(period_end),
            tier=tier,
        )
        if cached:
            return cached

        # Default period
        if not period_end:
            period_end = date.today()
        if not period_start:
            period_start = period_end - timedelta(days=90)

        # Query transactions
        query = select(Transaction).where(
            and_(
                Transaction.transaction_type == "SALE",
                Transaction.item_category == product_category,
                Transaction.timestamp >= datetime.combine(period_start, datetime.min.time()),
                Transaction.timestamp <= datetime.combine(period_end, datetime.max.time()),
            )
        )

        if product_name:
            query = query.where(Transaction.item == product_name)

        # Apply region filter
        user_ids = None
        if region:
            user_query = select(User.id).where(
                and_(
                    User.location_geohash.like(f"{region}%"),
                    User.is_active == True,
                    User.consent_data_sharing == True,
                )
            )
            result = await self.db.execute(user_query)
            user_ids = [row[0] for row in result.all()]
            if not user_ids:
                return None
            query = query.where(Transaction.user_id.in_(user_ids))

        result = await self.db.execute(query)
        transactions = result.scalars().all()

        if not transactions:
            return None

        # k-anonymity check
        unique_users = set(t.user_id for t in transactions)
        k = len(unique_users)
        passes, k_value = self.anonymizer.check_k_anonymity(k)
        if not passes:
            logger.warning("soko_pulse_k_anonymity_failed", k=k, threshold=settings.K_ANONYMITY_THRESHOLD)
            return None

        # Aggregate metrics
        amounts = [t.amount for t in transactions]
        quantities = [t.quantity or 0 for t in transactions]
        unit_prices = [t.unit_price for t in transactions if t.unit_price and t.unit_price > 0]

        total_volume = sum(quantities)
        days_in_period = (period_end - period_start).days or 1
        avg_daily_volume = total_volume / days_in_period

        # ── STA 244: Day-of-week pattern ────────────────────────────────────
        dow_data = defaultdict(lambda: {"volume": 0, "amount": 0, "count": 0})
        for t in transactions:
            dow = t.timestamp.strftime("%a")
            dow_data[dow]["volume"] += t.quantity or 0
            dow_data[dow]["amount"] += t.amount
            dow_data[dow]["count"] += 1

        avg_dow_amount = np.mean([d["amount"] for d in dow_data.values()]) if dow_data else 1
        dow_pattern = {
            dow: round(data["amount"] / max(avg_dow_amount, 1), 2)
            for dow, data in dow_data.items()
        }

        # Monthly trend
        monthly = defaultdict(lambda: {"volume": 0, "amount": 0, "count": 0})
        for t in transactions:
            m = t.timestamp.strftime("%Y-%m")
            monthly[m]["volume"] += t.quantity or 0
            monthly[m]["amount"] += t.amount
            monthly[m]["count"] += 1

        monthly_trend = [
            {"month": m, "volume": d["volume"], "revenue": round(d["amount"], 2)}
            for m, d in sorted(monthly.items())
        ]

        # ── STA 244: Seasonal Decomposition ─────────────────────────────────
        seasonal_decomposition = None
        if len(monthly_trend) >= 6:
            monthly_volumes = np.array([m["volume"] for m in monthly_trend], dtype=float)
            trend_comp, seasonal_comp, irregular_comp = _seasonal_decompose_additive(
                monthly_volumes, period=12
            )
            seasonal_decomposition = {
                "method": "additive",
                "period": 12,
                "trend": [round(float(v), 2) for v in trend_comp[:len(monthly_trend)]],
                "seasonal": [round(float(v), 2) for v in seasonal_comp[:len(monthly_trend)]],
                "irregular": [round(float(v), 2) for v in irregular_comp[:len(monthly_trend)]],
            }

        # ── STA 244: Demand trend ───────────────────────────────────────────
        mid_date = period_end - timedelta(days=30)
        recent = [t for t in transactions if t.timestamp >= datetime.combine(mid_date, datetime.min.time())]
        older = [t for t in transactions if t.timestamp < datetime.combine(mid_date, datetime.min.time())]

        recent_vol = sum(t.quantity or 0 for t in recent)
        older_vol = sum(t.quantity or 0 for t in older)

        if older_vol > 0:
            change_pct = (recent_vol - older_vol) / older_vol * 100
            if change_pct > 5:
                demand_trend = "rising"
            elif change_pct < -5:
                demand_trend = "declining"
            else:
                demand_trend = "stable"
        else:
            demand_trend = "stable"
            change_pct = 0

        # ── ECO 201: Price Intelligence ─────────────────────────────────────
        avg_price = round(float(np.mean(unit_prices)), 2) if unit_prices else 0
        min_price = round(float(np.min(unit_prices)), 2) if unit_prices else 0
        max_price = round(float(np.max(unit_prices)), 2) if unit_prices else 0
        median_price = round(float(np.median(unit_prices)), 2) if unit_prices else 0
        price_std = round(float(np.std(unit_prices)), 2) if len(unit_prices) > 1 else 0
        price_cv = round(price_std / avg_price, 4) if avg_price > 0 else 0

        # Price trend
        if unit_prices and len(recent) > 10 and len(older) > 10:
            recent_prices = [t.unit_price for t in recent if t.unit_price and t.unit_price > 0]
            older_prices = [t.unit_price for t in older if t.unit_price and t.unit_price > 0]
            if recent_prices and older_prices:
                price_change = (np.mean(recent_prices) - np.mean(older_prices)) / np.mean(older_prices) * 100
                if price_change > 3:
                    price_trend = "rising"
                elif price_change < -3:
                    price_trend = "declining"
                else:
                    price_trend = "stable"
            else:
                price_trend = "stable"
                price_change = 0
        else:
            price_trend = "stable"
            price_change = 0

        # ── ECO 201/424: Price Elasticity of Demand ─────────────────────────
        elasticity_result = None
        if unit_prices and quantities and len(unit_prices) >= 20:
            p_arr = np.array(unit_prices[:len(quantities)])
            q_arr = np.array(quantities[:len(unit_prices)])
            elasticity_result = _estimate_price_elasticity(p_arr, q_arr)

        # ── ECO 201: Consumer Surplus Estimate ──────────────────────────────
        consumer_surplus = None
        if unit_prices and quantities and len(unit_prices) >= 10:
            p_arr = np.array(unit_prices)
            q_arr = np.array(quantities[:len(unit_prices)])
            mask = (p_arr > 0) & (q_arr > 0)
            if mask.sum() >= 10:
                # Linear demand: P = a - bQ  (OLS)
                X_cs = np.column_stack([np.ones(mask.sum()), q_arr[mask]])
                try:
                    beta_cs = np.linalg.lstsq(X_cs, p_arr[mask], rcond=None)[0]
                    a_est, b_est = float(beta_cs[0]), float(-beta_cs[1])
                    if b_est > 0 and a_est > avg_price:
                        consumer_surplus = _compute_consumer_surplus(
                            a_est, b_est, avg_price, float(np.mean(q_arr[mask]))
                        )
                except Exception:
                    pass

        # ── STA 244: Forecasting ────────────────────────────────────────────
        forecast = None
        seasonal_factor = round(avg_daily_volume / max(total_volume / max(days_in_period, 1), 1), 2)

        if tier in ("premium", "enterprise") and len(monthly_trend) >= 3:
            volumes = np.array([m["volume"] for m in monthly_trend], dtype=float)

            # Holt-Winters (STA 244)
            hw_result = _holt_winters_forecast(
                volumes,
                seasonal_period=min(12, max(3, len(volumes) // 2)),
                alpha=0.3, beta=0.1, gamma=0.2,
                n_forecast=3,
            )

            # ARIMA (STA 244)
            arima_result = _simple_arima_forecast(
                volumes, order=(1, 1, 0), n_forecast=3
            )

            # Simple exponential smoothing (original)
            alpha = 0.3
            smoothed = volumes[0]
            for v in volumes[1:]:
                smoothed = alpha * v + (1 - alpha) * smoothed

            residuals = [v - smoothed for v in volumes]
            std_err = float(np.std(residuals)) if len(residuals) > 1 else smoothed * 0.1

            # Ensemble forecast: weighted average of Holt-Winters and ARIMA
            hw_fc = hw_result["forecast"]
            arima_fc = arima_result["forecast"]
            ensemble = [
                round(0.5 * hw + 0.5 * ar, 0)
                for hw, ar in zip(hw_fc, arima_fc)
            ]

            forecast = {
                "forecasted_volume": round(smoothed, 0),
                "confidence_interval_low": round(max(0, smoothed - 1.96 * std_err), 0),
                "confidence_interval_high": round(smoothed + 1.96 * std_err, 0),
                "forecast_method": "ensemble_holt_winters_arima",
                "holt_winters_forecast": hw_fc,
                "arima_forecast": arima_fc,
                "arima_aic": arima_result.get("aic"),
                "arima_diagnostics": {
                    "ljung_box_q": arima_result.get("ljung_box_q"),
                },
                "ensemble_forecast": ensemble,
                "mape": round(float(np.mean(np.abs(np.array(residuals) / np.array(volumes)))) * 100, 1) if volumes else None,
                "seasonal_decomposition": seasonal_decomposition,
            }

        # ── Peak demand days ────────────────────────────────────────────────
        daily_volumes = defaultdict(float)
        for t in transactions:
            daily_volumes[t.timestamp.strftime("%Y-%m-%d")] += t.quantity or 0
        sorted_days = sorted(daily_volumes.items(), key=lambda x: x[1], reverse=True)
        peak_days = [d[0] for d in sorted_days[:5]]

        # ── Apply differential privacy ──────────────────────────────────────
        dp_total_volume = round(self.anonymizer.add_laplace_noise(total_volume, sensitivity=100), 0)
        dp_avg_daily = round(self.anonymizer.add_laplace_noise(avg_daily_volume, sensitivity=50), 2)

        # ── Build response ──────────────────────────────────────────────────
        response = {
            "product": "soko_pulse",
            "version": "2.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "data_freshness": datetime.now(timezone.utc).isoformat(),
            "k_anonymity_threshold": settings.K_ANONYMITY_THRESHOLD,
            "quality_score": min(1.0, k / 50),
            "confidence_level": min(1.0, len(transactions) / 100),
            "region": region or "national",
            "product_category": product_category,
            "product_name": product_name or "all",
            "time_period": f"{period_start} to {period_end}",
            "total_volume": max(0, dp_total_volume),
            "avg_daily_volume": max(0, dp_avg_daily),
            "demand_trend": demand_trend,
            "forecast": forecast,
            "price_intelligence": {
                "avg_price": avg_price,
                "min_price": min_price,
                "max_price": max_price,
                "median_price": median_price,
                "price_std": price_std,
                "price_cv": price_cv,
                "price_trend": price_trend,
                "price_change_pct": round(price_change, 1),
                "unit": "KES",
                # ECO 201: Price elasticity of demand
                "price_elasticity": elasticity_result,
                # ECO 201: Consumer surplus (welfare measure)
                "consumer_surplus_estimate": consumer_surplus,
                # STA 342: Confidence interval for average price
                "confidence_interval_95pct": (
                    ConfidenceIntervalCalculator.mean_ci(
                        [float(p) for p in unit_prices], confidence=0.95
                    ).to_dict() if len(unit_prices) > 1 else None
                ),
            },
            "day_of_week_pattern": dow_pattern,
            "monthly_trend": monthly_trend,
            "peak_demand_days": peak_days,
            "vendor_count": k,
            "stockout_frequency": None,  # Would need inventory data
            "seasonal_factor": seasonal_factor,
            "seasonal_events": [],
            "users_included": k,
            "data_points": len(transactions),
            "tier": tier,
            # STA 342: Statistical significance testing
            "statistical_tests": {
                "demand_trend_significance": self._test_demand_significance(
                    recent, older
                ) if recent and older else None,
                "methodology": "STA 342 — Test of Hypothesis",
            },
        }

        # Cache
        await intelligence_cache.set(
            "soko_pulse", response,
            category=product_category,
            product=product_name,
            region=region,
            start=str(period_start),
            end=str(period_end),
            tier=tier,
        )

        logger.info(
            "soko_pulse_generated",
            category=product_category,
            region=region,
            k=k,
            transactions=len(transactions),
        )

        return response

    @staticmethod
    def _test_demand_significance(
        recent: list,
        older: list,
    ) -> Optional[Dict[str, Any]]:
        """
        Test whether demand change is statistically significant.

        Uses Welch's t-test (STA 342) to test whether recent period
        transaction amounts differ significantly from older period.
        """
        recent_amounts = [t.amount for t in recent]
        older_amounts = [t.amount for t in older]

        if len(recent_amounts) < 2 or len(older_amounts) < 2:
            return None

        tester = HypothesisTester(alpha=0.05)
        result = tester.two_sample_t_test(recent_amounts, older_amounts)

        return {
            "test": "welch_t_test",
            "p_value": round(result.p_value, 6),
            "significant": result.reject_null,
            "effect_size": round(result.effect_size or 0, 4),
            "confidence_interval": (
                [round(result.confidence_interval[0], 4),
                 round(result.confidence_interval[1], 4)]
                if result.confidence_interval else None
            ),
            "interpretation": result.interpretation,
        }
