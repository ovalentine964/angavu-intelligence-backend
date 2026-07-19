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
  exchange rate pass-through, gravity model for trade flows,
  comparative advantage (Ricardian model), AfCFTA tariff analysis,
  balance of payments, exchange rate modeling

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
from app.services.econometric_engine import ARIMAModel, CointegrationTester, VARModel
from app.services.game_theory import BertrandDuopoly, CournotDuopoly
from app.services.intelligence.cache import intelligence_cache
from app.services.research.confidence_intervals import BootstrapCI, ConfidenceIntervalCalculator
from app.services.research.hypothesis_testing import HypothesisTester
from app.services.statistical_foundation import (
    ClusterAnalyzer,
    bootstrap,
    kde_estimator,
)

# ── ML Layer: XGBoost demand forecasting (complements classical stats) ──
try:
    from app.services.ml.feature_engineering import FeatureEngineer
    from app.services.ml.xgboost_service import XGBoostService
    _xgb_service = XGBoostService()
    _ml_available = True
except ImportError:
    _ml_available = False
    _xgb_service = None

logger = structlog.get_logger(__name__)
settings = get_settings()


# ─────────────────────────────────────────────────────────────────────────────
# STA 244 — Time Series Analysis & Forecasting helpers
# ─────────────────────────────────────────────────────────────────────────────

def _seasonal_decompose_additive(
    series: np.ndarray, period: int = 7
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
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
) -> dict[str, Any]:
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
    series: np.ndarray, order: tuple[int, int, int] = (1, 1, 0), n_forecast: int = 4
) -> dict[str, Any]:
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
) -> dict[str, float]:
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
        product_name: str | None = None,
        region: str | None = None,
        period_start: date | None = None,
        period_end: date | None = None,
        tier: str = "standard",
        buyer_id: str | None = None,
    ) -> dict[str, Any] | None:
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

            # ARIMA (STA 244) — using full ARIMAModel from econometric_engine
            arima_model = ARIMAModel(p=1, d=1, q=0)
            arima_fit = arima_model.fit(volumes)
            arima_fc_result = arima_model.forecast(steps=3)
            arima_result = {
                "forecast": [round(f["forecast"]) for f in arima_fc_result["forecasts"]],
                "aic": arima_fit.get("aic"),
                "ljung_box_q": arima_fit.get("ljung_box", {}).get("Q_statistic"),
            }

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

            # ── ML Layer: XGBoost demand forecast ──────────────────────────
            # Complements classical ensemble with non-linear feature interactions.
            # XGBoost captures category×location×temporal patterns that
            # Holt-Winters and ARIMA cannot model.
            if _ml_available and _xgb_service and len(transactions) >= 20:
                try:
                    ml_features = FeatureEngineer.extract_all_features(transactions)
                    ml_demand = _xgb_service.predict_demand(ml_features)
                    if ml_demand.get("available"):
                        forecast["ml_xgboost_forecast"] = {
                            "predicted_volume": ml_demand["predicted_volume"],
                            "confidence": ml_demand["confidence"],
                            "shap_explanation": ml_demand.get("shap_explanation"),
                            "note": "XGBoost ML complement to classical ensemble",
                        }
                        # Update ensemble to include ML if confidence is high enough
                        if ml_demand["confidence"] >= 0.5:
                            ml_pred = ml_demand["predicted_volume"]
                            # 40% HW, 30% ARIMA, 30% XGBoost ensemble
                            ml_ensemble = round(
                                0.4 * hw_fc[0] + 0.3 * arima_fc[0] + 0.3 * ml_pred, 0
                            ) if hw_fc and arima_fc else ensemble[0]
                            forecast["ml_enhanced_ensemble"] = [ml_ensemble]
                            forecast["forecast_method"] = "ml_enhanced_ensemble_holt_winters_arima_xgboost"
                except Exception as e:
                    logger.debug("ml_demand_forecast_failed", error=str(e))

        # ── Peak demand days ────────────────────────────────────────────────
        daily_volumes = defaultdict(float)
        for t in transactions:
            daily_volumes[t.timestamp.strftime("%Y-%m-%d")] += t.quantity or 0
        sorted_days = sorted(daily_volumes.items(), key=lambda x: x[1], reverse=True)
        peak_days = [d[0] for d in sorted_days[:5]]

        # ── STA 244: VAR Model for multi-market dynamics ────────────────
        var_analysis = None
        if tier in ("premium", "enterprise") and len(monthly_trend) >= 4:
            try:
                volumes_arr = np.array([m["volume"] for m in monthly_trend], dtype=float)
                revenues_arr = np.array([m["revenue"] for m in monthly_trend], dtype=float)
                if len(volumes_arr) >= 4:
                    var_data = np.column_stack([volumes_arr, revenues_arr])
                    var_model = VARModel(p=1)
                    var_fit = var_model.fit(var_data, variable_names=["volume", "revenue"])
                    if "error" not in var_fit:
                        irf = var_model.impulse_response(periods=6)
                        var_analysis = {
                            "model_order": var_fit["order"],
                            "equations": var_fit["equations"],
                            "granger_causality": var_fit.get("granger_causality", []),
                            "aic": var_fit["aic"],
                            "bic": var_fit["bic"],
                            "impulse_response": irf.get("impulse_responses", []),
                        }
            except Exception as e:
                logger.debug("var_analysis_failed", error=str(e))

        # ── STA 244: Cointegration for cross-border price analysis ──────
        cointegration_analysis = None
        if tier == "enterprise" and unit_prices and len(unit_prices) >= 20:
            try:
                mid = len(unit_prices) // 2
                prices_a = np.array(unit_prices[:mid], dtype=float)
                prices_b = np.array(unit_prices[mid:2*mid], dtype=float)
                if len(prices_a) >= 10 and len(prices_b) >= 10:
                    cg_tester = CointegrationTester()
                    cg_result = cg_tester.engle_granger(prices_a, prices_b)
                    if "error" not in cg_result:
                        cointegration_analysis = {
                            "test": cg_result["engle_granger_test"],
                            "cointegrating_vector": cg_result["cointegrating_vector"],
                            "error_correction_model": cg_result.get("error_correction_model"),
                            "interpretation": cg_result["engle_granger_test"]["conclusion"],
                        }
            except Exception as e:
                logger.debug("cointegration_analysis_failed", error=str(e))

        # ── STA 442: Cluster Analysis for market segmentation ───────────
        market_segmentation = None
        if tier in ("premium", "enterprise") and len(transactions) >= 30:
            try:
                trader_data = defaultdict(lambda: {"prices": [], "quantities": [], "revenue": 0, "count": 0})
                for t in transactions:
                    uid = str(t.user_id)
                    if t.unit_price and t.unit_price > 0:
                        trader_data[uid]["prices"].append(t.unit_price)
                    trader_data[uid]["quantities"].append(t.quantity or 0)
                    trader_data[uid]["revenue"] += t.amount
                    trader_data[uid]["count"] += 1

                feature_rows = []
                for uid, d in trader_data.items():
                    if len(d["prices"]) >= 3:
                        feature_rows.append([
                            float(np.mean(d["prices"])),
                            float(np.sum(d["quantities"])),
                            d["revenue"],
                            d["count"],
                        ])

                if len(feature_rows) >= 10:
                    seg_data = np.array(feature_rows, dtype=float)
                    seg_result = ClusterAnalyzer.segment_market(
                        seg_data,
                        feature_names=["avg_price", "total_volume", "total_revenue", "txn_count"],
                        max_k=min(5, len(feature_rows) // 3),
                    )
                    market_segmentation = {
                        "optimal_k": seg_result["optimal_k"],
                        "silhouette_score": seg_result["silhouette_score"],
                        "segments": [
                            {
                                "segment_id": s["segment_id"],
                                "size": s["size"],
                                "proportion": s["proportion"],
                                "profile": s["profile"],
                            }
                            for s in seg_result["segments"]
                        ],
                    }
            except Exception as e:
                logger.debug("market_segmentation_failed", error=str(e))

        # ── ECO 422: Competition analysis (Cournot & Bertrand) ──────────
        competition_analysis = None
        if tier in ("premium", "enterprise") and avg_price > 0:
            try:
                demand_intercept = avg_price * 2.5
                demand_slope = 0.001
                est_marginal_cost = avg_price * 0.6

                cournot_result = CournotDuopoly.solve_linear(
                    demand_intercept=demand_intercept,
                    demand_slope=demand_slope,
                    marginal_cost_1=est_marginal_cost,
                    marginal_cost_2=est_marginal_cost * 1.1,
                )

                bertrand_result = BertrandDuopoly.solve_differentiated(
                    demand_intercept=demand_intercept,
                    own_price_sensitivity=1.0 / avg_price,
                    cross_price_sensitivity=0.3 / avg_price,
                    marginal_cost_1=est_marginal_cost,
                    marginal_cost_2=est_marginal_cost * 1.1,
                )

                competition_analysis = {
                    "cournot_quantity_competition": cournot_result.to_dict(),
                    "bertrand_price_competition": bertrand_result.to_dict(),
                    "estimated_marginal_cost": round(est_marginal_cost, 2),
                    "market_structure": bertrand_result.to_dict()["market_structure"],
                }
            except Exception as e:
                logger.debug("competition_analysis_failed", error=str(e))

        # ── ECO 305/313: Cross-border trade intelligence ───────────────
        cross_border_intelligence = None
        if tier == "enterprise":
            try:
                # Default to Kenya-Uganda cross-border analysis (largest EAC corridor)
                origin = "KE"
                dest = "UG"
                # Estimate current tariff rate for this product category
                tariff_rates = {
                    "food": 0.25, "household": 0.30, "health": 0.10,
                    "clothing": 0.35, "electronics": 0.25, "beauty": 0.30,
                    "agriculture": 0.15, "services": 0.0, "other": 0.25,
                }
                tariff = tariff_rates.get(product_category, 0.25)
                est_trade_volume = float(total_volume * avg_price) if avg_price > 0 else 1000000

                # Use unit_prices for PPP if available
                domestic_prices = [float(p) for p in unit_prices[:50]] if unit_prices else None
                # Estimate foreign prices as domestic * 0.85 (PPP approximation)
                foreign_prices = [p * 0.85 for p in domestic_prices] if domestic_prices else None

                cross_border_intelligence = CrossBorderTradeIntelligence.full_cross_border_analysis(
                    origin=origin,
                    destination=dest,
                    product_category=product_category,
                    domestic_prices=domestic_prices,
                    foreign_prices=foreign_prices,
                    current_tariff_rate=tariff,
                    current_trade_volume=est_trade_volume,
                )
            except Exception as e:
                logger.debug("cross_border_intelligence_failed", error=str(e))

        # ── Apply differential privacy ──────────────────────────────────────
        dp_total_volume = round(self.anonymizer.add_laplace_noise(total_volume, sensitivity=100), 0)
        dp_avg_daily = round(self.anonymizer.add_laplace_noise(avg_daily_volume, sensitivity=50), 2)

        # ── Build response ──────────────────────────────────────────────────
        response = {
            "product": "soko_pulse",
            "version": "2.0",
            "generated_at": datetime.now(UTC).isoformat(),
            "data_freshness": datetime.now(UTC).isoformat(),
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
                # STA 444: Bootstrap CI on average price (non-parametric)
                "bootstrap_ci": (
                    BootstrapCI.compute(
                        [float(p) for p in unit_prices],
                        statistic="mean", confidence=0.95, n_bootstrap=5000,
                    ).to_dict() if len(unit_prices) >= 10 else None
                ),
            },
            "day_of_week_pattern": dow_pattern,
            "monthly_trend": monthly_trend,
            "peak_demand_days": peak_days,
            # STA 244: VAR model for multi-market dynamics
            "var_multi_market_dynamics": var_analysis,
            # STA 244: Cointegration for cross-border price analysis
            "cointegration_cross_border": cointegration_analysis,
            # STA 442: Cluster analysis for market segmentation
            # STA 444: Non-parametric analysis
            "nonparametric_analysis": self._run_nonparametric_analysis(
                transactions, unit_prices, quantities, tier, user_ids,
            ),
            "market_segmentation": market_segmentation,
            # ECO 422: Competition analysis (Cournot & Bertrand)
            "competition_analysis": competition_analysis,
            # ECO 305/313: Cross-border trade intelligence (enterprise only)
            "cross_border_trade": cross_border_intelligence,
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

    def _run_nonparametric_analysis(
        self,
        transactions: list,
        unit_prices: list,
        quantities: list,
        tier: str,
        user_ids: list | None,
    ) -> dict[str, Any] | None:
        """
        Run non-parametric statistical analysis (STA 444).

        Applies Kruskal-Wallis, Mann-Whitney, KDE, bootstrap CI,
        and Spearman rank correlation — essential for informal economy
        data which is non-normal, small-sample, and outlier-heavy.
        """
        if tier == "basic" or len(transactions) < 20:
            return None

        result: dict[str, Any] = {}

        # ── STA 444: KDE for price distribution ─────────────────────────────
        if unit_prices and len(unit_prices) >= 20:
            try:
                prices_arr = np.array(unit_prices, dtype=float)
                grid, density = kde_estimator.gaussian_kde(prices_arr)
                mode_idx = int(np.argmax(density))
                result["kde_price_distribution"] = {
                    "description": "Non-parametric price density (Gaussian KDE)",
                    "mode_price": round(float(grid[mode_idx]), 2),
                    "bandwidth": round(float(
                        0.9 * min(
                            np.std(prices_arr),
                            (np.percentile(prices_arr, 75) - np.percentile(prices_arr, 25)) / 1.34,
                        ) * len(prices_arr) ** (-0.2)
                    ), 4),
                    "n_observations": len(prices_arr),
                    "multimodality": kde_estimator.detect_multimodality(prices_arr),
                }
            except Exception as e:
                logger.debug("kde_price_distribution_failed", error=str(e))

        # ── STA 444: Kruskal-Wallis — compare prices across markets ────────
        if user_ids and len(unit_prices) >= 30:
            try:
                # Group prices by user (proxy for market/supplier)
                user_prices: dict[str, list] = defaultdict(list)
                for t in transactions:
                    if t.unit_price and t.unit_price > 0:
                        user_prices[str(t.user_id)].append(float(t.unit_price))

                # Need 3+ groups with 5+ observations each
                valid_groups = [
                    p for p in user_prices.values() if len(p) >= 5
                ]
                if len(valid_groups) >= 3:
                    tester = HypothesisTester(alpha=0.05)
                    kw_result = tester.kruskal_wallis(valid_groups)
                    result["kruskal_wallis_price_comparison"] = {
                        "test": "Kruskal-Wallis H",
                        "null_hypothesis": "All markets/suppliers have the same price distribution",
                        "test_statistic": round(kw_result.test_statistic, 4),
                        "p_value": round(kw_result.p_value, 6),
                        "significant": kw_result.reject_null,
                        "effect_size_epsilon_sq": round(kw_result.effect_size or 0, 4),
                        "n_groups": len(valid_groups),
                        "n_total": sum(len(g) for g in valid_groups),
                        "interpretation": kw_result.interpretation,
                        "method": "STA 444 — Non-parametric ANOVA (no normality assumption)",
                    }
            except Exception as e:
                logger.debug("kruskal_wallis_price_failed", error=str(e))

        # ── STA 444: Mann-Whitney U — compare two market segments ──────────
        if len(unit_prices) >= 20:
            try:
                prices_arr = np.array(unit_prices, dtype=float)
                median_price = float(np.median(prices_arr))
                above_median = prices_arr[prices_arr >= median_price]
                below_median = prices_arr[prices_arr < median_price]
                if len(above_median) >= 5 and len(below_median) >= 5:
                    tester = HypothesisTester(alpha=0.05)
                    mw_result = tester.mann_whitney_u(
                        above_median.tolist(), below_median.tolist()
                    )
                    result["mann_whitney_price_segments"] = {
                        "test": "Mann-Whitney U",
                        "null_hypothesis": "Price distributions of high-value and low-value segments are the same",
                        "test_statistic": round(mw_result.test_statistic, 4),
                        "p_value": round(mw_result.p_value, 6),
                        "significant": mw_result.reject_null,
                        "effect_size": round(mw_result.effect_size or 0, 4),
                        "high_segment_median": round(float(np.median(above_median)), 2),
                        "low_segment_median": round(float(np.median(below_median)), 2),
                        "interpretation": mw_result.interpretation,
                        "method": "STA 444 — Non-parametric two-sample test",
                    }
            except Exception as e:
                logger.debug("mann_whitney_price_failed", error=str(e))

        # ── STA 444: Spearman rank correlation — price vs demand ───────────
        if unit_prices and quantities and len(unit_prices) >= 20:
            try:
                p_arr = np.array(unit_prices[:len(quantities)], dtype=float)
                q_arr = np.array(quantities[:len(unit_prices)], dtype=float)
                mask = (p_arr > 0) & (np.array(q_arr) > 0)
                if mask.sum() >= 20:
                    from scipy import stats as sp_stats
                    rho, p_val = sp_stats.spearmanr(p_arr[mask], q_arr[mask])
                    result["spearman_price_demand_correlation"] = {
                        "test": "Spearman rank correlation",
                        "null_hypothesis": "No monotonic relationship between price and demand",
                        "rho": round(float(rho), 4),
                        "p_value": round(float(p_val), 6),
                        "significant": p_val < 0.05,
                        "direction": "positive" if rho > 0 else "negative",
                        "strength": (
                            "strong" if abs(rho) > 0.7
                            else "moderate" if abs(rho) > 0.4
                            else "weak"
                        ),
                        "n_observations": int(mask.sum()),
                        "interpretation": (
                            f"{'Significant' if p_val < 0.05 else 'Non-significant'} "
                            f"{'positive' if rho > 0 else 'negative'} monotonic "
                            f"relationship (ρ={rho:.3f})"
                        ),
                        "method": "STA 444 — Rank-based correlation (no linearity assumption)",
                    }
            except Exception as e:
                logger.debug("spearman_correlation_failed", error=str(e))

        # ── STA 444: Bootstrap CI on forecast ──────────────────────────────
        if unit_prices and len(unit_prices) >= 30:
            try:
                prices_arr = np.array(unit_prices, dtype=float)
                boot_ci = bootstrap.percentile_ci(
                    prices_arr, np.mean, n_bootstrap=5000, confidence=0.95,
                )
                result["bootstrap_forecast_ci"] = {
                    "estimate": boot_ci["estimate"],
                    "ci_lower": boot_ci["ci_lower"],
                    "ci_upper": boot_ci["ci_upper"],
                    "bootstrap_se": boot_ci["bootstrap_se"],
                    "confidence": 0.95,
                    "method": "STA 444 — Bootstrap percentile CI (distribution-free)",
                }
            except Exception as e:
                logger.debug("bootstrap_forecast_ci_failed", error=str(e))

        return result if result else None

    @staticmethod
    def _test_demand_significance(
        recent: list,
        older: list,
    ) -> dict[str, Any] | None:
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


# ─────────────────────────────────────────────────────────────────────────────
# ECO 305/313 — International Economics: Cross-Border Trade Intelligence
# ─────────────────────────────────────────────────────────────────────────────


class CrossBorderTradeIntelligence:
    """
    Cross-border trade intelligence for EAC informal markets.

    Driven by ECO 305 § Introduction to International Economics and
    ECO 313 § International Economics:

    - Gravity Model (Tinbergen, 1962): Trade flow between countries i
      and j is proportional to their economic sizes (GDP) and inversely
      proportional to the distance between them:
        T_ij = A × (GDP_i × GDP_j) / D_ij^β
      In log-log form: ln(T_ij) = α + β₁ln(GDP_i) + β₂ln(GDP_j) - β₃ln(D_ij) + ε

    - Comparative Advantage (Ricardo, 1817): A country exports goods in
      which it has the lowest opportunity cost. Revealed comparative
      advantage (RCA) index measures this empirically:
        RCA = (X_ij/X_i) / (X_wj/X_w) where X = exports, j = commodity
      RCA > 1 → country has comparative advantage in commodity j.

    - Exchange Rate Pass-Through (ERPT): The degree to which exchange
      rate changes are transmitted to domestic prices:
        ΔP_domestic = α + β × ΔER + ε
      β = ERPT coefficient (0 = no pass-through, 1 = full pass-through)

    - AfCFTA Integration: African Continental Free Trade Area aims to
      reduce tariffs on 90% of goods. For informal cross-border traders,
      this means reduced barriers and expanded market access.

    - Purchasing Power Parity (PPP): Long-run equilibrium where
      identical goods have the same price across countries:
        P_KES = P_UGX × ER(KES/UGX)
      Deviations from PPP indicate arbitrage opportunities.

    Data Sources:
    - Kenya National Bureau of Statistics (KNBS)
    - Uganda Bureau of Statistics (UBOS)
    - Tanzania National Bureau of Statistics (NBS)
    - World Bank WITS (World Integrated Trade Solution)
    - UN COMTRADE

    References:
    - Tinbergen, J. (1962). Shaping the World Economy. Twentieth Century Fund.
    - Ricardo, D. (1817). On the Principles of Political Economy and Taxation.
    - Anderson, J.E. & van Wincoop, E. (2003). "Gravity with Gravitas." AER.
    - Krugman, P. (1980). "Scale Economies, Product Differentiation, and the
      Pattern of Trade." AER.
    """

    # EAC member states with approximate coordinates (lat, lon) and GDP (USD billions, 2024 est.)
    EAC_COUNTRIES = {
        "KE": {"name": "Kenya", "lat": -1.29, "lon": 36.82, "gdp_billion_usd": 113.0, "currency": "KES"},
        "UG": {"name": "Uganda", "lat": 0.35, "lon": 32.58, "gdp_billion_usd": 45.5, "currency": "UGX"},
        "TZ": {"name": "Tanzania", "lat": -6.17, "lon": 35.74, "gdp_billion_usd": 75.7, "currency": "TZS"},
        "RW": {"name": "Rwanda", "lat": -1.94, "lon": 29.87, "gdp_billion_usd": 14.1, "currency": "RWF"},
        "BI": {"name": "Burundi", "lat": -3.37, "lon": 29.36, "gdp_billion_usd": 3.1, "currency": "BIF"},
        "SS": {"name": "South Sudan", "lat": 4.86, "lon": 31.58, "gdp_billion_usd": 5.3, "currency": "SSP"},
        "CD": {"name": "DRC", "lat": -4.32, "lon": 15.31, "gdp_billion_usd": 66.4, "currency": "CDF"},
    }

    # Approximate distances between capital cities (km)
    DISTANCE_MATRIX = {
        ("KE", "UG"): 660, ("KE", "TZ"): 740, ("KE", "RW"): 1050,
        ("KE", "BI"): 1450, ("KE", "SS"): 1100, ("KE", "CD"): 1700,
        ("UG", "TZ"): 1100, ("UG", "RW"): 510, ("UG", "BI"): 850,
        ("UG", "SS"): 650, ("UG", "CD"): 1600,
        ("TZ", "RW"): 1100, ("TZ", "BI"): 1300, ("TZ", "CD"): 1900,
        ("RW", "BI"): 230, ("RW", "CD"): 1200,
        ("BI", "SS"): 1300, ("BI", "CD"): 1100,
        ("SS", "CD"): 1400,
    }

    # AfCFTA tariff reduction schedule (% of base tariff)
    AFFECTED_TARIFF_REDUCTION = {
        "90pct_goods": 0.0,      # 90% of goods: tariff-free
        "sensitive_7pct": 0.5,   # 7% sensitive goods: 50% reduction
        "exclusion_3pct": 1.0,   # 3% exclusion list: no reduction
    }

    @classmethod
    def gravity_model_estimate(
        cls,
        origin: str,
        destination: str,
        product_category: str,
        observed_flow: float | None = None,
    ) -> dict[str, Any]:
        """
        Estimate bilateral trade flow using the gravity model.

        Driven by ECO 305 § Gravity Model of Trade:
        ln(T_ij) = α + β₁ln(GDP_i) + β₂ln(GDP_j) - β₃ln(D_ij) + ε

        Standard estimates (from meta-analysis):
        β₁ ≈ 0.8-1.0 (GDP elasticity of exporter)
        β₂ ≈ 0.8-1.0 (GDP elasticity of importer)
        β₃ ≈ 0.6-1.2 (distance elasticity)

        Args:
            origin: origin country code (e.g., "KE")
            destination: destination country code (e.g., "UG")
            product_category: product category for trade
            observed_flow: actual trade flow value (optional, for residual)

        Returns:
            Dict with predicted flow, gravity components, and trade potential
        """
        origin = origin.upper()
        dest = destination.upper()

        if origin not in cls.EAC_COUNTRIES or dest not in cls.EAC_COUNTRIES:
            return {"error": f"Unknown country code: {origin} or {dest}"}

        gdp_i = cls.EAC_COUNTRIES[origin]["gdp_billion_usd"]
        gdp_j = cls.EAC_COUNTRIES[dest]["gdp_billion_usd"]

        # Get distance (symmetric)
        key = (origin, dest) if (origin, dest) in cls.DISTANCE_MATRIX else (dest, origin)
        distance = cls.DISTANCE_MATRIX.get(key, 2000)  # Default 2000km

        # Log-log gravity model with standard coefficients
        alpha = -2.5  # Intercept
        beta_gdp_exporter = 0.9  # GDP elasticity of exporter
        beta_gdp_importer = 0.9  # GDP elasticity of importer
        beta_distance = 0.8     # Distance elasticity

        log_flow = (
            alpha
            + beta_gdp_exporter * np.log(max(gdp_i, 1))
            + beta_gdp_importer * np.log(max(gdp_j, 1))
            - beta_distance * np.log(max(distance, 1))
        )
        predicted_flow = np.exp(log_flow)

        # Trade potential (ratio of actual to predicted)
        trade_potential = None
        residual = None
        if observed_flow is not None:
            trade_potential = round(observed_flow / max(predicted_flow, 1e-6), 4)
            residual = round(np.log(max(observed_flow, 1e-6)) - log_flow, 4)

        # Border effect (EAC common market reduces trade barriers)
        border_bonus = 1.35  # EAC integration bonus ~35%
        adjusted_flow = predicted_flow * border_bonus

        return {
            "origin": origin,
            "origin_name": cls.EAC_COUNTRIES[origin]["name"],
            "destination": dest,
            "destination_name": cls.EAC_COUNTRIES[dest]["name"],
            "product_category": product_category,
            "gravity_model": {
                "gdp_origin_billion_usd": gdp_i,
                "gdp_destination_billion_usd": gdp_j,
                "distance_km": distance,
                "predicted_flow_million_usd": round(predicted_flow, 2),
                "adjusted_flow_million_usd": round(adjusted_flow, 2),
                "eac_border_bonus": border_bonus,
                "coefficients": {
                    "intercept": alpha,
                    "gdp_exporter_elasticity": beta_gdp_exporter,
                    "gdp_importer_elasticity": beta_gdp_importer,
                    "distance_elasticity": beta_distance,
                },
            },
            "trade_potential": trade_potential,
            "residual": residual,
            "interpretation": cls._interpret_gravity(
                trade_potential, origin, dest
            ),
            "method": "ECO 305 — Gravity Model (Tinbergen, 1962)",
        }

    @classmethod
    def comparative_advantage_index(
        cls,
        country: str,
        product_category: str,
        domestic_share: float,
        world_share: float,
    ) -> dict[str, Any]:
        """
        Compute Revealed Comparative Advantage (RCA) index.

        Driven by ECO 313 § Comparative Advantage:
        RCA = (X_ij / X_i) / (X_wj / X_w)

        where X_ij = country i's exports of commodity j
              X_i = country i's total exports
              X_wj = world exports of commodity j
              X_w = world total exports

        RCA > 1 → country has revealed comparative advantage
        RCA < 1 → country has revealed comparative disadvantage

        Balassa (1965) definition, widely used in trade policy analysis.

        Args:
            country: country code
            product_category: commodity/product category
            domestic_share: share of this product in country's total trade (0-1)
            world_share: share of this product in world trade (0-1)

        Returns:
            Dict with RCA index and interpretation
        """
        country = country.upper()
        if country not in cls.EAC_COUNTRIES:
            return {"error": f"Unknown country: {country}"}

        rca = domestic_share / max(world_share, 1e-10)

        # Interpretation
        if rca > 2.5:
            strength = "strong_comparative_advantage"
        elif rca > 1.0:
            strength = "comparative_advantage"
        elif rca > 0.5:
            strength = "comparative_disadvantage"
        else:
            strength = "strong_comparative_disadvantage"

        # Opportunity cost interpretation (Ricardian model)
        if rca > 1:
            opportunity_cost = "low"  # Low opportunity cost → export
            trade_recommendation = "export"
        else:
            opportunity_cost = "high"  # High opportunity cost → import
            trade_recommendation = "import"

        return {
            "country": country,
            "country_name": cls.EAC_COUNTRIES[country]["name"],
            "product_category": product_category,
            "rca_index": round(rca, 4),
            "domestic_share": round(domestic_share, 4),
            "world_share": round(world_share, 4),
            "strength": strength,
            "opportunity_cost": opportunity_cost,
            "trade_recommendation": trade_recommendation,
            "interpretation": (
                f"{cls.EAC_COUNTRIES[country]['name']} has {'a' if rca > 1 else 'no'} "
                f"revealed comparative advantage in {product_category} "
                f"(RCA = {rca:.2f}). "
                f"Recommendation: {trade_recommendation}."
            ),
            "method": "ECO 313 — Revealed Comparative Advantage (Balassa, 1965)",
        }

    @classmethod
    def exchange_rate_pass_through(
        cls,
        origin: str,
        destination: str,
        exchange_rate_changes: list[float],
        domestic_price_changes: list[float],
    ) -> dict[str, Any]:
        """
        Estimate exchange rate pass-through to domestic prices.

        Driven by ECO 313 § Exchange Rate Economics:
        ΔP_domestic = α + β × ΔER + ε

        where β = ERPT coefficient:
        - β = 0: no pass-through (prices insulated from FX)
        - β = 1: full pass-through (FX fully reflected in prices)
        - 0 < β < 1: partial pass-through (typical for EAC)

        Uses OLS with heteroskedasticity-robust SE (White/HC1).

        Args:
            origin: origin country code
            destination: destination country code
            exchange_rate_changes: list of % changes in bilateral exchange rate
            domestic_price_changes: list of % changes in domestic prices

        Returns:
            Dict with ERPT coefficient, SE, R², and interpretation
        """
        er = np.array(exchange_rate_changes, dtype=float)
        dp = np.array(domestic_price_changes, dtype=float)

        if len(er) < 5 or len(dp) < 5:
            return {"error": "Need at least 5 observations for ERPT estimation"}

        # OLS: dp = α + β·er
        X = np.column_stack([np.ones(len(er)), er])
        try:
            beta_hat = np.linalg.lstsq(X, dp, rcond=None)[0]
        except np.linalg.LinAlgError:
            return {"error": "OLS estimation failed"}

        residuals = dp - X @ beta_hat
        n, k = X.shape
        if n <= k:
            return {"error": "Insufficient degrees of freedom"}

        # HC1 robust SE
        bread = np.linalg.inv(X.T @ X)
        meat = X.T @ np.diag(residuals ** 2) @ X
        robust_var = bread @ meat @ bread * (n / (n - k))
        se = np.sqrt(np.diag(robust_var))

        # R²
        ss_res = np.sum(residuals ** 2)
        ss_tot = np.sum((dp - np.mean(dp)) ** 2)
        r_sq = 1 - ss_res / max(ss_tot, 1e-10)

        erpt_coeff = float(beta_hat[1])
        erpt_se = float(se[1])
        t_stat = erpt_coeff / max(erpt_se, 1e-10)

        # 95% CI
        from scipy import stats as sp_stats
        t_crit = sp_stats.t.ppf(0.975, max(n - k, 1))
        ci_lower = erpt_coeff - t_crit * erpt_se
        ci_upper = erpt_coeff + t_crit * erpt_se

        # Interpretation
        if erpt_coeff > 0.8:
            erpt_level = "high"
            policy_implication = "FX movements significantly affect consumer prices"
        elif erpt_coeff > 0.4:
            erpt_level = "moderate"
            policy_implication = "Partial FX transmission to consumer prices"
        else:
            erpt_level = "low"
            policy_implication = "Prices largely insulated from FX movements"

        return {
            "origin": origin,
            "destination": destination,
            "erpt_coefficient": round(erpt_coeff, 4),
            "standard_error": round(erpt_se, 4),
            "t_statistic": round(t_stat, 4),
            "ci_95": (round(ci_lower, 4), round(ci_upper, 4)),
            "r_squared": round(r_sq, 4),
            "n_observations": n,
            "erpt_level": erpt_level,
            "policy_implication": policy_implication,
            "interpretation": (
                f"A 1% depreciation of {origin}/{destination} exchange rate "
                f"leads to a {erpt_coeff:.2f}% change in domestic prices "
                f"(ERPT = {erpt_coeff:.2f}, {'significant' if abs(t_stat) > 2 else 'not significant'})."
            ),
            "method": "ECO 313 — Exchange Rate Pass-Through (OLS with HC1 SE)",
        }

    @classmethod
    def ppp_deviation(
        cls,
        origin: str,
        destination: str,
        domestic_price: float,
        foreign_price: float,
        exchange_rate: float,
    ) -> dict[str, Any]:
        """
        Compute Purchasing Power Parity deviation.

        Driven by ECO 313 § Purchasing Power Parity:
        PPP exchange rate = P_domestic / P_foreign
        Deviation = (Actual ER - PPP ER) / PPP ER × 100

        Positive deviation → domestic currency overvalued
        Negative deviation → domestic currency undervalued

        Args:
            origin: domestic country code
            destination: foreign country code
            domestic_price: price of representative basket in domestic currency
            foreign_price: price of representative basket in foreign currency
            exchange_rate: actual exchange rate (domestic per foreign)

        Returns:
            Dict with PPP rate, deviation, and arbitrage signal
        """
        ppp_rate = domestic_price / max(foreign_price, 1e-10)
        deviation_pct = (exchange_rate - ppp_rate) / max(ppp_rate, 1e-10) * 100

        # Arbitrage signal
        if abs(deviation_pct) > 20:
            arbitrage_signal = "strong"
        elif abs(deviation_pct) > 10:
            arbitrage_signal = "moderate"
        else:
            arbitrage_signal = "weak"

        if deviation_pct > 10:
            direction = "domestic_overvalued"
            trade_signal = "import"  # Cheaper to import
        elif deviation_pct < -10:
            direction = "domestic_undervalued"
            trade_signal = "export"  # Cheaper to export
        else:
            direction = "near_equilibrium"
            trade_signal = "neutral"

        return {
            "origin": origin,
            "destination": destination,
            "domestic_price": domestic_price,
            "foreign_price": foreign_price,
            "actual_exchange_rate": exchange_rate,
            "ppp_exchange_rate": round(ppp_rate, 4),
            "deviation_pct": round(deviation_pct, 2),
            "direction": direction,
            "arbitrage_signal": arbitrage_signal,
            "trade_signal": trade_signal,
            "interpretation": (
                f"{'Overvalued' if deviation_pct > 0 else 'Undervalued'} by {abs(deviation_pct):.1f}%. "
                f"PPP rate: {ppp_rate:.2f}, Actual: {exchange_rate:.2f}. "
                f"Signal: {trade_signal}."
            ),
            "method": "ECO 313 — Purchasing Power Parity (absolute PPP)",
        }

    @classmethod
    def afcfta_tariff_analysis(
        cls,
        origin: str,
        destination: str,
        product_category: str,
        current_tariff_rate: float,
        current_trade_volume: float,
        price_elasticity_of_demand: float = -1.2,
    ) -> dict[str, Any]:
        """
        Analyze impact of AfCFTA tariff reductions on trade.

        Driven by ECO 305 § Trade Policy and ECO 313 § Trade Agreements:

        Tariff reduction → lower import price → increased quantity demanded
        (law of demand, ECO 201).

        Welfare effects:
        - Consumer surplus gain: ΔCS = ½ × ΔP × (Q₁ + Q₀)
        - Government revenue loss: ΔRev = t₁ × Q₁ - t₀ × Q₀
        - Producer surplus loss: ΔPS = ½ × ΔP × (Q₀ + Q₁)
        - Net welfare = ΔCS - ΔPS - ΔRev + terms_of_trade_gain

        AfCFTA coverage:
        - 90% of tariff lines: fully eliminated
        - 7% sensitive products: reduced by 50%
        - 3% exclusion list: no change

        Args:
            origin: exporting country code
            destination: importing country code
            product_category: product category
            current_tariff_rate: current tariff rate (0-1)
            current_trade_volume: current trade volume (USD)
            price_elasticity_of_demand: PED for this product (default -1.2)

        Returns:
            Dict with tariff scenarios, welfare effects, and trade creation
        """
        # Determine AfCFTA treatment
        # Assume product is in 90% liberalized goods
        treatment = "90pct_goods"
        tariff_reduction = 1.0  # Full elimination

        new_tariff = current_tariff_rate * (1 - tariff_reduction)
        price_reduction_pct = current_tariff_rate * tariff_reduction

        # Trade creation effect (Viner, 1950)
        # % change in quantity = PED × % change in price
        ped = abs(price_elasticity_of_demand)
        quantity_change_pct = ped * price_reduction_pct * 100
        new_volume = current_trade_volume * (1 + quantity_change_pct / 100)
        trade_creation = new_volume - current_trade_volume

        # Consumer surplus gain (approximate)
        cs_gain = 0.5 * price_reduction_pct * (current_trade_volume + new_volume)

        # Government revenue loss
        revenue_loss = current_tariff_rate * current_trade_volume - new_tariff * new_volume

        # Net welfare effect
        net_welfare = cs_gain - revenue_loss

        # Sensitive products scenario (50% reduction)
        sensitive_new_tariff = current_tariff_rate * 0.5
        sensitive_quantity_change = ped * (current_tariff_rate * 0.5) * 100
        sensitive_new_volume = current_trade_volume * (1 + sensitive_quantity_change / 100)

        return {
            "origin": origin,
            "destination": destination,
            "product_category": product_category,
            "current_tariff_rate_pct": round(current_tariff_rate * 100, 1),
            "scenarios": {
                "full_liberalization": {
                    "new_tariff_rate_pct": round(new_tariff * 100, 1),
                    "price_reduction_pct": round(price_reduction_pct * 100, 1),
                    "quantity_change_pct": round(quantity_change_pct, 1),
                    "new_trade_volume_usd": round(new_volume, 0),
                    "trade_creation_usd": round(trade_creation, 0),
                    "consumer_surplus_gain_usd": round(cs_gain, 0),
                    "government_revenue_loss_usd": round(revenue_loss, 0),
                    "net_welfare_effect_usd": round(net_welfare, 0),
                    "treatment": "90% of goods (AfCFTA)",
                },
                "sensitive_products": {
                    "new_tariff_rate_pct": round(sensitive_new_tariff * 100, 1),
                    "quantity_change_pct": round(sensitive_quantity_change, 1),
                    "new_trade_volume_usd": round(sensitive_new_volume, 0),
                    "treatment": "7% sensitive goods (50% reduction)",
                },
                "exclusion_list": {
                    "new_tariff_rate_pct": round(current_tariff_rate * 100, 1),
                    "trade_volume_usd": current_trade_volume,
                    "treatment": "3% exclusion list (no change)",
                },
            },
            "price_elasticity_used": -ped,
            "interpretation": (
                f"AfCFTA liberalization would increase {product_category} trade "
                f"from {origin} to {destination} by ~{quantity_change_pct:.0f}%, "
                f"creating ~${trade_creation:,.0f} in new trade and "
                f"~${cs_gain:,.0f} in consumer surplus. "
                f"Government revenue loss: ~${revenue_loss:,.0f}. "
                f"Net welfare: {'positive' if net_welfare > 0 else 'negative'} (${net_welfare:,.0f})."
            ),
            "method": "ECO 305/313 — AfCFTA Tariff Impact Analysis (Viner trade creation)",
        }

    @classmethod
    def full_cross_border_analysis(
        cls,
        origin: str,
        destination: str,
        product_category: str,
        domestic_prices: list[float] | None = None,
        foreign_prices: list[float] | None = None,
        exchange_rate_changes: list[float] | None = None,
        domestic_price_changes: list[float] | None = None,
        current_tariff_rate: float = 0.25,
        current_trade_volume: float = 1000000,
    ) -> dict[str, Any]:
        """
        Comprehensive cross-border trade intelligence report.

        Combines all ECO 305/313 analyses into a single report:
        1. Gravity model trade flow prediction
        2. Comparative advantage assessment
        3. Exchange rate pass-through estimation
        4. PPP deviation analysis
        5. AfCFTA tariff impact analysis

        Args:
            origin: exporting country code
            destination: importing country code
            product_category: product category
            domestic_prices: list of domestic prices (for PPP)
            foreign_prices: list of foreign prices (for PPP)
            exchange_rate_changes: ER changes (for ERPT)
            domestic_price_changes: price changes (for ERPT)
            current_tariff_rate: current tariff (0-1)
            current_trade_volume: current volume (USD)

        Returns:
            Comprehensive cross-border intelligence report
        """
        report = {
            "product": "soko_pulse_cross_border",
            "origin": origin,
            "destination": destination,
            "product_category": product_category,
            "generated_at": datetime.now(UTC).isoformat(),
        }

        # 1. Gravity model
        report["gravity_model"] = cls.gravity_model_estimate(
            origin, destination, product_category
        )

        # 2. Comparative advantage (requires domestic/world shares)
        # Use estimated shares based on EAC trade patterns
        domestic_share = 0.15  # Placeholder: 15% of country's trade
        world_share = 0.05     # Placeholder: 5% of world trade
        report["comparative_advantage"] = cls.comparative_advantage_index(
            origin, product_category, domestic_share, world_share
        )

        # 3. Exchange rate pass-through
        if exchange_rate_changes and domestic_price_changes:
            report["exchange_rate_pass_through"] = cls.exchange_rate_pass_through(
                origin, destination, exchange_rate_changes, domestic_price_changes
            )

        # 4. PPP deviation
        if domestic_prices and foreign_prices:
            avg_domestic = float(np.mean(domestic_prices))
            avg_foreign = float(np.mean(foreign_prices))
            # Estimate ER from price ratio
            est_er = avg_domestic / max(avg_foreign, 1e-10)
            report["ppp_analysis"] = cls.ppp_deviation(
                origin, destination, avg_domestic, avg_foreign, est_er
            )

        # 5. AfCFTA tariff analysis
        report["afcfta_impact"] = cls.afcfta_tariff_analysis(
            origin, destination, product_category,
            current_tariff_rate, current_trade_volume,
        )

        # Summary
        report["summary"] = {
            "eac_trade_partner": cls.EAC_COUNTRIES.get(destination, {}).get("name", destination),
            "distance_km": cls.DISTANCE_MATRIX.get(
                (origin, destination) if (origin, destination) in cls.DISTANCE_MATRIX
                else (destination, origin), "unknown"
            ),
            "recommendation": "expand" if report.get("gravity_model", {}).get("trade_potential", 1) > 0.8 else "monitor",
            "key_insight": (
                f"{product_category} trade from {origin} to {destination}: "
                f"Gravity model predicts ${report.get('gravity_model', {}).get('gravity_model', {}).get('adjusted_flow_million_usd', 0):.1f}M "
                f"flow. AfCFTA could boost volume by "
                f"~{report.get('afcfta_impact', {}).get('scenarios', {}).get('full_liberalization', {}).get('quantity_change_pct', 0):.0f}%."
            ),
        }

        return report

    @staticmethod
    def _interpret_gravity(
        trade_potential: float | None, origin: str, dest: str,
    ) -> str:
        """Interpret gravity model trade potential ratio."""
        if trade_potential is None:
            return "No observed flow data for comparison."
        if trade_potential > 1.5:
            return f"Trade between {origin} and {dest} exceeds gravity prediction — strong trade link."
        elif trade_potential > 0.8:
            return f"Trade between {origin} and {dest} is near gravity prediction — normal trade link."
        elif trade_potential > 0.3:
            return f"Trade between {origin} and {dest} is below prediction — untapped potential."
        else:
            return f"Trade between {origin} and {dest} is well below prediction — significant barriers exist."
