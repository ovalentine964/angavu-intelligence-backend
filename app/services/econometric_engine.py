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


class ARIMAModel:
    """
    Full ARIMA(p,d,q) model (STA 244 — Time Series Analysis).

    Implements the Box-Jenkins methodology:
    1. Identification: Determine p, d, q via ACF/PACF and AIC/BIC
    2. Estimation: AR(p) via Yule-Walker, MA(q) via innovation algorithm
    3. Diagnostic checking: Ljung-Box test on residuals
    4. Forecasting: Multi-step ahead with prediction intervals

    Model: φ(B)(1-B)^d X_t = θ(B) ε_t
    where φ(B) = 1 - φ₁B - ... - φ_p B^p  (AR polynomial)
          θ(B) = 1 + θ₁B + ... + θ_q B^q  (MA polynomial)
          B = backshift operator, d = differencing order

    References:
    - Box, G.E.P. & Jenkins, G.M. (1976). Time Series Analysis:
      Forecasting and Control. Holden-Day.
    - Brockwell, P.J. & Davis, R.A. (2016). Introduction to Time
      Series and Forecasting. 3rd ed. Springer.
    - Hamilton, J.D. (1994). Time Series Analysis. Princeton.
    """

    def __init__(self, p: int = 1, d: int = 0, q: int = 0):
        self.p = p
        self.d = d
        self.q = q
        self.ar_coeffs: Optional[np.ndarray] = None
        self.ma_coeffs: Optional[np.ndarray] = None
        self.residuals: Optional[np.ndarray] = None
        self.sigma2: float = 0.0
        self._original_data: Optional[np.ndarray] = None
        self._diff_data: Optional[np.ndarray] = None

    @staticmethod
    def _difference(series: np.ndarray, d: int) -> np.ndarray:
        """Apply d-th order differencing: (1-B)^d X_t"""
        result = series.copy()
        for _ in range(d):
            result = np.diff(result)
        return result

    @staticmethod
    def _yule_walker(data: np.ndarray, p: int) -> Tuple[np.ndarray, float]:
        """
        Estimate AR(p) coefficients via Yule-Walker equations.

        Solves the system: Γ_p × φ = γ_p
        where Γ_p is the Toeplitz autocovariance matrix and
        γ_p is the autocovariance vector.

        Reference: Brockwell & Davis (2016), §5.1
        """
        n = len(data)
        mean = np.mean(data)
        centered = data - mean

        # Compute sample autocovariances γ(0), γ(1), ..., γ(p)
        gamma = np.zeros(p + 1)
        for k in range(p + 1):
            gamma[k] = np.sum(centered[:n - k] * centered[k:]) / n

        # Toeplitz autocovariance matrix Γ_p
        Gamma = np.zeros((p, p))
        for i in range(p):
            for j in range(p):
                Gamma[i, j] = gamma[abs(i - j)]

        # Solve Yule-Walker: Γ_p × φ = γ_p
        try:
            phi = np.linalg.solve(Gamma, gamma[1:p + 1])
        except np.linalg.LinAlgError:
            phi = np.zeros(p)

        # Innovation variance: σ² = γ(0) - φ' × γ_p
        sigma2 = gamma[0] - phi @ gamma[1:p + 1]
        sigma2 = max(sigma2, 1e-10)

        return phi, float(sigma2)

    @staticmethod
    def _innovation_ma(data: np.ndarray, q: int, ar_coeffs: np.ndarray = None,
                       ar_sigma2: float = 1.0) -> Tuple[np.ndarray, float]:
        """
        Estimate MA(q) coefficients via the innovation algorithm.

        For a pure MA(q) process, the innovation algorithm (Durbin, 1959)
        computes the MA coefficients from the autocovariance function.

        For ARMA(p,q), we apply the innovation algorithm to the
        autocovariances of the AR-residual process.

        Reference:
        - Durbin, J. (1959). Efficient estimation of parameters in
          moving-average models. Biometrika, 46(3-4), 306-316.
        - Brockwell & Davis (2016), §5.3
        """
        n = len(data)

        # Compute autocovariances of the residual series
        if ar_coeffs is not None:
            # For ARMA: compute autocovariances of the AR-filtered series
            p = len(ar_coeffs)
            resid = data.copy()
            for t in range(p, n):
                for j in range(p):
                    resid[t] -= ar_coeffs[j] * data[t - j - 1]
            centered = resid - np.mean(resid)
        else:
            centered = data - np.mean(data)

        # Autocovariances up to lag q
        gamma = np.zeros(q + 1)
        for k in range(q + 1):
            gamma[k] = np.sum(centered[:n - k] * centered[k:]) / n

        if q == 0:
            return np.array([]), max(float(gamma[0]), 1e-10)

        # Innovation algorithm
        # v[0] = γ(0), then iteratively compute θ coefficients
        v = np.zeros(q + 1)
        theta = np.zeros((q + 1, q + 1))

        v[0] = gamma[0] if gamma[0] > 0 else 1e-10

        for j in range(1, q + 1):
            # θ_{j,j} = (γ(j) - Σ_{k=0}^{j-1} θ_{j-1,k} × γ(j-k-1+1)) / v[j-1]
            # Simplified: use autocovariance matching
            num = gamma[j]
            for k in range(j):
                num -= theta[j - 1, k] * gamma[abs(j - k)]
            theta[j, j] = num / max(v[j - 1], 1e-10)

            for k in range(j):
                theta[j, k] = theta[j - 1, k] + theta[j, j] * theta[j - 1, j - k - 1]

            v[j] = v[j - 1] * (1 - theta[j, j] ** 2)
            if v[j] <= 0:
                v[j] = 1e-10

        ma_coeffs = theta[q, :q]
        sigma2 = float(v[q])

        return ma_coeffs, max(sigma2, 1e-10)

    def fit(self, data: np.ndarray) -> Dict[str, Any]:
        """
        Fit ARIMA(p,d,q) model to time series data.

        Procedure:
        1. Difference the series d times to achieve stationarity
        2. Estimate AR(p) coefficients via Yule-Walker
        3. Estimate MA(q) coefficients via innovation algorithm
        4. Compute residuals and diagnostics

        Args:
            data: Raw time series (1D array)

        Returns:
            Dict with estimated parameters, diagnostics, and fit statistics
        """
        self._original_data = data.copy()
        n = len(data)

        # Step 1: Difference
        if self.d > 0:
            diff_data = self._difference(data, self.d)
        else:
            diff_data = data.copy()
        self._diff_data = diff_data

        n_diff = len(diff_data)
        if n_diff < self.p + self.q + 2:
            return {"error": f"Insufficient observations after differencing: {n_diff} < {self.p + self.q + 2}"}

        # Step 2: AR(p) estimation via Yule-Walker
        if self.p > 0:
            self.ar_coeffs, ar_sigma2 = self._yule_walker(diff_data, self.p)
        else:
            self.ar_coeffs = np.array([])
            ar_sigma2 = np.var(diff_data)

        # Step 3: MA(q) estimation via innovation algorithm
        if self.q > 0:
            self.ma_coeffs, self.sigma2 = self._innovation_ma(
                diff_data, self.q,
                ar_coeffs=self.ar_coeffs if self.p > 0 else None,
                ar_sigma2=ar_sigma2,
            )
        else:
            self.ma_coeffs = np.array([])
            self.sigma2 = ar_sigma2

        # Step 4: Compute residuals
        # Residuals = differenced series - AR fitted values - MA terms
        self.residuals = self._compute_residuals(diff_data)

        # Diagnostics
        n_resid = len(self.residuals)
        k = self.p + self.q + 1  # parameters (AR + MA + intercept)
        ss_res = np.sum(self.residuals ** 2)
        mse = ss_res / max(n_resid - k, 1)

        # Log-likelihood (Gaussian assumption)
        log_lik = -0.5 * n_resid * (np.log(2 * np.pi * mse) + 1)

        # Information criteria
        aic = -2 * log_lik + 2 * k
        bic = -2 * log_lik + k * np.log(n_resid)

        # Ljung-Box test
        lb = self._ljung_box(self.residuals)

        return {
            "order": {"p": self.p, "d": self.d, "q": self.q},
            "ar_coefficients": self.ar_coeffs.tolist() if self.p > 0 else [],
            "ma_coefficients": self.ma_coeffs.tolist() if self.q > 0 else [],
            "sigma2": round(float(self.sigma2), 6),
            "log_likelihood": round(float(log_lik), 4),
            "aic": round(float(aic), 2),
            "bic": round(float(bic), 2),
            "n_observations": n,
            "n_effective": n_resid,
            "n_parameters": k,
            "ljung_box": lb,
            "method": f"ARIMA({self.p},{self.d},{self.q})",
        }

    def _compute_residuals(self, diff_data: np.ndarray) -> np.ndarray:
        """Compute model residuals from differenced data."""
        n = len(diff_data)
        p = self.p
        q = self.q
        start = max(p, q)
        residuals = np.zeros(n)

        for t in range(start, n):
            fitted = 0.0
            # AR component
            for j in range(p):
                fitted += self.ar_coeffs[j] * diff_data[t - j - 1]
            # MA component (using past residuals)
            for j in range(q):
                fitted += self.ma_coeffs[j] * residuals[t - j - 1]
            residuals[t] = diff_data[t] - fitted

        return residuals[start:]

    @staticmethod
    def _ljung_box(residuals: np.ndarray, max_lag: int = None) -> Dict[str, Any]:
        """
        Ljung-Box portmanteau test for residual autocorrelation.

        H₀: Residuals are white noise (no autocorrelation up to lag m)
        Q(m) = n(n+2) Σ_{k=1}^{m} r̂²_k / (n-k)
        Under H₀: Q(m) ~ χ²(m)

        Reference: Ljung, G.M. & Box, G.E.P. (1978). On a measure of
        lack of fit in time series models. Biometrika, 65(2), 297-303.
        """
        n = len(residuals)
        if max_lag is None:
            max_lag = min(20, n // 5)
        max_lag = max(1, min(max_lag, n - 1))

        mean = np.mean(residuals)
        centered = residuals - mean
        var0 = np.sum(centered ** 2) / n
        if var0 < 1e-15:
            return {"Q_statistic": 0.0, "p_value": 1.0, "lags": max_lag,
                    "autocorrelations": []}

        acf = []
        q_stat = 0.0
        for k in range(1, max_lag + 1):
            rk = np.sum(centered[:n - k] * centered[k:]) / (n * var0)
            acf.append(round(float(rk), 4))
            q_stat += rk ** 2 / (n - k)

        q_stat *= n * (n + 2)
        p_value = 1 - stats.chi2.cdf(q_stat, max_lag)

        return {
            "Q_statistic": round(float(q_stat), 4),
            "p_value": round(float(p_value), 4),
            "lags": max_lag,
            "autocorrelations": acf,
            "white_noise": p_value > 0.05,
        }

    def forecast(self, steps: int = 12, alpha: float = 0.05) -> Dict[str, Any]:
        """
        Multi-step ahead forecasting with prediction intervals.

        For ARIMA, the minimum MSE forecast is:
        Ŷ_{n+h} = μ + Σ φ_i Ŷ_{n+h-i} + Σ θ_j â_{n+h-j}
        where future â = 0 (best guess).

        Prediction intervals widen with horizon:
        Var(e(h)) = σ² Σ ψ²_j  (ψ-weights from MA(∞) representation)

        Args:
            steps: Number of periods to forecast
            alpha: Significance level (default 0.05 → 95% CI)

        Returns:
            Dict with point forecasts and prediction intervals
        """
        if self.ar_coeffs is None:
            return {"error": "Model not fitted. Call fit() first."}

        diff_data = self._diff_data
        residuals = self.residuals
        p = self.p
        q = self.q

        # Extend the differenced series with forecasts
        extended = list(diff_data)
        extended_resid = list(residuals)
        forecasts_diff = []

        for h in range(steps):
            fc = 0.0
            t = len(extended)
            # AR component
            for j in range(p):
                idx = t - j - 1
                if idx >= 0:
                    fc += self.ar_coeffs[j] * extended[idx]
            # MA component (future shocks = 0)
            for j in range(q):
                idx = t - j - 1
                if idx >= 0 and idx < len(extended_resid):
                    fc += self.ma_coeffs[j] * extended_resid[idx]

            forecasts_diff.append(fc)
            extended.append(fc)
            extended_resid.append(0.0)  # future residual = 0

        # If differenced, integrate back to level forecasts
        if self.d > 0:
            last_values = self._original_data[-self.d:].tolist()
            forecasts_level = []
            # For d=1: forecast_level = last_level + forecast_diff
            # For d=2: cumulative sum approach
            integrated = last_values + forecasts_diff
            for _ in range(self.d):
                integrated = np.cumsum(integrated)
            forecasts_level = integrated[self.d:].tolist()
        else:
            forecasts_level = forecasts_diff

        # Prediction intervals via simulation (psi-weight approximation)
        # Use sqrt(h) scaling as simple approximation
        z = stats.norm.ppf(1 - alpha / 2)
        sigma = np.sqrt(self.sigma2)
        intervals = []
        for h in range(steps):
            # Width grows with forecast horizon
            width = z * sigma * np.sqrt(h + 1)
            intervals.append({
                "step": h + 1,
                "forecast": round(float(forecasts_level[h]), 4),
                "lower": round(float(forecasts_level[h] - width), 4),
                "upper": round(float(forecasts_level[h] + width), 4),
            })

        return {
            "forecasts": intervals,
            "horizon": steps,
            "confidence_level": 1 - alpha,
            "sigma": round(float(sigma), 6),
            "method": f"ARIMA({self.p},{self.d},{self.q})",
        }

    @classmethod
    def auto_select(cls, data: np.ndarray, max_p: int = 5, max_d: int = 2,
                    max_q: int = 5) -> Dict[str, Any]:
        """
        Automatic ARIMA order selection via AIC/BIC grid search.

        Tests all (p,d,q) combinations up to the specified maxima
        and selects the model with the lowest BIC (parsimonious).

        Reference: Hyndman, R.J. & Khandakar, Y. (2008). Automatic
        time series forecasting: the forecast package for R. JSS.

        Args:
            data: Time series data
            max_p: Maximum AR order to test
            max_d: Maximum differencing order to test
            max_q: Maximum MA order to test

        Returns:
            Dict with best model parameters and comparison table
        """
        results = []
        best_bic = np.inf
        best_order = (0, 0, 0)

        for d in range(max_d + 1):
            if d > 0:
                diff_data = cls._difference(data, d)
            else:
                diff_data = data.copy()

            n_diff = len(diff_data)
            if n_diff < 10:
                continue

            for p in range(max_p + 1):
                for q in range(max_q + 1):
                    if p == 0 and q == 0:
                        continue
                    if p + q >= n_diff - 2:
                        continue

                    try:
                        model = cls(p=p, d=d, q=q)
                        result = model.fit(data)
                        if "error" in result:
                            continue

                        bic = result["bic"]
                        results.append({
                            "order": f"({p},{d},{q})",
                            "aic": result["aic"],
                            "bic": bic,
                            "log_lik": result["log_likelihood"],
                        })

                        if bic < best_bic:
                            best_bic = bic
                            best_order = (p, d, q)
                    except Exception:
                        continue

        # Fit the best model
        best_model = cls(p=best_order[0], d=best_order[1], q=best_order[2])
        best_fit = best_model.fit(data)

        # Sort by BIC
        results.sort(key=lambda x: x["bic"])

        return {
            "best_order": {"p": best_order[0], "d": best_order[1], "q": best_order[2]},
            "best_fit": best_fit,
            "top_models": results[:10],
            "total_models_tested": len(results),
        }


class VARModel:
    """
    Vector Autoregression (VAR) model (STA 244 — Time Series Analysis).

    A VAR(p) model for k endogenous variables:
    Y_t = c + A₁ Y_{t-1} + ... + A_p Y_{t-p} + ε_t
    where Y_t is k×1, each A_i is k×k, and ε_t ~ N(0, Σ).

    Estimation: Equation-by-equation OLS (equivalent to SUR when
    regressors are identical across equations).

    Applications in Biashara Intelligence:
    - Lead-lag analysis: Does M-Pesa volume Granger-cause prices?
    - Spillover effects: Cross-market price transmission
    - Policy simulation: Impulse response to external shocks

    References:
    - Sims, C.A. (1980). Macroeconomics and reality. Econometrica, 48(1), 1-48.
    - Lütkepohl, H. (2005). New Introduction to Multiple Time Series
      Analysis. 2nd ed. Springer.
    - Hamilton, J.D. (1994). Time Series Analysis. Princeton. Ch. 11.
    """

    def __init__(self, p: int = 1):
        self.p = p
        self.coefficients: Optional[np.ndarray] = None  # (k, k*p+1) — intercept + lags
        self.sigma: Optional[np.ndarray] = None  # residual covariance
        self.variable_names: Optional[List[str]] = None
        self._data: Optional[np.ndarray] = None
        self._residuals: Optional[np.ndarray] = None

    def fit(self, data: np.ndarray, variable_names: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Fit VAR(p) model via equation-by-equation OLS.

        The system in matrix form:
        Y = X B + E
        where Y is (T-p)×k, X is (T-p)×(kp+1), B is (kp+1)×k.
        OLS: B̂ = (X'X)⁻¹ X'Y

        Args:
            data: (T × k) matrix, each column is one variable
            variable_names: Optional list of variable names

        Returns:
            Dict with coefficient matrices, diagnostics, Granger tests
        """
        T, k = data.shape
        self._data = data
        self.variable_names = variable_names or [f"y{i+1}" for i in range(k)]

        if T <= self.p + k + 1:
            return {"error": f"Insufficient observations: {T} for VAR({self.p}) with {k} variables"}

        # Build lag matrix: [1, Y_{t-1}', Y_{t-2}', ..., Y_{t-p}']
        n_obs = T - self.p
        X = np.ones((n_obs, k * self.p + 1))
        for lag in range(1, self.p + 1):
            X[:, 1 + (lag - 1) * k: 1 + lag * k] = data[self.p - lag:T - lag]

        Y = data[self.p:]

        # OLS: B̂ = (X'X)⁻¹ X'Y
        try:
            XtX_inv = np.linalg.inv(X.T @ X)
            B_hat = XtX_inv @ (X.T @ Y)
        except np.linalg.LinAlgError:
            return {"error": "Singular matrix in VAR estimation"}

        self.coefficients = B_hat.T  # (k, kp+1)

        # Residuals
        E = Y - X @ B_hat
        self._residuals = E

        # Residual covariance matrix Σ̂ = E'E / (T - kp - 1)
        df = n_obs - (k * self.p + 1)
        self.sigma = (E.T @ E) / max(df, 1)

        # Log-likelihood (multivariate normal)
        sign, logdet = np.linalg.slogdet(self.sigma)
        log_lik = -0.5 * n_obs * (k * np.log(2 * np.pi) + logdet + k)

        # Information criteria
        n_params = k * (k * self.p + 1)
        aic = -2 * log_lik + 2 * n_params
        bic = -2 * log_lik + n_params * np.log(n_obs)

        # Per-equation statistics
        equations = {}
        for i, name in enumerate(self.variable_names):
            y_i = Y[:, i]
            resid_i = E[:, i]
            ss_res = np.sum(resid_i ** 2)
            ss_tot = np.sum((y_i - np.mean(y_i)) ** 2)
            r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0

            coef_i = B_hat[:, i]
            se_i = np.sqrt(np.diag(XtX_inv) * (ss_res / max(df, 1)))
            t_i = coef_i / np.maximum(se_i, 1e-10)
            p_i = 2 * (1 - stats.t.cdf(np.abs(t_i), df=max(df, 1)))

            equations[name] = {
                "coefficients": coef_i.tolist(),
                "standard_errors": se_i.tolist(),
                "t_statistics": t_i.tolist(),
                "p_values": p_i.tolist(),
                "r_squared": round(float(r2), 4),
                "residual_std": round(float(np.std(resid_i)), 6),
            }

        # Granger causality tests
        granger = self._granger_causality_tests(X, Y, B_hat, k, n_obs, df)

        return {
            "order": self.p,
            "n_variables": k,
            "variable_names": self.variable_names,
            "n_observations": n_obs,
            "equations": equations,
            "log_likelihood": round(float(log_lik), 4),
            "aic": round(float(aic), 2),
            "bic": round(float(bic), 2),
            "residual_covariance": self.sigma.tolist(),
            "granger_causality": granger,
            "method": f"VAR({self.p})",
        }

    def _granger_causality_tests(self, X: np.ndarray, Y: np.ndarray,
                                 B_hat: np.ndarray, k: int,
                                 n_obs: int, df: int) -> List[Dict[str, Any]]:
        """
        Granger causality F-tests.

        For each pair (x_j → x_i), test H₀: all lagged coefficients
        of x_j in equation for x_i are zero.

        F = [(RSS_restricted - RSS_unrestricted) / p] /
            [RSS_unrestricted / (T - kp - 1)]
        Under H₀: F ~ F(p, T - kp - 1)

        Reference: Granger, C.W.J. (1969). Investigating causal
        relations by econometric models and cross-spectral methods.
        Econometrica, 37(3), 424-438.
        """
        results = []
        p = self.p
        names = self.variable_names

        for i in range(k):
            for j in range(k):
                if i == j:
                    continue

                # Identify columns for variable j across all lags
                restrict_cols = []
                for lag in range(1, p + 1):
                    restrict_cols.append(1 + (lag - 1) * k + j)  # +1 for intercept

                # Restricted model: zero out lagged j coefficients
                X_restricted = X.copy()
                X_restricted[:, restrict_cols] = 0

                B_restricted = np.linalg.lstsq(X_restricted, Y[:, i], rcond=None)[0]
                rss_unrestricted = np.sum((Y[:, i] - X @ B_hat[:, i]) ** 2)
                rss_restricted = np.sum((Y[:, i] - X_restricted @ B_restricted) ** 2)

                if rss_unrestricted < 1e-15:
                    f_stat = 0.0
                    p_value = 1.0
                else:
                    f_stat = ((rss_restricted - rss_unrestricted) / p) / \
                             (rss_unrestricted / max(df, 1))
                    p_value = 1 - stats.f.cdf(f_stat, p, max(df, 1))

                results.append({
                    "cause": names[j],
                    "effect": names[i],
                    "direction": f"{names[j]} → {names[i]}",
                    "F_statistic": round(float(f_stat), 4),
                    "p_value": round(float(p_value), 4),
                    "df_numerator": p,
                    "df_denominator": max(df, 1),
                    "significant": p_value < 0.05,
                })

        return results

    def impulse_response(self, periods: int = 20) -> Dict[str, Any]:
        """
        Compute impulse response functions (IRFs).

        IRF(h) = Ψ_h where Y_t = Σ_{h=0}^{∞} Ψ_h ε_{t-h}
        Recursive: Ψ_0 = I, Ψ_h = Σ_{j=1}^{min(h,p)} A_j Ψ_{h-j}

        Uses Cholesky decomposition for orthogonalized shocks:
        P = cholesky(Σ), so structural shock = P⁻¹ ε_t

        Reference: Sims, C.A. (1980). Macroeconomics and reality.
        Econometrica, 48(1), 1-48.
        """
        if self.coefficients is None:
            return {"error": "Model not fitted. Call fit() first."}

        k = self.sigma.shape[0]
        p = self.p

        # Extract A matrices from coefficients (k × kp+1), skip intercept column
        A_mats = []
        for lag in range(1, p + 1):
            A_mats.append(self.coefficients[:, 1 + (lag - 1) * k: 1 + lag * k])

        # Cholesky decomposition of Σ for orthogonalized IRFs
        try:
            P = np.linalg.cholesky(self.sigma)
        except np.linalg.LinAlgError:
            P = np.eye(k)

        # Compute IRFs
        irf = np.zeros((periods + 1, k, k))
        irf[0] = P  # Ψ_0 = P (impact)

        for h in range(1, periods + 1):
            for j in range(min(h, p)):
                irf[h] += A_mats[j] @ irf[h - j - 1]

        # Format by variable names
        names = self.variable_names
        response = []
        for shock_var in range(k):
            for resp_var in range(k):
                path = [round(float(irf[h, resp_var, shock_var]), 6)
                        for h in range(periods + 1)]
                response.append({
                    "shock": names[shock_var],
                    "response": names[resp_var],
                    "path": path,
                })

        return {
            "periods": periods,
            "impulse_responses": response,
            "orthogonalized": True,
            "ordering": names,
        }

    def variance_decomposition(self, periods: int = 20) -> Dict[str, Any]:
        """
        Forecast error variance decomposition (FEVD).

        Shows what fraction of the h-step forecast error variance
        of each variable is attributable to each structural shock.

        FEVD_{ij}(h) = Σ_{s=0}^{h} (Ψ_s P)²_{ij} /
                       Σ_{s=0}^{h} Σ_{l=1}^{k} (Ψ_s P)²_{il}

        Reference: Lütkepohl, H. (2005). New Introduction to Multiple
        Time Series Analysis. Springer. §2.3.
        """
        if self.coefficients is None:
            return {"error": "Model not fitted. Call fit() first."}

        k = self.sigma.shape[0]
        p = self.p
        names = self.variable_names

        # Extract A matrices
        A_mats = []
        for lag in range(1, p + 1):
            A_mats.append(self.coefficients[:, 1 + (lag - 1) * k: 1 + lag * k])

        try:
            P = np.linalg.cholesky(self.sigma)
        except np.linalg.LinAlgError:
            P = np.eye(k)

        # Compute Ψ matrices
        psi = np.zeros((periods + 1, k, k))
        psi[0] = np.eye(k)
        for h in range(1, periods + 1):
            for j in range(min(h, p)):
                psi[h] += A_mats[j] @ psi[h - j - 1]

        # FEVD
        names = self.variable_names
        decomposition = []
        for resp_var in range(k):
            # Cumulative variance contributions at each horizon
            cum_var = np.zeros((periods + 1, k))
            for h in range(periods + 1):
                PsiP = psi[h] @ P
                for shock in range(k):
                    cum_var[h, shock] = PsiP[resp_var, shock] ** 2

            # Total variance at each horizon
            total_var = np.sum(cum_var, axis=1, keepdims=True)
            total_var = np.maximum(total_var, 1e-15)

            # Proportions at final horizon
            proportions = cum_var[-1] / total_var[-1]
            decomposition.append({
                "variable": names[resp_var],
                "decomposition": {
                    names[shock]: round(float(proportions[shock]), 4)
                    for shock in range(k)
                },
                "horizon": periods,
            })

        return {
            "periods": periods,
            "variance_decomposition": decomposition,
            "ordering": names,
        }


class CointegrationTester:
    """
    Cointegration testing (STA 244 — Time Series Analysis).

    Two non-stationary series X_t and Y_t are cointegrated if
    a linear combination βX_t - Y_t is stationary. This implies
    a long-run equilibrium relationship despite each series
    having unit roots.

    Engle-Granger two-step method:
    Step 1: Estimate cointegrating regression Y_t = α + β X_t + ε_t
    Step 2: Test residuals ε̂_t for stationarity (ADF test)

    If cointegrated → estimate Error Correction Model (ECM):
    ΔY_t = γ(ε̂_{t-1}) + Σ a_i ΔY_{t-i} + Σ b_i ΔX_{t-i} + u_t
    where γ < 0 measures speed of adjustment to equilibrium.

    Applications in Biashara Intelligence:
    - Cross-border price linkages (Kenya-Uganda, Kenya-Tanzania)
    - Commodity price parity (Nairobi vs Mombasa wholesale)
    - Exchange rate pass-through to domestic prices

    References:
    - Engle, R.F. & Granger, C.W.J. (1987). Co-integration and error
      correction: Representation, estimation, and testing. Econometrica,
      55(2), 251-276.
    - Johansen, S. (1991). Estimation and hypothesis testing of
      cointegration vectors in Gaussian vector autoregressive models.
      Econometrica, 59(6), 1551-1580.
    - Hamilton, J.D. (1994). Time Series Analysis. Princeton. Ch. 19-20.
    """

    @staticmethod
    def _adf_test(series: np.ndarray, max_lag: int = None,
                  regression: str = "c") -> Dict[str, Any]:
        """
        Augmented Dickey-Fuller test for unit root.

        Δy_t = α + ρ y_{t-1} + Σ δ_i Δy_{t-i} + ε_t
        H₀: ρ = 0 (unit root) vs H₁: ρ < 0 (stationary)

        Test statistic: τ = ρ̂ / SE(ρ̂)
        Critical values from Fuller (1976) tables (not standard t).

        Args:
            series: Time series to test
            max_lag: Maximum lag for augmentation (default: sqrt(n))
            regression: "c" for constant, "ct" for constant+trend, "n" for none

        Returns:
            Dict with test statistic, critical values, conclusion

        Reference:
        - Dickey, D.A. & Fuller, W.A. (1979). Distribution of the
          estimators for autoregressive time series with a unit root.
          JASA, 74(366), 427-431.
        """
        n = len(series)
        if max_lag is None:
            max_lag = int(np.ceil(n ** 0.5))
        max_lag = max(0, min(max_lag, (n - 5) // 2))

        # Build regression: Δy_t = α + ρ y_{t-1} + Σ δ_i Δy_{t-i} + ε_t
        dy = np.diff(series)
        y_lag = series[:-1]
        T = len(dy) - max_lag

        if T < 5:
            return {"error": "Insufficient observations for ADF test"}

        # Build design matrix
        cols = []
        if regression in ("c", "ct"):
            cols.append(np.ones(T))  # constant
        if regression == "ct":
            cols.append(np.arange(T, dtype=float))  # trend
        cols.append(y_lag[max_lag:])  # y_{t-1}
        for lag in range(1, max_lag + 1):
            cols.append(dy[max_lag - lag:-lag])  # Δy_{t-i}

        X = np.column_stack(cols)
        y = dy[max_lag:]

        # OLS
        try:
            XtX_inv = np.linalg.inv(X.T @ X)
            beta = XtX_inv @ (X.T @ y)
        except np.linalg.LinAlgError:
            return {"error": "Singular matrix in ADF regression"}

        residuals = y - X @ beta
        mse = np.sum(residuals ** 2) / (T - X.shape[1])
        se = np.sqrt(np.diag(mse * XtX_inv))

        # The coefficient on y_{t-1}
        rho_idx = 2 if regression == "ct" else (1 if regression == "c" else 0)
        rho_hat = beta[rho_idx]
        se_rho = se[rho_idx]

        # ADF test statistic
        adf_stat = rho_hat / se_rho if se_rho > 0 else 0

        # MacKinnon (1996) approximate critical values
        critical_values = {
            "1%": -3.43 if regression == "ct" else (-3.43 if regression == "c" else -2.58),
            "5%": -2.86 if regression == "ct" else (-2.86 if regression == "c" else -1.95),
            "10%": -2.57 if regression == "ct" else (-2.57 if regression == "c" else -1.62),
        }

        stationary = adf_stat < critical_values["5%"]

        return {
            "ADF_statistic": round(float(adf_stat), 4),
            "critical_values": critical_values,
            "p_value_approx": round(float(
                stats.norm.cdf(adf_stat) if adf_stat < -2.86
                else 0.5  # rough approximation
            ), 4),
            "lags_used": max_lag,
            "n_obs": T,
            "regression": regression,
            "stationary": stationary,
            "conclusion": "Reject H₀ — series is stationary" if stationary
                          else "Fail to reject H₀ — series has unit root",
        }

    @classmethod
    def engle_granger(cls, y: np.ndarray, x: np.ndarray,
                      max_lag_adf: int = None) -> Dict[str, Any]:
        """
        Engle-Granger two-step cointegration test.

        Step 1: OLS regression  y_t = α + β x_t + ε_t
        Step 2: ADF test on residuals ε̂_t
                (critical values are non-standard — Engle-Granger tables)

        If cointegrated, estimate ECM (Error Correction Model).

        Note: The ADF critical values for cointegration residuals are
        more negative than standard ADF (larger rejection region).
        We use the standard 5% value as a conservative approximation.

        Args:
            y: Dependent variable (1D array)
            x: Independent variable (1D array)
            max_lag_adf: Max lag for ADF test on residuals

        Returns:
            Dict with cointegrating vector, test result, and ECM

        Reference:
        - Engle, R.F. & Granger, C.W.J. (1987). Co-integration and
          error correction. Econometrica, 55(2), 251-276.
        """
        n = len(y)
        if len(x) != n:
            return {"error": "y and x must have the same length"}
        if n < 10:
            return {"error": "Insufficient observations (need >= 10)"}

        # Step 1: Cointegrating regression y_t = α + β x_t + ε_t
        X_reg = np.column_stack([np.ones(n), x])
        try:
            XtX_inv = np.linalg.inv(X_reg.T @ X_reg)
            beta_hat = XtX_inv @ (X_reg.T @ y)
        except np.linalg.LinAlgError:
            return {"error": "Singular matrix in cointegrating regression"}

        alpha_hat, beta_coint = beta_hat[0], beta_hat[1]
        residuals = y - X_reg @ beta_hat

        # Step 2: ADF test on residuals
        # Use more conservative critical values for cointegration test
        adf_result = cls._adf_test(residuals, max_lag=max_lag_adf, regression="c")
        if "error" in adf_result:
            return adf_result

        # Override critical values with Engle-Granger (1987) values
        # These are more negative than standard ADF
        eg_critical = {
            "1%": -3.90,
            "5%": -3.34,
            "10%": -3.04,
        }
        cointegrated = adf_result["ADF_statistic"] < eg_critical["5%"]

        # Step 3: Error Correction Model (if cointegrated)
        ecm_result = None
        if cointegrated:
            ecm_result = cls._estimate_ecm(y, x, residuals, alpha_hat, beta_coint)

        return {
            "cointegrating_vector": {
                "alpha": round(float(alpha_hat), 6),
                "beta": round(float(beta_coint), 6),
            },
            "engle_granger_test": {
                "ADF_statistic": adf_result["ADF_statistic"],
                "critical_values": eg_critical,
                "lags_used": adf_result["lags_used"],
                "cointegrated": cointegrated,
                "conclusion": "Cointegrated — long-run equilibrium exists" if cointegrated
                              else "Not cointegrated — no stable long-run relationship",
            },
            "residual_diagnostics": {
                "mean": round(float(np.mean(residuals)), 6),
                "std": round(float(np.std(residuals)), 6),
                "adf_on_residuals": adf_result,
            },
            "error_correction_model": ecm_result,
            "method": "Engle-Granger two-step",
        }

    @staticmethod
    def _estimate_ecm(y: np.ndarray, x: np.ndarray,
                      coint_residuals: np.ndarray,
                      alpha: float, beta: float,
                      max_lag: int = None) -> Dict[str, Any]:
        """
        Estimate Error Correction Model (ECM).

        Δy_t = γ ε̂_{t-1} + Σ a_i Δy_{t-i} + Σ b_i Δx_{t-i} + u_t

        where ε̂_{t-1} is the lagged cointegrating residual (error
        correction term), and γ < 0 is the speed of adjustment.

        Half-life of deviations: h = ln(0.5) / ln(1 + γ)

        Args:
            y: Level of dependent variable
            x: Level of independent variable
            coint_residuals: Residuals from cointegrating regression
            alpha: Constant from cointegrating regression
            beta: Slope from cointegrating regression
            max_lag: Number of lagged differences to include

        Returns:
            Dict with ECM coefficients and diagnostics
        """
        n = len(y)
        if max_lag is None:
            max_lag = min(4, int(n ** 0.5))

        dy = np.diff(y)
        dx = np.diff(x)
        ec_term = coint_residuals[:-1]  # ε̂_{t-1}

        T = len(dy) - max_lag
        if T < 5:
            return {"error": "Insufficient observations for ECM"}

        # Build ECM design matrix
        cols = [ec_term[max_lag:]]  # error correction term
        for lag in range(1, max_lag + 1):
            cols.append(dy[max_lag - lag:-lag] if lag < len(dy) else dy[:T])
        for lag in range(1, max_lag + 1):
            start = max_lag - lag
            end = len(dx) - lag
            if end - start >= T:
                cols.append(dx[start:start + T])

        X_ecm = np.column_stack(cols)
        y_ecm = dy[max_lag:max_lag + T]

        if X_ecm.shape[0] != len(y_ecm):
            min_len = min(X_ecm.shape[0], len(y_ecm))
            X_ecm = X_ecm[:min_len]
            y_ecm = y_ecm[:min_len]

        # OLS
        try:
            XtX_inv = np.linalg.inv(X_ecm.T @ X_ecm)
            ecm_beta = XtX_inv @ (X_ecm.T @ y_ecm)
        except np.linalg.LinAlgError:
            return {"error": "Singular matrix in ECM estimation"}

        residuals_ecm = y_ecm - X_ecm @ ecm_beta
        df = len(y_ecm) - X_ecm.shape[1]
        mse = np.sum(residuals_ecm ** 2) / max(df, 1)
        se = np.sqrt(np.diag(mse * XtX_inv))
        t_stats = ecm_beta / np.maximum(se, 1e-10)
        p_values = 2 * (1 - stats.t.cdf(np.abs(t_stats), df=max(df, 1)))

        gamma = ecm_beta[0]  # speed of adjustment
        half_life = np.log(0.5) / np.log(1 + gamma) if -1 < gamma < 0 else float("inf")

        # R²
        ss_res = np.sum(residuals_ecm ** 2)
        ss_tot = np.sum((y_ecm - np.mean(y_ecm)) ** 2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0

        return {
            "speed_of_adjustment": round(float(gamma), 6),
            "speed_of_adjustment_t": round(float(t_stats[0]), 4),
            "speed_of_adjustment_p": round(float(p_values[0]), 4),
            "half_life_periods": round(float(half_life), 2) if half_life != float("inf") else None,
            "equilibrium_restoring": gamma < 0 and p_values[0] < 0.05,
            "ecm_coefficients": ecm_beta.tolist(),
            "ecm_standard_errors": se.tolist(),
            "ecm_t_statistics": t_stats.tolist(),
            "ecm_p_values": p_values.tolist(),
            "r_squared": round(float(r2), 4),
            "n_obs": len(y_ecm),
            "max_lag": max_lag,
        }


# Singleton instances
ols = OLSRegression()
logit = LogitModel()
index_builder = IndexNumberBuilder()
time_series = TimeSeriesForecaster()
heckman = HeckmanCorrection()
arima = ARIMAModel()
var_model = VARModel()
cointegration = CointegrationTester()
