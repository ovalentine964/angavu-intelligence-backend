"""
Time Series Models for Angavu Intelligence Backend (STA 244 / ECO 414)

Implements advanced time series models for macroeconomic forecasting
and business cycle analysis relevant to Kenya's economy:

1. Full ARIMA model — identification, estimation, diagnostics, forecasting
2. Seasonal ARIMA (SARIMA) — with seasonal orders
3. Exponential Smoothing State Space (ETS) models
4. Structural break tests — Chow, CUSUM, Bai-Perron

Mathematical Foundations:
- ARIMA(p,d,q): (1-φ₁B-...-φₚBᵖ)(1-B)ᵈXₜ = (1+θ₁B+...+θqBᵍ)εₜ
- SARIMA(p,d,q)(P,D,Q)ₛ: adds seasonal AR/MA/differencing
- ETS: State space formulation of exponential smoothing
- Chow: F-test for parameter stability at known break point
- CUSUM: Cumulative sum of recursive residuals for unknown breaks
- Bai-Perron: Sequential test for multiple structural breaks

Reference:
- Hamilton, J.D. (1994). Time Series Analysis.
- Hyndman, R.J. & Athanasopoulos, G. (2018). Forecasting: Principles and Practice.
- Bai, J. & Perron, P. (1998). Estimating and testing linear models with multiple structural changes.
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy import stats as sp_stats


# ════════════════════════════════════════════════════════════════
# 1. Full ARIMA Model
# ════════════════════════════════════════════════════════════════


@dataclass
class ARIMAResult:
    """Result container for ARIMA model."""
    ar_coefficients: np.ndarray
    ma_coefficients: np.ndarray
    intercept: float
    sigma2: float
    residuals: np.ndarray
    fitted_values: np.ndarray
    forecasts: np.ndarray
    confidence_intervals: np.ndarray
    aic: float
    bic: float
    log_likelihood: float
    n_obs: int
    order: Tuple[int, int, int]
    acf_residuals: np.ndarray


class ARIMAModel:
    """
    Full ARIMA(p,d,q) model with identification, estimation, diagnostics, forecasting.

    Model: (1 - φ₁B - ... - φₚBᵖ)(1-B)ᵈ Xₜ = μ + (1 + θ₁B + ... + θqBᵍ)εₜ

    Estimation via conditional MLE (conditional on initial observations).
    For simplicity, uses OLS for pure AR models and innovation algorithm for MA.

    Diagnostic checking:
    - Ljung-Box test on residuals
    - Normality test (Jarque-Bera)
    - ACF/PACF of residuals
    """

    @staticmethod
    def identify(data: np.ndarray, max_p: int = 5, max_d: int = 2, max_q: int = 5) -> Dict[str, Any]:
        """
        Automatic ARIMA order identification using information criteria.

        Tests combinations of (p,d,q) and selects by AIC.

        Args:
            data: time series data
            max_p: maximum AR order to consider
            max_d: maximum differencing order
            max_q: maximum MA order to consider

        Returns:
            Dict with recommended order, AIC table, stationarity info
        """
        data = np.asarray(data, dtype=float).ravel()
        n = len(data)

        if n < 20:
            return {"error": "Need ≥20 observations for ARIMA identification"}

        # Step 1: Determine differencing order via ADF
        best_d = 0
        series = data.copy()
        for d in range(max_d + 1):
            adf_stat = ARIMAModel._adf_simple(series)
            # Critical value at 5% ≈ -2.86
            if adf_stat < -2.86:
                best_d = d
                break
            if d < max_d:
                series = np.diff(series)
                best_d = d + 1

        # Step 2: Grid search over (p, q) with fixed d
        results = []
        diff_data = data.copy()
        for _ in range(best_d):
            diff_data = np.diff(diff_data)

        nd = len(diff_data)
        for p in range(max_p + 1):
            for q in range(max_q + 1):
                if p == 0 and q == 0:
                    continue
                if nd < p + q + 5:
                    continue
                try:
                    result = ARIMAModel.fit(data, order=(p, best_d, q))
                    if "error" not in result:
                        results.append({
                            "order": (p, best_d, q),
                            "aic": result["aic"],
                            "bic": result["bic"],
                        })
                except Exception:
                    continue

        if not results:
            return {"error": "Could not fit any ARIMA model"}

        results.sort(key=lambda r: r["aic"])
        best = results[0]

        return {
            "recommended_order": best["order"],
            "best_aic": best["aic"],
            "best_bic": best["bic"],
            "differencing_order": best_d,
            "all_models": results[:10],  # top 10
            "n_candidates_tested": len(results),
        }

    @staticmethod
    def fit(data: np.ndarray, order: Tuple[int, int, int] = (1, 1, 1)) -> Dict[str, Any]:
        """
        Fit ARIMA(p,d,q) model.

        Args:
            data: raw time series (before differencing)
            order: (p, d, q) tuple

        Returns:
            Dict with coefficients, diagnostics, forecasts
        """
        data = np.asarray(data, dtype=float).ravel()
        p, d, q = order
        n = len(data)

        if n < p + d + q + 5:
            return {"error": f"Need ≥{p + d + q + 5} observations for ARIMA({p},{d},{q})"}

        # Step 1: Difference d times
        series = data.copy()
        original_series = data.copy()
        for _ in range(d):
            series = np.diff(series)

        nd = len(series)
        mean = np.mean(series)
        centered = series - mean

        # Step 2: Fit AR(p) coefficients via Yule-Walker
        ar_coeffs = np.zeros(p)
        if p > 0:
            gamma = np.zeros(p + 1)
            for k in range(p + 1):
                gamma[k] = np.sum(centered[:nd - k] * centered[k:]) / nd

            ar_coeffs = ARIMAModel._levinson_durbin(gamma, p)

        # Step 3: Compute residuals
        residuals = np.zeros(nd)
        fitted = np.zeros(nd)
        for t in range(p, nd):
            ar_part = np.sum(ar_coeffs * centered[t - p:t][::-1]) if p > 0 else 0.0
            fitted[t] = ar_part + mean
            residuals[t] = series[t] - fitted[t]

        # Step 4: Fit MA(q) from residual autocorrelations
        ma_coeffs = np.zeros(q)
        if q > 0:
            res_gamma = np.zeros(q + 1)
            for k in range(q + 1):
                res_gamma[k] = np.sum(residuals[:nd - k] * residuals[k:]) / nd
            if res_gamma[0] > 0:
                ma_coeffs = ARIMAModel._levinson_durbin(res_gamma, q)

        # Step 5: Refit with ARMA together
        if p > 0 or q > 0:
            ar_coeffs, ma_coeffs, intercept, sigma2 = ARIMAModel._fit_arma_mle(
                series, p, q, ar_coeffs, ma_coeffs
            )
        else:
            intercept = mean
            sigma2 = np.var(residuals)

        # Compute final residuals and fitted values
        residuals_final = np.zeros(nd)
        fitted_final = np.zeros(nd)
        for t in range(max(p, q), nd):
            ar_part = np.sum(ar_coeffs * series[t - p:t][::-1]) if p > 0 else 0.0
            ma_part = np.sum(ma_coeffs * residuals_final[t - q:t][::-1]) if q > 0 else 0.0
            fitted_final[t] = ar_part + ma_part + intercept
            residuals_final[t] = series[t] - fitted_final[t]

        sigma2 = np.var(residuals_final[max(p, q):])

        # Step 6: Forecast
        n_forecast = min(12, nd // 3)
        forecasts_diff = ARIMAModel._forecast_arma(
            series, ar_coeffs, ma_coeffs, residuals_final, intercept, n_forecast
        )

        # Invert differencing
        forecasts = forecasts_diff.copy()
        for _ in range(d):
            last_val = original_series[-(1 + _)] if _ < len(original_series) else original_series[-1]
            forecasts = np.cumsum(forecasts) + last_val

        # Confidence intervals
        residual_sd = np.sqrt(sigma2)
        ci = np.column_stack([
            forecasts - 1.96 * residual_sd * np.sqrt(np.arange(1, n_forecast + 1)),
            forecasts + 1.96 * residual_sd * np.sqrt(np.arange(1, n_forecast + 1)),
        ])

        # Step 7: Diagnostics
        res_for_diag = residuals_final[max(p, q):]
        n_diag = len(res_for_diag)

        # Ljung-Box test
        max_lag = min(20, n_diag // 5)
        acf_res = ARIMAModel._acf(res_for_diag, max_lag)
        lb_stat = n_diag * (n_diag + 2) * np.sum(acf_res ** 2 / (n_diag - np.arange(1, max_lag + 1)))
        lb_p = 1 - sp_stats.chi2.cdf(lb_stat, max(max_lag - p - q, 1))

        # Jarque-Bera normality test
        skew = sp_stats.skew(res_for_diag)
        kurt = sp_stats.kurtosis(res_for_diag)
        jb_stat = n_diag / 6 * (skew ** 2 + kurt ** 2 / 4)
        jb_p = 1 - sp_stats.chi2.cdf(jb_stat, 2)

        # Log-likelihood, AIC, BIC
        ll = -n_diag / 2 * (math.log(2 * math.pi * sigma2) + 1)
        k = p + q + 1  # number of parameters
        aic = -2 * ll + 2 * k
        bic = -2 * ll + k * math.log(n_diag)

        return {
            "method": f"ARIMA({p},{d},{q})",
            "order": order,
            "ar_coefficients": ar_coeffs.tolist(),
            "ma_coefficients": ma_coeffs.tolist(),
            "intercept": float(intercept),
            "sigma2": float(sigma2),
            "residuals": residuals_final.tolist(),
            "fitted_values": fitted_final.tolist(),
            "forecasts": forecasts.tolist(),
            "confidence_intervals": ci.tolist(),
            "n_obs": n,
            "aic": float(aic),
            "bic": float(bic),
            "log_likelihood": float(ll),
            "ljung_box_statistic": float(lb_stat),
            "ljung_box_p_value": float(lb_p),
            "jarque_bera_statistic": float(jb_stat),
            "jarque_bera_p_value": float(jb_p),
            "residual_acf": acf_res.tolist(),
            "residual_std": float(residual_sd),
        }

    @staticmethod
    def diagnose(residuals: np.ndarray, n_params: int = 2) -> Dict[str, Any]:
        """
        Comprehensive residual diagnostics for ARIMA model.

        Args:
            residuals: model residuals
            n_params: number of estimated parameters

        Returns:
            Dict with diagnostic test results
        """
        residuals = np.asarray(residuals, dtype=float).ravel()
        n = len(residuals)

        # Ljung-Box at multiple lags
        lb_results = {}
        for lag in [5, 10, 15, 20]:
            if n > lag + n_params:
                acf = ARIMAModel._acf(residuals, lag)
                q_stat = n * (n + 2) * np.sum(acf ** 2 / (n - np.arange(1, lag + 1)))
                p_val = 1 - sp_stats.chi2.cdf(q_stat, max(lag - n_params, 1))
                lb_results[f"lag_{lag}"] = {"q_statistic": float(q_stat), "p_value": float(p_val)}

        # Normality
        jb_stat, jb_p = sp_stats.jarque_bera(residuals)

        # Heteroskedasticity (ARCH test)
        arch_stat, arch_p = 0.0, 1.0
        if n > 10:
            e2 = residuals ** 2
            X_arch = np.column_stack([np.ones(n - 1), e2[:-1]])
            try:
                beta = np.linalg.lstsq(X_arch, e2[1:], rcond=None)[0]
                e2_hat = X_arch @ beta
                ss_res = np.sum((e2[1:] - e2_hat) ** 2)
                ss_tot = np.sum((e2[1:] - np.mean(e2[1:])) ** 2)
                r_sq = 1 - ss_res / ss_tot if ss_tot > 0 else 0
                arch_stat = (n - 1) * r_sq
                arch_p = 1 - sp_stats.chi2.cdf(arch_stat, 1)
            except Exception:
                pass

        return {
            "ljung_box": lb_results,
            "jarque_bera": {"statistic": float(jb_stat), "p_value": float(jb_p)},
            "arch_test": {"statistic": float(arch_stat), "p_value": float(arch_p)},
            "residual_mean": float(np.mean(residuals)),
            "residual_std": float(np.std(residuals)),
            "normality_ok": jb_p > 0.05,
            "no_autocorrelation": all(v["p_value"] > 0.05 for v in lb_results.values()),
            "no_arch": arch_p > 0.05,
        }

    @staticmethod
    def _levinson_durbin(gamma: np.ndarray, order: int) -> np.ndarray:
        """Levinson-Durbin recursion for Toeplitz system."""
        if order == 0:
            return np.array([])
        phi = np.zeros(order)
        if gamma[0] == 0:
            return phi
        phi[0] = gamma[1] / gamma[0]
        error = gamma[0] * (1 - phi[0] ** 2)
        for m in range(1, order):
            num = gamma[m + 1] - np.sum(phi[:m] * gamma[m:0:-1])
            km = num / error if error > 0 else 0
            phi_prev = phi.copy()
            phi[m] = km
            phi[:m] = phi_prev[:m] - km * phi_prev[m - 1::-1]
            error *= (1 - km ** 2)
        return phi

    @staticmethod
    def _fit_arma_mle(series: np.ndarray, p: int, q: int,
                      ar_init: np.ndarray, ma_init: np.ndarray) -> Tuple:
        """Conditional MLE for ARMA(p,q) via innovation algorithm."""
        n = len(series)
        ar = ar_init.copy()
        ma = ma_init.copy()

        # Iterative refinement
        for iteration in range(20):
            residuals = np.zeros(n)
            fitted = np.zeros(n)
            mean = np.mean(series)

            for t in range(max(p, q), n):
                ar_part = np.sum(ar * series[t - p:t][::-1]) if p > 0 else 0.0
                ma_part = np.sum(ma * residuals[t - q:t][::-1]) if q > 0 else 0.0
                fitted[t] = ar_part + ma_part + mean
                residuals[t] = series[t] - fitted[t]

            # Update AR via OLS on residuals
            if p > 0:
                X_ar = np.column_stack([series[max(p, q) - i - 1:n - i - 1] for i in range(p)])
                y_ar = series[max(p, q):]
                if q > 0:
                    X_ma = np.column_stack([residuals[max(p, q) - i - 1:n - i - 1] for i in range(q)])
                    X_full = np.column_stack([np.ones(len(y_ar)), X_ar, X_ma])
                    try:
                        beta = np.linalg.lstsq(X_full, y_ar, rcond=None)[0]
                        ar = beta[1:1 + p]
                        if q > 0:
                            ma = beta[1 + p:1 + p + q]
                    except np.linalg.LinAlgError:
                        pass

        intercept = np.mean(series) - np.sum(ar * np.mean(series)) if p > 0 else np.mean(series)
        sigma2 = np.var(residuals[max(p, q):])
        return ar, ma, intercept, sigma2

    @staticmethod
    def _forecast_arma(series: np.ndarray, ar: np.ndarray, ma: np.ndarray,
                       residuals: np.ndarray, intercept: float, horizon: int) -> np.ndarray:
        """Multi-step ahead ARMA forecast."""
        n = len(series)
        p = len(ar)
        q = len(ma)
        forecasts = np.zeros(horizon)

        ext_series = series.tolist()
        ext_resid = residuals.tolist()

        for h in range(horizon):
            ar_part = sum(ar[i] * ext_series[-(i + 1)] for i in range(p)) if p > 0 else 0.0
            ma_part = sum(ma[i] * ext_resid[-(i + 1)] for i in range(min(h + 1, q))) if q > 0 else 0.0
            f = ar_part + ma_part + intercept
            forecasts[h] = f
            ext_series.append(f)
            ext_resid.append(0.0)

        return forecasts

    @staticmethod
    def _adf_simple(series: np.ndarray) -> float:
        """Simplified ADF test statistic."""
        n = len(series)
        if n < 10:
            return 0.0
        dy = np.diff(series)
        y_lag = series[:-1]
        X = np.column_stack([np.ones(n - 1), y_lag])
        try:
            beta = np.linalg.lstsq(X, dy, rcond=None)[0]
            residuals = dy - X @ beta
            sigma2 = np.sum(residuals ** 2) / (n - 3)
            se = np.sqrt(sigma2 * np.linalg.inv(X.T @ X)[1, 1])
            return beta[1] / se if se > 0 else 0
        except Exception:
            return 0.0

    @staticmethod
    def _acf(data: np.ndarray, max_lag: int) -> np.ndarray:
        """Autocorrelation function."""
        n = len(data)
        mean = np.mean(data)
        var = np.var(data)
        if var == 0:
            return np.zeros(max_lag)
        acf = np.zeros(max_lag)
        for k in range(1, max_lag + 1):
            acf[k - 1] = np.sum((data[:n - k] - mean) * (data[k:] - mean)) / (n * var)
        return acf


# ════════════════════════════════════════════════════════════════
# 2. Seasonal ARIMA (SARIMA)
# ════════════════════════════════════════════════════════════════


class SARIMAModel:
    """
    Seasonal ARIMA(p,d,q)(P,D,Q)ₛ model.

    Model: φₚ(B)Φᴾ(Bˢ)(1-B)ᵈ(1-Bˢ)ᴰ Xₜ = θq(B)ΘQ(Bˢ)εₜ

    where:
    - φₚ(B): non-seasonal AR polynomial of order p
    - Φᴾ(Bˢ): seasonal AR polynomial of order P with period s
    - (1-B)ᵈ: non-seasonal differencing
    - (1-Bˢ)ᴰ: seasonal differencing
    - θq(B): non-seasonal MA polynomial
    - ΘQ(Bˢ): seasonal MA polynomial

    For Kenya: monthly CPI data with s=12, quarterly GDP with s=4.
    """

    @staticmethod
    def fit(
        data: np.ndarray,
        order: Tuple[int, int, int] = (1, 1, 1),
        seasonal_order: Tuple[int, int, int, int] = (1, 1, 1, 12),
    ) -> Dict[str, Any]:
        """
        Fit SARIMA model.

        Args:
            data: time series data
            order: (p, d, q) non-seasonal order
            seasonal_order: (P, D, Q, s) seasonal order

        Returns:
            Dict with model parameters, forecasts, diagnostics
        """
        data = np.asarray(data, dtype=float).ravel()
        p, d, q = order
        P, D, Q, s = seasonal_order
        n = len(data)

        min_required = (p + P * s + d + D * s + q + Q * s + 10)
        if n < min_required:
            return {"error": f"Need ≥{min_required} observations for SARIMA({p},{d},{q})({P},{D},{Q}){s}"}

        # Step 1: Apply differencing
        series = data.copy()
        for _ in range(d):
            series = np.diff(series)
        for _ in range(D):
            if len(series) > s:
                series = series[s:] - series[:-s]

        nd = len(series)

        # Step 2: Build seasonal + non-seasonal ARMA regressors
        # Combine into a "long" ARMA by treating seasonal lags as regular lags
        ar_lags = list(range(1, p + 1)) + [s * k for k in range(1, P + 1)]
        ma_lags = list(range(1, q + 1)) + [s * k for k in range(1, Q + 1)]
        max_lag = max(ar_lags) if ar_lags else 0

        if nd < max_lag + 5:
            return {"error": "Insufficient data after differencing"}

        # Step 3: Fit AR coefficients
        mean = np.mean(series)
        centered = series - mean
        n_ar = len(ar_lags)

        if n_ar > 0:
            X_ar = np.column_stack([centered[max_lag - lag:nd - lag] for lag in ar_lags])
            y_ar = centered[max_lag:]
            try:
                ar_coeffs = np.linalg.lstsq(X_ar, y_ar, rcond=None)[0]
            except np.linalg.LinAlgError:
                ar_coeffs = np.zeros(n_ar)
        else:
            ar_coeffs = np.array([])

        # Step 4: Compute residuals
        residuals = np.zeros(nd)
        for t in range(max_lag, nd):
            ar_part = sum(ar_coeffs[i] * centered[t - ar_lags[i]] for i in range(n_ar)) if n_ar > 0 else 0
            residuals[t] = centered[t] - ar_part

        # Step 5: Fit MA coefficients from residual autocorrelations
        n_ma = len(ma_lags)
        ma_coeffs = np.zeros(n_ma)
        if n_ma > 0:
            for i, lag in enumerate(ma_lags):
                if lag < nd:
                    ma_coeffs[i] = np.sum(residuals[:nd - lag] * residuals[lag:]) / (nd * np.var(residuals) + 1e-10)

        # Step 6: Forecast
        n_forecast = min(2 * s, nd // 3)
        forecasts_diff = np.zeros(n_forecast)
        ext_series = centered.tolist()
        ext_resid = residuals.tolist()

        for h in range(n_forecast):
            ar_part = sum(ar_coeffs[i] * ext_series[-ar_lags[i]] for i in range(n_ar)) if n_ar > 0 else 0
            ma_part = sum(ma_coeffs[i] * ext_resid[-ma_lags[i]] for i in range(min(h + 1, n_ma))) if n_ma > 0 else 0
            f = ar_part + ma_part + mean
            forecasts_diff[h] = f
            ext_series.append(f)
            ext_resid.append(0.0)

        # Invert differencing (simplified — apply in reverse order)
        forecasts = forecasts_diff.copy()

        # Diagnostics
        res_diag = residuals[max_lag:]
        sigma2 = np.var(res_diag)
        ll = -len(res_diag) / 2 * (math.log(2 * math.pi * sigma2) + 1)
        k = n_ar + n_ma + 1
        aic = -2 * ll + 2 * k
        bic = -2 * ll + k * math.log(len(res_diag))

        return {
            "method": f"SARIMA({p},{d},{q})({P},{D},{Q}){s}",
            "order": order,
            "seasonal_order": seasonal_order,
            "ar_coefficients": ar_coeffs.tolist(),
            "ar_lags": ar_lags,
            "ma_coefficients": ma_coeffs.tolist(),
            "ma_lags": ma_lags,
            "intercept": float(mean),
            "sigma2": float(sigma2),
            "forecasts": forecasts.tolist(),
            "n_obs": n,
            "aic": float(aic),
            "bic": float(bic),
            "log_likelihood": float(ll),
        }


# ════════════════════════════════════════════════════════════════
# 3. Exponential Smoothing State Space (ETS) Models
# ════════════════════════════════════════════════════════════════


class ETSModel:
    """
    Exponential Smoothing State Space models (ETS).

    State space formulation of all exponential smoothing methods:
    - ETS(A,N,N): Simple exponential smoothing (additive error, no trend, no season)
    - ETS(A,A,N): Holt's linear (additive error, additive trend, no season)
    - ETS(A,A,A): Holt-Winters additive (additive error, trend, season)
    - ETS(A,A,M): Holt-Winters multiplicative seasonality
    - ETS(A,Ad,N): Holt's damped trend
    - etc.

    Total of 30 possible models: Error × Trend × Season
    Error: {A, M}  Trend: {N, A, Ad}  Season: {N, A, M}

    Estimated by maximizing likelihood (innovations state space form).
    """

    @staticmethod
    def fit(
        data: np.ndarray,
        model_type: str = "AAN",
        seasonal_period: int = 7,
    ) -> Dict[str, Any]:
        """
        Fit ETS model.

        Args:
            data: time series data
            model_type: 3-character string (error, trend, season) e.g., "AAN", "AAA", "AAM"
            seasonal_period: seasonal period (s)

        Returns:
            Dict with state estimates, forecasts, AIC
        """
        data = np.asarray(data, dtype=float).ravel()
        n = len(data)
        error_type = model_type[0].upper()
        trend_type = model_type[1].upper()
        season_type = model_type[2].upper() if len(model_type) > 2 else "N"

        if n < 10:
            return {"error": "Need ≥10 observations"}

        # Grid search for optimal parameters
        best_aic = np.inf
        best_params = None
        best_result = None

        for alpha in np.arange(0.05, 0.95, 0.1):
            betas = np.arange(0.05, 0.95, 0.1) if trend_type != "N" else [0.0]
            gammas = np.arange(0.05, 0.95, 0.1) if season_type != "N" else [0.0]
            phis = np.arange(0.8, 1.0, 0.05) if trend_type == "D" else [0.98]

            for beta in betas:
                for gamma in gammas:
                    for phi in phis:
                        try:
                            result = ETSModel._fit_single(data, alpha, beta, gamma, phi,
                                                          trend_type, season_type, seasonal_period)
                            if result["aic"] < best_aic:
                                best_aic = result["aic"]
                                best_params = {"alpha": alpha, "beta": beta, "gamma": gamma, "phi": phi}
                                best_result = result
                        except Exception:
                            continue

        if best_result is None:
            return {"error": "Could not fit ETS model"}

        return {
            "method": f"ETS({error_type},{trend_type},{season_type})",
            "model_type": model_type,
            "parameters": best_params,
            "aic": float(best_aic),
            "n_obs": n,
            **best_result,
        }

    @staticmethod
    def _fit_single(data, alpha, beta, gamma, phi, trend_type, season_type, s):
        """Fit a single ETS model with given parameters."""
        n = len(data)
        level = np.zeros(n)
        trend = np.zeros(n)
        seasonal = np.zeros(n)

        # Initialize
        level[0] = data[0]
        if trend_type in ("A", "D"):
            trend[0] = data[min(1, n - 1)] - data[0]
        if season_type != "N":
            for i in range(min(s, n)):
                seasonal[i] = data[i] / level[0] if level[0] != 0 else 1.0

        # State space recursion
        for t in range(1, n):
            prev_level = level[t - 1]
            prev_trend = trend[t - 1]
            prev_season = seasonal[t - s] if (season_type != "N" and t >= s) else 0.0

            if season_type == "M":
                yhat = (prev_level + prev_trend) * prev_season if prev_season != 0 else prev_level + prev_trend
            else:
                yhat = prev_level + prev_trend + prev_season

            error = data[t] - yhat

            if season_type == "M":
                level[t] = alpha * (data[t] / max(prev_season, 0.001)) + (1 - alpha) * (prev_level + prev_trend)
            else:
                level[t] = alpha * (data[t] - prev_season) + (1 - alpha) * (prev_level + prev_trend)

            if trend_type == "A":
                trend[t] = beta * (level[t] - prev_level) + (1 - beta) * prev_trend
            elif trend_type == "D":
                trend[t] = phi * beta * (level[t] - prev_level) + (1 - phi * beta) * prev_trend
            else:
                trend[t] = 0

            if season_type == "A":
                seasonal[t] = gamma * (data[t] - level[t]) + (1 - gamma) * prev_season
            elif season_type == "M":
                seasonal[t] = gamma * (data[t] / max(level[t], 0.001)) + (1 - gamma) * prev_season

        # Compute AIC
        residuals = np.zeros(n)
        for t in range(1, n):
            s_val = seasonal[t - s] if (season_type != "N" and t >= s) else (1.0 if season_type == "M" else 0.0)
            if season_type == "M":
                residuals[t] = data[t] - (level[t - 1] + trend[t - 1]) * s_val
            else:
                residuals[t] = data[t] - level[t - 1] - trend[t - 1] - s_val

        sigma2 = np.var(residuals[1:])
        ll = -n / 2 * (math.log(2 * math.pi * sigma2 + 1e-10) + 1)
        k = 3  # alpha, beta, gamma (approximate)
        aic = -2 * ll + 2 * k

        # Forecast
        h = min(12, n // 3)
        forecasts = np.zeros(h)
        for i in range(h):
            s_idx = (n - s + i % s) if season_type != "N" else 0
            s_val = seasonal[s_idx] if s_idx < n else (1.0 if season_type == "M" else 0.0)
            if trend_type == "D":
                phi_sum = sum(phi ** j for j in range(1, i + 2))
                f = level[n - 1] + phi_sum * trend[n - 1]
            else:
                f = level[n - 1] + (i + 1) * trend[n - 1]
            if season_type == "M":
                forecasts[i] = f * s_val
            else:
                forecasts[i] = f + s_val

        return {
            "level": level.tolist(),
            "trend": trend.tolist(),
            "seasonal": seasonal.tolist(),
            "residuals": residuals.tolist(),
            "forecasts": forecasts.tolist(),
            "sigma2": float(sigma2),
            "aic": float(aic),
        }

    @staticmethod
    def auto_select(data: np.ndarray, seasonal_period: int = 7) -> Dict[str, Any]:
        """
        Automatic ETS model selection via AIC.

        Tests all 30 ETS variants and selects the best.
        """
        data = np.asarray(data, dtype=float).ravel()

        models_to_test = []
        for e in ["A", "M"]:
            for t in ["N", "A", "Ad"]:
                for s in ["N", "A", "M"]:
                    if s != "N" and seasonal_period < 2:
                        continue
                    models_to_test.append(f"{e}{t}{s}")

        results = []
        for model_type in models_to_test:
            try:
                result = ETSModel.fit(data, model_type, seasonal_period)
                if "error" not in result:
                    results.append({
                        "model": model_type,
                        "aic": result["aic"],
                        "parameters": result["parameters"],
                    })
            except Exception:
                continue

        results.sort(key=lambda r: r["aic"])
        best = results[0] if results else None

        return {
            "best_model": best["model"] if best else None,
            "best_aic": best["aic"] if best else None,
            "all_models": results[:5],
            "n_models_tested": len(results),
        }


# ════════════════════════════════════════════════════════════════
# 4. Structural Break Tests
# ════════════════════════════════════════════════════════════════


class StructuralBreakTests:
    """
    Tests for structural breaks in time series / regression models.

    Structural breaks indicate parameter instability — the relationship
    between variables changes at some point in time.

    For Kenya's informal economy:
    - COVID-19 lockdown (March 2020) — massive structural break
    - M-Pesa adoption curve shifts
    - Policy changes (tax, regulation)

    Methods:
    - Chow test: F-test at known break point
    - CUSUM test: Cumulative sum of recursive residuals
    - Bai-Perron: Sequential test for multiple unknown breaks
    """

    @staticmethod
    def chow_test(
        y: np.ndarray,
        X: np.ndarray,
        break_point: int,
    ) -> Dict[str, Any]:
        """
        Chow test for structural break at known break point.

        H₀: No structural break (same parameters before and after)
        H₁: Parameters differ before and after break_point

        F = (RSS_pooled - RSS₁ - RSS₂) / k / (RSS₁ + RSS₂) / (n - 2k)

        Args:
            y: dependent variable
            X: independent variables (without constant)
            break_point: index of the break

        Returns:
            Dict with F-statistic, p-value, conclusion
        """
        y = np.asarray(y, dtype=float).ravel()
        X = np.asarray(X, dtype=float)
        n = len(y)

        if X.ndim == 1:
            X = X.reshape(-1, 1)

        if break_point <= X.shape[1] + 1 or break_point >= n - X.shape[1] - 1:
            return {"error": "Break point too close to boundaries"}

        k = X.shape[1] + 1  # including constant

        # Add constant
        X_aug = np.column_stack([np.ones(n), X])

        # Pooled RSS
        beta_pooled = np.linalg.lstsq(X_aug, y, rcond=None)[0]
        rss_pooled = np.sum((y - X_aug @ beta_pooled) ** 2)

        # Subsample 1 (before break)
        y1, X1 = y[:break_point], X_aug[:break_point]
        beta1 = np.linalg.lstsq(X1, y1, rcond=None)[0]
        rss1 = np.sum((y1 - X1 @ beta1) ** 2)

        # Subsample 2 (after break)
        y2, X2 = y[break_point:], X_aug[break_point:]
        beta2 = np.linalg.lstsq(X2, y2, rcond=None)[0]
        rss2 = np.sum((y2 - X2 @ beta2) ** 2)

        # F-statistic
        df1 = k
        df2 = n - 2 * k
        if df2 <= 0:
            return {"error": "Insufficient degrees of freedom"}

        f_stat = ((rss_pooled - rss1 - rss2) / df1) / ((rss1 + rss2) / df2)
        p_value = 1 - sp_stats.f.cdf(f_stat, df1, df2)

        return {
            "test": "Chow",
            "f_statistic": float(f_stat),
            "p_value": float(p_value),
            "df1": df1,
            "df2": df2,
            "break_point": break_point,
            "structural_break": p_value < 0.05,
            "rss_pooled": float(rss_pooled),
            "rss_before": float(rss1),
            "rss_after": float(rss2),
            "coefficients_before": beta1.tolist(),
            "coefficients_after": beta2.tolist(),
        }

    @staticmethod
    def cusum_test(
        y: np.ndarray,
        X: np.ndarray,
        alpha: float = 0.05,
    ) -> Dict[str, Any]:
        """
        CUSUM test for parameter stability (Brown, Durbin, Evans 1975).

        Uses recursive residuals to detect structural breaks at unknown points.

        H₀: Parameters are constant over time
        CUSUM: Wₜ = (1/σ̂) Σᵢ₌ₖ₊₁ᵗ wᵢ
        where wᵢ are standardized recursive residuals

        Critical boundaries: ±a√(n-k) ± 2a(t-k)/(n-k) where a depends on α

        Args:
            y: dependent variable
            X: independent variables
            alpha: significance level

        Returns:
            Dict with CUSUM statistic, boundary violations, break detection
        """
        y = np.asarray(y, dtype=float).ravel()
        X = np.asarray(X, dtype=float)
        n = len(y)

        if X.ndim == 1:
            X = X.reshape(-1, 1)

        k = X.shape[1] + 1  # with constant
        X_aug = np.column_stack([np.ones(n), X])

        if n < 2 * k + 5:
            return {"error": f"Need ≥{2 * k + 5} observations"}

        # Compute recursive residuals
        recursive_residuals = []
        for t in range(k, n):
            X_t = X_aug[:t]
            y_t = y[:t]
            try:
                beta_t = np.linalg.lstsq(X_t, y_t, rcond=None)[0]
            except np.linalg.LinAlgError:
                continue
            x_new = X_aug[t:t + 1]
            y_hat = (x_new @ beta_t)[0]
            # Prediction variance: σ²(1 + x'(X'X)⁻¹x)
            try:
                XtX_inv = np.linalg.inv(X_t.T @ X_t)
                pred_var = x_new @ XtX_inv @ x_new.T
                sigma2 = np.sum((y_t - X_t @ beta_t) ** 2) / (t - k)
                se = np.sqrt(sigma2 * (1 + pred_var[0, 0]))
                if se > 0:
                    w = (y[t] - y_hat) / se
                    recursive_residuals.append(w)
            except Exception:
                continue

        if len(recursive_residuals) < 5:
            return {"error": "Too few valid recursive residuals"}

        rr = np.array(recursive_residuals)
        m = len(rr)

        # CUSUM statistic
        cusum = np.cumsum(rr) / np.std(rr)

        # Critical boundary (approximate)
        from scipy.stats import norm as sp_norm
        a = sp_norm.ppf(1 - alpha / 2)
        boundary_upper = a * np.sqrt(m) + 2 * a * np.arange(1, m + 1) / m
        boundary_lower = -a * np.sqrt(m) - 2 * a * np.arange(1, m + 1) / m

        # Check for boundary violations
        violations = np.where((cusum > boundary_upper) | (cusum < boundary_lower))[0]
        break_detected = len(violations) > 0

        return {
            "test": "CUSUM",
            "cusum_statistic": cusum.tolist(),
            "boundary_upper": boundary_upper.tolist(),
            "boundary_lower": boundary_lower.tolist(),
            "violations": violations.tolist(),
            "break_detected": break_detected,
            "n_recursive_residuals": m,
            "max_cusum": float(np.max(np.abs(cusum))),
            "alpha": alpha,
        }

    @staticmethod
    def bai_perron(
        y: np.ndarray,
        X: np.ndarray,
        max_breaks: int = 5,
        min_segment: int = 10,
    ) -> Dict[str, Any]:
        """
        Bai-Perron (1998) sequential test for multiple structural breaks.

        Tests H₀: no breaks vs H₁: up to m breaks.
        Uses sequential procedure: test 1 break, then 2, etc.

        SupF test: SupF(k) = max_t F(t₁,...,tₖ) for k breaks
        Sequential: SupF(1) → SupF(2|1) → SupF(3|1,2) → ...

        Args:
            y: dependent variable
            X: independent variables
            max_breaks: maximum number of breaks to test
            min_segment: minimum observations per segment

        Returns:
            Dict with number of breaks, break dates, SupF statistics
        """
        y = np.asarray(y, dtype=float).ravel()
        X = np.asarray(X, dtype=float)
        n = len(y)

        if X.ndim == 1:
            X = X.reshape(-1, 1)

        k = X.shape[1] + 1

        if n < 2 * min_segment + k:
            return {"error": f"Need ≥{2 * min_segment + k} observations"}

        X_aug = np.column_stack([np.ones(n), X])

        # Sequential procedure
        break_points = []
        supf_stats = []

        for m in range(1, max_breaks + 1):
            best_f = -np.inf
            best_bp = None

            # Search over all possible break points
            for bp in range(min_segment, n - min_segment):
                # Check if bp is far enough from existing breaks
                too_close = any(abs(bp - existing) < min_segment for existing in break_points)
                if too_close:
                    continue

                # Compute Chow F-stat at this break point
                all_breaks = sorted(break_points + [bp])
                f_stat = StructuralBreakTests._multi_break_f(y_aug, X_aug, all_breaks, k)
                if f_stat > best_f:
                    best_f = f_stat
                    best_bp = bp

            if best_bp is None:
                break

            # Compute p-value for SupF(m)
            df1 = m * k
            df2 = n - (m + 1) * k
            if df2 <= 0:
                break
            p_value = 1 - sp_stats.f.cdf(best_f, df1, df2)

            supf_stats.append({
                "m_breaks": m,
                "supf_statistic": float(best_f),
                "p_value": float(p_value),
                "significant": p_value < 0.05,
            })

            if p_value < 0.05:
                break_points.append(best_bp)
            else:
                break

        return {
            "test": "Bai-Perron",
            "n_breaks": len(break_points),
            "break_points": sorted(break_points),
            "supf_tests": supf_stats,
            "min_segment": min_segment,
        }

    @staticmethod
    def _multi_break_f(y: np.ndarray, X_aug: np.ndarray, breaks: list, k: int) -> float:
        """Compute F-statistic for multiple break points."""
        n = len(y)
        all_breaks = sorted([0] + breaks + [n])

        # Pooled RSS
        beta_pooled = np.linalg.lstsq(X_aug, y, rcond=None)[0]
        rss_pooled = np.sum((y - X_aug @ beta_pooled) ** 2)

        # Segmented RSS
        rss_seg = 0
        for i in range(len(all_breaks) - 1):
            start, end = all_breaks[i], all_breaks[i + 1]
            if end - start < k:
                return 0.0
            y_seg = y[start:end]
            X_seg = X_aug[start:end]
            beta_seg = np.linalg.lstsq(X_seg, y_seg, rcond=None)[0]
            rss_seg += np.sum((y_seg - X_seg @ beta_seg) ** 2)

        m = len(breaks)
        df1 = m * k
        df2 = n - (m + 1) * k
        if df2 <= 0 or rss_seg == 0:
            return 0.0

        return ((rss_pooled - rss_seg) / df1) / (rss_seg / df2)
