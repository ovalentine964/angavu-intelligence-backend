"""
Econometric Engine — Causal inference and regression framework.

Theoretical Foundations:
- ECO 414: Introduction to Econometrics
- ECO 424: Econometrics (Advanced)
- ECO 210: Introduction to Quantitative Methods
- STA 341: Theory of Estimation

This module provides the shared econometric infrastructure for
estimating causal relationships, forecasting time series, and
building predictive models across all intelligence products.

Key Methods:
- OLS regression with robust standard errors (ECO 414)
- Instrumental variables / 2SLS for endogeneity (ECO 424)
- Logit/Probit for binary outcomes (ECO 424)
- ARIMA/ETS time series forecasting (STA 244)
- Index number construction (ECO 203)
- Heckman selection correction (ECO 424)
"""

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import structlog
from scipy import stats
from scipy.optimize import minimize

logger = structlog.get_logger(__name__)


class OLSRegression:
    """
    Ordinary Least Squares regression (ECO 414 — Intro Econometrics).

    Model: Y = Xβ + ε
    Estimator: β̂ = (X'X)⁻¹X'Y

    Assumptions (Gauss-Markov):
    1. Linearity: E[Y|X] = Xβ
    2. Random sampling
    3. No perfect multicollinearity
    4. Zero conditional mean: E[ε|X] = 0
    5. Homoskedasticity: Var(ε|X) = σ²

    Under these assumptions, OLS is BLUE (Best Linear Unbiased Estimator).
    When assumption 5 fails, use robust (White) standard errors.
    """

    @staticmethod
    def fit(
        X: np.ndarray,
        y: np.ndarray,
        robust: bool = True,
        add_constant: bool = True,
    ) -> Dict[str, Any]:
        """
        Fit OLS regression model.

        Args:
            X: Design matrix (n × k)
            y: Dependent variable (n × 1)
            robust: Use White robust standard errors
            add_constant: Add intercept term

        Returns:
            Dict with coefficients, standard errors, R², diagnostics
        """
        if add_constant:
            X = np.column_stack([np.ones(len(X)), X])

        n, k = X.shape

        # β̂ = (X'X)⁻¹X'Y
        XtX = X.T @ X
        Xty = X.T @ y
        try:
            XtX_inv = np.linalg.inv(XtX)
        except np.linalg.LinAlgError:
            return {"error": "Singular matrix — perfect multicollinearity detected"}

        beta_hat = XtX_inv @ Xty

        # Residuals
        residuals = y - X @ beta_hat
        mse = np.sum(residuals ** 2) / (n - k)

        # Standard errors
        if robust:
            # White robust (heteroskedasticity-consistent) standard errors
            # Var(β̂) = (X'X)⁻¹ X'ΩX (X'X)⁻¹ where Ω = diag(εᵢ²)
            Omega = np.diag(residuals ** 2)
            sandwich = XtX_inv @ (X.T @ Omega @ X) @ XtX_inv
            se = np.sqrt(np.diag(sandwich))
        else:
            # Classical standard errors
            se = np.sqrt(np.diag(mse * XtX_inv))

        # t-statistics and p-values
        t_stats = beta_hat / se
        p_values = 2 * (1 - stats.t.cdf(np.abs(t_stats), df=n - k))

        # R² and adjusted R²
        y_mean = np.mean(y)
        ss_tot = np.sum((y - y_mean) ** 2)
        ss_res = np.sum(residuals ** 2)
        r_squared = 1 - ss_res / ss_tot
        adj_r_squared = 1 - (1 - r_squared) * (n - 1) / (n - k)

        # F-test for joint significance
        if k > 1:
            ss_reg = np.sum((X @ beta_hat - y_mean) ** 2)
            f_stat = (ss_reg / (k - 1)) / (ss_res / (n - k))
            f_p_value = 1 - stats.f.cdf(f_stat, k - 1, n - k)
        else:
            f_stat = None
            f_p_value = None

        # Confidence intervals
        t_crit = stats.t.ppf(0.975, df=n - k)
        ci_lower = beta_hat - t_crit * se
        ci_upper = beta_hat + t_crit * se

        return {
            "coefficients": beta_hat.tolist(),
            "standard_errors": se.tolist(),
            "t_statistics": t_stats.tolist(),
            "p_values": p_values.tolist(),
            "confidence_intervals_95": list(zip(ci_lower.tolist(), ci_upper.tolist())),
            "r_squared": round(r_squared, 4),
            "adj_r_squared": round(adj_r_squared, 4),
            "n_observations": n,
            "n_parameters": k,
            "residual_std_error": round(np.sqrt(mse), 4),
            "f_statistic": round(float(f_stat), 4) if f_stat else None,
            "f_p_value": round(float(f_p_value), 6) if f_p_value else None,
            "robust_se": robust,
        }

    @staticmethod
    def compute_elasticity(
        beta: float,
        x_mean: float,
        y_mean: float,
        log_model: bool = True,
    ) -> float:
        """
        Compute elasticity from regression coefficient.

        For log-log model: elasticity = β₁ (coefficient directly)
        For log-level model: elasticity = β₁ × x_mean
        For level-log model: elasticity = β₁ / y_mean
        For level-level model: elasticity = β₁ × x_mean / y_mean

        Args:
            beta: Regression coefficient
            x_mean: Mean of independent variable
            y_mean: Mean of dependent variable
            log_model: True if both variables are in logs

        Returns:
            Elasticity value
        """
        if log_model:
            return round(float(beta), 4)
        else:
            return round(float(beta * x_mean / y_mean), 4)


class LogitModel:
    """
    Logistic regression for binary outcomes (ECO 424 — Econometrics).

    Model: P(Y=1|X) = Λ(Xβ) = e^(Xβ) / (1 + e^(Xβ))

    Used by Alama Score for default probability estimation:
    P(default=1|X) = Λ(β₀ + β₁·activity + β₂·stability + ...)

    Estimation: Maximum Likelihood Estimation (STA 341)
    Log-likelihood: ℓ(β) = Σ[yᵢ log Λ(Xᵢβ) + (1-yᵢ) log(1-Λ(Xᵢβ))]
    """

    @staticmethod
    def sigmoid(z: np.ndarray) -> np.ndarray:
        """Logistic (sigmoid) function: Λ(z) = 1/(1+e^(-z))"""
        z = np.clip(z, -500, 500)
        return 1 / (1 + np.exp(-z))

    @classmethod
    def fit(
        cls,
        X: np.ndarray,
        y: np.ndarray,
        add_constant: bool = True,
        max_iter: int = 1000,
        tol: float = 1e-8,
    ) -> Dict[str, Any]:
        """
        Fit logistic regression via Maximum Likelihood Estimation.

        Args:
            X: Design matrix (n × k)
            y: Binary outcome vector (n × 1), values in {0, 1}
            add_constant: Add intercept
            max_iter: Maximum iterations for Newton-Raphson
            tol: Convergence tolerance

        Returns:
            Dict with coefficients, standard errors, marginal effects
        """
        if add_constant:
            X = np.column_stack([np.ones(len(X)), X])

        n, k = X.shape
        y = y.astype(float)

        # Initialize
        beta = np.zeros(k)

        # Newton-Raphson iteration
        for iteration in range(max_iter):
            z = X @ beta
            p = cls.sigmoid(z)

            # Gradient: X'(y - p)
            gradient = X.T @ (y - p)

            # Hessian: -X'WX where W = diag(p(1-p))
            W = np.diag(p * (1 - p))
            hessian = -(X.T @ W @ X)

            # Update: β_new = β - H⁻¹g
            try:
                delta = np.linalg.solve(hessian, gradient)
            except np.linalg.LinAlgError:
                return {"error": "Singular Hessian — model may be perfect separation"}

            beta = beta - delta

            if np.max(np.abs(delta)) < tol:
                break

        # Standard errors from inverse of observed information
        try:
            cov_matrix = np.linalg.inv(-hessian)
            se = np.sqrt(np.diag(cov_matrix))
        except np.linalg.LinAlgError:
            se = np.full(k, np.nan)

        # Wald statistics
        z_stats = beta / se
        p_values = 2 * (1 - stats.norm.cdf(np.abs(z_stats)))

        # Log-likelihood
        p_final = cls.sigmoid(X @ beta)
        p_final = np.clip(p_final, 1e-10, 1 - 1e-10)
        log_lik = np.sum(y * np.log(p_final) + (1 - y) * np.log(1 - p_final))

        # AIC and BIC
        aic = -2 * log_lik + 2 * k
        bic = -2 * log_lik + k * np.log(n)

        # Marginal effects at mean
        p_mean = cls.sigmoid(np.mean(X, axis=0) @ beta)
        marginal_effects = beta * p_mean * (1 - p_mean)

        # Pseudo R² (McFadden)
        log_lik_null = np.sum(
            y * np.log(np.mean(y)) + (1 - y) * np.log(1 - np.mean(y))
        )
        pseudo_r2 = 1 - log_lik / log_lik_null

        return {
            "coefficients": beta.tolist(),
            "standard_errors": se.tolist(),
            "z_statistics": z_stats.tolist(),
            "p_values": p_values.tolist(),
            "marginal_effects_at_mean": marginal_effects.tolist(),
            "log_likelihood": round(float(log_lik), 4),
            "pseudo_r_squared": round(float(pseudo_r2), 4),
            "aic": round(float(aic), 2),
            "bic": round(float(bic), 2),
            "n_observations": n,
            "n_parameters": k,
            "converged": iteration < max_iter - 1,
            "iterations": iteration + 1,
        }

    @classmethod
    def predict_probability(
        cls,
        X: np.ndarray,
        coefficients: np.ndarray,
        add_constant: bool = True,
    ) -> np.ndarray:
        """
        Predict P(Y=1|X) using fitted coefficients.

        Args:
            X: Design matrix
            coefficients: Fitted β vector
            add_constant: Add intercept

        Returns:
            Array of predicted probabilities
        """
        if add_constant:
            X = np.column_stack([np.ones(len(X)), X])
        return cls.sigmoid(X @ coefficients)


class IndexNumberBuilder:
    """
    Index number construction (ECO 203 — Economic Statistics).

    Implements standard index number methods used by statistical
    agencies worldwide for measuring price changes over time.

    Key indices:
    - Laspeyres: Pᴸ = Σp₁q₀/Σp₀q₀ (base period quantities)
    - Paasche: Pᴾ = Σp₁q₁/Σp₀q₁ (current period quantities)
    - Fisher: Pᶠ = √(Pᴸ × Pᴾ) (geometric mean — "ideal" index)
    - Törnqvist: Discrete Divisia approximation

    Used by:
    - Soko Pulse: Market price indices
    - Biashara Pulse: Activity indices
    - Tax Base: Revenue indices
    """

    @staticmethod
    def laspeyres(
        prices_base: np.ndarray,
        prices_current: np.ndarray,
        quantities_base: np.ndarray,
    ) -> float:
        """
        Laspeyres price index.

        Pᴸ = Σ(p₁ᵢ × q₀ᵢ) / Σ(p₀ᵢ × q₀ᵢ)

        Uses base period quantities as weights. Tends to overstate
        price increases (substitution bias).

        Args:
            prices_base: Base period prices
            prices_current: Current period prices
            quantities_base: Base period quantities (weights)

        Returns:
            Laspeyres index value (100 = no change)
        """
        numerator = np.sum(prices_current * quantities_base)
        denominator = np.sum(prices_base * quantities_base)
        return round(float(numerator / denominator * 100), 2)

    @staticmethod
    def paasche(
        prices_base: np.ndarray,
        prices_current: np.ndarray,
        quantities_current: np.ndarray,
    ) -> float:
        """
        Paasche price index.

        Pᴾ = Σ(p₁ᵢ × q₁ᵢ) / Σ(p₀ᵢ × q₁ᵢ)

        Uses current period quantities. Tends to understate
        price increases.

        Args:
            prices_base: Base period prices
            prices_current: Current period prices
            quantities_current: Current period quantities (weights)

        Returns:
            Paasche index value (100 = no change)
        """
        numerator = np.sum(prices_current * quantities_current)
        denominator = np.sum(prices_base * quantities_current)
        return round(float(numerator / denominator * 100), 2)

    @staticmethod
    def fisher(
        prices_base: np.ndarray,
        prices_current: np.ndarray,
        quantities_base: np.ndarray,
        quantities_current: np.ndarray,
    ) -> float:
        """
        Fisher "ideal" price index.

        Pᶠ = √(Pᴸ × Pᴾ)

        Geometric mean of Laspeyres and Paasche. Satisfies the
        factor reversal test and time reversal test. Diewert (1976)
        showed this is "superlative" — exact for flexible functional forms.

        Args:
            prices_base: Base period prices
            prices_current: Current period prices
            quantities_base: Base period quantities
            quantities_current: Current period quantities

        Returns:
            Fisher index value (100 = no change)
        """
        L = IndexNumberBuilder.laspeyres(prices_base, prices_current, quantities_base)
        P = IndexNumberBuilder.paasche(prices_base, prices_current, quantities_current)
        return round(float(np.sqrt(L * P)), 2)

    @staticmethod
    def tornqvist(
        prices_base: np.ndarray,
        prices_current: np.ndarray,
        shares_base: np.ndarray,
        shares_current: np.ndarray,
    ) -> float:
        """
        Törnqvist price index (discrete Divisia approximation).

        ln(Pᵀ) = Σ(½(s₀ᵢ + s₁ᵢ)) × ln(p₁ᵢ/p₀ᵢ)

        Uses arithmetic mean of base and current expenditure shares.
        Preferred for productivity and cost-of-living analysis.

        Args:
            prices_base: Base period prices
            prices_current: Current period prices
            shares_base: Base period expenditure shares
            shares_current: Current period expenditure shares

        Returns:
            Törnqvist index value (100 = no change)
        """
        avg_shares = 0.5 * (shares_base + shares_current)
        price_ratios = prices_current / prices_base
        log_index = np.sum(avg_shares * np.log(price_ratios))
        return round(float(np.exp(log_index) * 100), 2)


class TimeSeriesForecaster:
    """
    Time series forecasting (STA 244 — Time Series Analysis).

    Implements exponential smoothing methods for price and demand
    forecasting in Soko Pulse.

    Methods:
    - Simple Exponential Smoothing (SES): Level only
    - Holt's Linear Trend: Level + trend
    - Holt-Winters: Level + trend + seasonality

    State Space Formulation (Hyndman et al.): ETS models as
    innovations state space — unifying framework for all methods.
    """

    @staticmethod
    def simple_exponential_smoothing(
        data: np.ndarray,
        alpha: float = 0.3,
    ) -> Dict[str, Any]:
        """
        Simple Exponential Smoothing (SES).

        Sₜ₊₁ = α × Xₜ + (1-α) × Sₜ

        For data with no trend or seasonality.
        Optimal α minimizes in-sample MSE.

        Args:
            data: Time series data
            alpha: Smoothing parameter (0 < α < 1)

        Returns:
            Dict with smoothed values, forecast, and diagnostics
        """
        n = len(data)
        smoothed = np.zeros(n)
        smoothed[0] = data[0]

        for t in range(1, n):
            smoothed[t] = alpha * data[t] + (1 - alpha) * smoothed[t - 1]

        # One-step-ahead forecast
        forecast = smoothed[-1]

        # Residuals and diagnostics
        residuals = data - smoothed
        mse = np.mean(residuals ** 2)
        mape = np.mean(np.abs(residuals / np.maximum(data, 1e-10))) * 100

        # Prediction interval (simplified)
        std_resid = np.std(residuals)

        return {
            "forecast": round(float(forecast), 2),
            "confidence_interval_low": round(float(forecast - 1.96 * std_resid), 2),
            "confidence_interval_high": round(float(forecast + 1.96 * std_resid), 2),
            "alpha": alpha,
            "mse": round(float(mse), 4),
            "mape": round(float(mape), 2),
            "method": "simple_exponential_smoothing",
        }

    @staticmethod
    def holt_linear(
        data: np.ndarray,
        alpha: float = 0.3,
        beta: float = 0.1,
    ) -> Dict[str, Any]:
        """
        Holt's Linear Trend method.

        Level:    lₜ = α × Xₜ + (1-α) × (lₜ₋₁ + bₜ₋₁)
        Trend:    bₜ = β × (lₜ - lₜ₋₁) + (1-β) × bₜ₋₁
        Forecast: Ŝₜ₊ₕ = lₜ + h × bₜ

        For data with trend but no seasonality.

        Args:
            data: Time series data
            alpha: Level smoothing parameter
            beta: Trend smoothing parameter

        Returns:
            Dict with level, trend, forecast, and diagnostics
        """
        n = len(data)
        level = np.zeros(n)
        trend = np.zeros(n)

        # Initialize
        level[0] = data[0]
        trend[0] = (data[-1] - data[0]) / max(n - 1, 1)

        for t in range(1, n):
            level[t] = alpha * data[t] + (1 - alpha) * (level[t - 1] + trend[t - 1])
            trend[t] = beta * (level[t] - level[t - 1]) + (1 - beta) * trend[t - 1]

        # One-step-ahead forecast
        forecast = level[-1] + trend[-1]

        residuals = data - (level + np.roll(trend, 1))
        residuals[0] = 0
        mse = np.mean(residuals[1:] ** 2)
        std_resid = np.std(residuals[1:])

        return {
            "forecast": round(float(forecast), 2),
            "confidence_interval_low": round(float(forecast - 1.96 * std_resid), 2),
            "confidence_interval_high": round(float(forecast + 1.96 * std_resid), 2),
            "level": round(float(level[-1]), 2),
            "trend": round(float(trend[-1]), 2),
            "alpha": alpha,
            "beta": beta,
            "mse": round(float(mse), 4),
            "method": "holt_linear_trend",
        }


class HeckmanCorrection:
    """
    Heckman selection correction (ECO 424 — Econometrics).

    Addresses selection bias when the sample is not random.
    In Biashara Intelligence: only active businesses have
    transaction data → selection on activity.

    Two-step estimation (Heckman, 1979):
    Step 1: Probit selection model → compute Inverse Mills Ratio (λ)
    Step 2: OLS outcome model with λ as additional regressor

    The Inverse Mills Ratio: λ(z) = φ(z)/Φ(z)
    where φ = standard normal PDF, Φ = standard normal CDF

    Used by Alama Score to correct credit scoring for
    selection bias (only active businesses observed).
    """

    @staticmethod
    def inverse_mills_ratio(z: np.ndarray) -> np.ndarray:
        """
        Compute Inverse Mills Ratio: λ(z) = φ(z)/Φ(z)

        Args:
            z: Selection variable values

        Returns:
            Inverse Mills Ratio for each observation
        """
        return stats.norm.pdf(z) / np.maximum(stats.norm.cdf(z), 1e-10)

    @classmethod
    def two_step(
        cls,
        X_selection: np.ndarray,
        selection_indicator: np.ndarray,
        X_outcome: np.ndarray,
        y_outcome: np.ndarray,
    ) -> Dict[str, Any]:
        """
        Heckman two-step estimation.

        Step 1: Probit P(selection=1|X) → compute λ
        Step 2: OLS of Y on X and λ for selected observations

        Args:
            X_selection: Selection equation regressors
            selection_indicator: Binary selection indicator
            X_outcome: Outcome equation regressors
            y_outcome: Outcome variable (observed only for selected)

        Returns:
            Dict with corrected coefficients and selection statistics
        """
        # Step 1: Probit selection model
        n_sel = len(selection_indicator)
        X_sel_with_const = np.column_stack([np.ones(n_sel), X_selection])

        # Fit probit using MLE
        def neg_log_lik(beta):
            z = X_sel_with_const @ beta
            p = stats.norm.cdf(z)
            p = np.clip(p, 1e-10, 1 - 1e-10)
            ll = np.sum(
                selection_indicator * np.log(p)
                + (1 - selection_indicator) * np.log(1 - p)
            )
            return -ll

        from scipy.optimize import minimize

        beta0 = np.zeros(X_sel_with_const.shape[1])
        result = minimize(neg_log_lik, beta0, method="BFGS")
        beta_probit = result.x

        # Compute Inverse Mills Ratio for selected observations
        selected_mask = selection_indicator == 1
        z_selected = X_sel_with_const[selected_mask] @ beta_probit
        lambda_selected = cls.inverse_mills_ratio(z_selected)

        # Step 2: OLS with IMR correction
        X_out_selected = X_outcome[selected_mask]
        y_selected = y_outcome[selected_mask]
        X_augmented = np.column_stack([X_out_selected, lambda_selected])

        # OLS: β̂ = (X'X)⁻¹X'Y
        try:
            XtX_inv = np.linalg.inv(X_augmented.T @ X_augmented)
            beta_ols = XtX_inv @ (X_augmented.T @ y_selected)
        except np.linalg.LinAlgError:
            return {"error": "Singular matrix in outcome equation"}

        # Residuals
        residuals = y_selected - X_augmented @ beta_ols
        n_out = len(y_selected)
        k = X_augmented.shape[1]
        mse = np.sum(residuals ** 2) / (n_out - k)

        # Standard errors (need to account for generated regressor λ)
        # Simplified: use OLS SEs as approximation
        se = np.sqrt(np.diag(mse * XtX_inv))

        # Lambda coefficient (selection bias parameter)
        lambda_coeff = beta_ols[-1]
        lambda_se = se[-1]
        lambda_t = lambda_coeff / lambda_se if lambda_se > 0 else 0
        lambda_p = 2 * (1 - stats.norm.cdf(abs(lambda_t)))

        return {
            "selection_coefficients": beta_probit.tolist(),
            "outcome_coefficients": beta_ols[:-1].tolist(),
            "lambda_coefficient": round(float(lambda_coeff), 4),
            "lambda_standard_error": round(float(lambda_se), 4),
            "lambda_t_statistic": round(float(lambda_t), 4),
            "lambda_p_value": round(float(lambda_p), 4),
            "selection_bias_detected": lambda_p < 0.05,
            "n_selected": int(np.sum(selected_mask)),
            "n_total": n_sel,
            "selection_rate": round(float(np.mean(selected_mask)), 4),
        }


# Singleton instances
ols = OLSRegression()
logit = LogitModel()
index_builder = IndexNumberBuilder()
time_series = TimeSeriesForecaster()
heckman = HeckmanCorrection()
