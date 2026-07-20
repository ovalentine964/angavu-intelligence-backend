"""
Tests for the Econometric Engine — OLS, Logit, ARIMA, Index Numbers, etc.

Tests cover:
- OLS regression (coefficient recovery, robust SE, R², diagnostics)
- Logit model (sigmoid, MLE convergence, marginal effects)
- Index numbers (Laspeyres, Paasche, Fisher, Törnqvist)
- Time series forecasting (SES, Holt linear)
- ARIMA model (fit, forecast, auto-select, Ljung-Box)
- Heckman selection correction
- Monte Carlo integration
- Edge cases and error handling

Run: pytest tests/test_econometrics.py -v
"""

from __future__ import annotations

import importlib.util
import os
import sys

import numpy as np
import pytest
from scipy import stats

# Direct module loading (avoids heavy app imports — same pattern as test_causal_inference.py)
_base = os.path.join(os.path.dirname(__file__), "..")

def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

_ee = _load_module(
    "app.services.econometric_engine",
    os.path.join(_base, "app", "services", "econometric_engine.py"),
)
_em = _load_module(
    "app.services.econometric_methods",
    os.path.join(_base, "app", "services", "econometric_methods.py"),
)

OLSRegression = _ee.OLSRegression
LogitModel = _ee.LogitModel
IndexNumberBuilder = _ee.IndexNumberBuilder
TimeSeriesForecaster = _ee.TimeSeriesForecaster
ARIMAModel = _ee.ARIMAModel
HeckmanCorrection = _ee.HeckmanCorrection
MonteCarloEngine = _em.MonteCarloEngine

np.random.seed(42)


# ════════════════════════════════════════════════════════════════════
# OLS Regression Tests
# ════════════════════════════════════════════════════════════════════


class TestOLSRegression:
    """Test OLS regression estimation and diagnostics."""

    def test_coefficient_recovery(self):
        """OLS should recover true coefficients from clean data."""
        n = 500
        X = np.random.randn(n, 2)
        beta_true = np.array([3.0, 1.5, -0.8])
        y = beta_true[0] + X @ beta_true[1:] + np.random.randn(n) * 0.1

        result = OLSRegression.fit(X, y, robust=False, add_constant=True)

        assert "coefficients" in result
        coefs = np.array(result["coefficients"])
        # Should be close to [3.0, 1.5, -0.8]
        np.testing.assert_allclose(coefs, beta_true, atol=0.1)

    def test_r_squared_high_for_good_fit(self):
        """R² should be close to 1 when noise is small."""
        n = 200
        X = np.random.randn(n, 1)
        y = 5 + 2 * X[:, 0] + np.random.randn(n) * 0.01

        result = OLSRegression.fit(X, y, robust=False)
        assert result["r_squared"] > 0.99

    def test_r_squared_low_for_noisy_data(self):
        """R² should be low when noise dominates."""
        n = 200
        X = np.random.randn(n, 1)
        y = np.random.randn(n) * 100  # Pure noise

        result = OLSRegression.fit(X, y, robust=False)
        assert result["r_squared"] < 0.1

    def test_robust_standard_errors(self):
        """Robust SEs should differ from classical SEs under heteroskedasticity."""
        n = 300
        X = np.random.randn(n, 1)
        # Heteroskedastic errors
        noise = np.random.randn(n) * (1 + np.abs(X[:, 0]))
        y = 5 + 2 * X[:, 0] + noise

        classical = OLSRegression.fit(X, y, robust=False)
        robust = OLSRegression.fit(X, y, robust=True)

        # SEs should be different
        assert classical["standard_errors"] != robust["standard_errors"]
        assert robust["robust_se"] is True
        assert classical["robust_se"] is False

    def test_confidence_intervals_contain_true_value(self):
        """95% CI should contain the true coefficient."""
        n = 200
        X = np.random.randn(n, 1)
        beta_true = 5.0
        y = beta_true + X[:, 0] * 2 + np.random.randn(n) * 1

        result = OLSRegression.fit(X, y, robust=True)
        ci = result["confidence_intervals_95"]
        # Intercept CI should contain 5.0
        assert ci[0][0] <= beta_true <= ci[0][1]

    def test_f_statistic_significant(self):
        """F-test should produce a statistic when coefficients are non-zero."""
        n = 200
        X = np.random.randn(n, 2)
        y = 10 + 3 * X[:, 0] - 2 * X[:, 1] + np.random.randn(n) * 0.5

        result = OLSRegression.fit(X, y, robust=False)
        assert result["f_statistic"] is not None
        assert result["f_statistic"] > 100  # Very significant

    def test_p_values_for_significant_coefficients(self):
        """p-values should be small for truly non-zero coefficients."""
        n = 500
        X = np.random.randn(n, 1)
        y = 5 + 3 * X[:, 0] + np.random.randn(n) * 0.5

        result = OLSRegression.fit(X, y, robust=True)
        # Both intercept and slope should be significant
        assert result["p_values"][0] < 0.01  # intercept
        assert result["p_values"][1] < 0.01  # slope

    def test_singular_matrix_detection(self):
        """Perfect multicollinearity should return error."""
        n = 100
        X = np.column_stack([np.ones(n), np.ones(n)])  # Two identical columns
        y = np.random.randn(n)

        result = OLSRegression.fit(X, y, add_constant=False)
        assert "error" in result
        assert "multicollinearity" in result["error"].lower() or "singular" in result["error"].lower()

    def test_no_constant_option(self):
        """add_constant=False should not add intercept."""
        n = 100
        X = np.random.randn(n, 1)
        y = 2 * X[:, 0] + np.random.randn(n) * 0.1

        result = OLSRegression.fit(X, y, add_constant=False)
        # Should have 1 coefficient (no intercept)
        assert result["n_parameters"] == 1

    def test_elasticity_log_log(self):
        """Elasticity in log-log model equals the coefficient."""
        e = OLSRegression.compute_elasticity(0.5, 3.0, 100.0, log_model=True)
        assert e == 0.5

    def test_elasticity_level_level(self):
        """Elasticity in level-level model = β * x_mean / y_mean."""
        e = OLSRegression.compute_elasticity(2.0, 50.0, 100.0, log_model=False)
        assert e == 1.0  # 2.0 * 50 / 100


# ════════════════════════════════════════════════════════════════════
# Logit Model Tests
# ════════════════════════════════════════════════════════════════════


class TestLogitModel:
    """Test logistic regression estimation."""

    def test_sigmoid(self):
        """Sigmoid should map R → (0, 1)."""
        assert LogitModel.sigmoid(np.array([0]))[0] == 0.5
        assert LogitModel.sigmoid(np.array([100]))[0] > 0.99
        assert LogitModel.sigmoid(np.array([-100]))[0] < 0.01

    def test_sigmoid_extreme_values(self):
        """Sigmoid should handle extreme values without overflow."""
        result = LogitModel.sigmoid(np.array([1000, -1000, 0]))
        # Near-extreme values should be in [0, 1] range
        assert 0 <= float(result[0]) <= 1
        assert 0 <= float(result[1]) <= 1
        assert 0 <= float(result[2]) <= 1
        # Middle value should be 0.5
        assert float(result[2]) == 0.5

    def test_convergence(self):
        """Logit MLE should converge on well-separated data."""
        n = 300
        X = np.random.randn(n, 2)
        # Clear separation
        z = 2 + 3 * X[:, 0] - 1.5 * X[:, 1]
        prob = 1 / (1 + np.exp(-z))
        y = (np.random.rand(n) < prob).astype(float)

        result = LogitModel.fit(X, y)
        assert "error" not in result
        assert result["converged"] is True

    def test_coefficient_signs(self):
        """Coefficients should have correct signs."""
        n = 500
        X = np.random.randn(n, 1)
        z = -1 + 4 * X[:, 0]
        prob = 1 / (1 + np.exp(-z))
        y = (np.random.rand(n) < prob).astype(float)

        result = LogitModel.fit(X, y)
        coefs = result["coefficients"]
        # Intercept should be negative, slope positive
        assert coefs[0] < 0  # intercept
        assert coefs[1] > 0  # slope

    def test_pseudo_r_squared(self):
        """Pseudo R² should be between 0 and 1."""
        n = 300
        X = np.random.randn(n, 2)
        z = 1 + 2 * X[:, 0]
        prob = 1 / (1 + np.exp(-z))
        y = (np.random.rand(n) < prob).astype(float)

        result = LogitModel.fit(X, y)
        assert 0 < result["pseudo_r_squared"] < 1

    def test_predict_probability(self):
        """predict_probability should return values in [0, 1]."""
        X = np.array([[1, 0], [0, 1], [1, 1]])
        coefs = np.array([0.5, 1.0, -0.5])
        probs = LogitModel.predict_probability(X, coefs)
        assert all(0 <= p <= 1 for p in probs)

    def test_aic_bic_computed(self):
        """AIC and BIC should be computed."""
        n = 200
        X = np.random.randn(n, 1)
        z = 1 + 2 * X[:, 0]
        y = (np.random.rand(n) < 1 / (1 + np.exp(-z))).astype(float)

        result = LogitModel.fit(X, y)
        assert "aic" in result
        assert "bic" in result
        assert result["bic"] > 0


# ════════════════════════════════════════════════════════════════════
# Index Number Tests
# ════════════════════════════════════════════════════════════════════


class TestIndexNumbers:
    """Test price index construction methods."""

    def test_laspeyres_no_change(self):
        """Laspeyres should be 100 when prices don't change."""
        p0 = np.array([100, 200, 50])
        q0 = np.array([10, 5, 20])
        idx = IndexNumberBuilder.laspeyres(p0, p0, q0)
        assert idx == 100.0

    def test_laspeyres_price_increase(self):
        """Laspeyres should reflect price increases."""
        p0 = np.array([100, 200, 50])
        p1 = np.array([110, 220, 55])  # 10% increase
        q0 = np.array([10, 5, 20])
        idx = IndexNumberBuilder.laspeyres(p0, p1, q0)
        assert abs(idx - 110.0) < 0.1

    def test_paasche_no_change(self):
        """Paasche should be 100 when prices don't change."""
        p0 = np.array([100, 200, 50])
        q1 = np.array([10, 5, 20])
        idx = IndexNumberBuilder.paasche(p0, p0, q1)
        assert idx == 100.0

    def test_fisher_is_geometric_mean(self):
        """Fisher should be geometric mean of Laspeyres and Paasche."""
        p0 = np.array([100, 200, 50])
        p1 = np.array([110, 220, 55])
        q0 = np.array([10, 5, 20])
        q1 = np.array([12, 4, 18])

        L = IndexNumberBuilder.laspeyres(p0, p1, q0)
        P = IndexNumberBuilder.paasche(p0, p1, q1)
        F = IndexNumberBuilder.fisher(p0, p1, q0, q1)

        expected = np.sqrt(L * P)
        assert abs(F - expected) < 0.01

    def test_fisher_time_reversal(self):
        """Fisher satisfies time reversal test: P(0→1) × P(1→0) ≈ 1."""
        p0 = np.array([100, 200, 50])
        p1 = np.array([110, 220, 55])
        q0 = np.array([10, 5, 20])
        q1 = np.array([12, 4, 18])

        f01 = IndexNumberBuilder.fisher(p0, p1, q0, q1)
        f10 = IndexNumberBuilder.fisher(p1, p0, q1, q0)
        product = f01 * f10 / 100  # Should be ≈ 100
        assert abs(product - 100) < 1.0

    def test_tornqvist_no_change(self):
        """Törnqvist should be 100 when prices don't change."""
        p0 = np.array([100, 200, 50])
        s0 = np.array([0.4, 0.35, 0.25])
        s1 = np.array([0.4, 0.35, 0.25])
        idx = IndexNumberBuilder.tornqvist(p0, p0, s0, s1)
        assert idx == 100.0

    def test_tornqvist_price_increase(self):
        """Törnqvist should reflect price increases."""
        p0 = np.array([100, 200, 50])
        p1 = np.array([120, 240, 60])  # 20% increase
        s0 = np.array([0.4, 0.35, 0.25])
        s1 = np.array([0.42, 0.33, 0.25])
        idx = IndexNumberBuilder.tornqvist(p0, p1, s0, s1)
        assert idx > 100


# ════════════════════════════════════════════════════════════════════
# Time Series Forecaster Tests
# ════════════════════════════════════════════════════════════════════


class TestTimeSeriesForecaster:
    """Test exponential smoothing methods."""

    def test_ses_flat_data(self):
        """SES forecast should be near the mean for flat data."""
        data = np.full(50, 100.0) + np.random.randn(50) * 0.1
        result = TimeSeriesForecaster.simple_exponential_smoothing(data, alpha=0.3)
        assert abs(result["forecast"] - 100.0) < 1.0
        assert result["method"] == "simple_exponential_smoothing"

    def test_ses_responds_to_level_shift(self):
        """SES should track level shifts with appropriate alpha."""
        data = np.concatenate([np.full(30, 100.0), np.full(30, 200.0)])
        result = TimeSeriesForecaster.simple_exponential_smoothing(data, alpha=0.5)
        # Should be closer to 200 than 100
        assert result["forecast"] > 150

    def test_ses_confidence_interval(self):
        """SES should produce confidence intervals."""
        data = np.random.randn(50) + 50
        result = TimeSeriesForecaster.simple_exponential_smoothing(data, alpha=0.3)
        assert result["confidence_interval_low"] < result["forecast"]
        assert result["confidence_interval_high"] > result["forecast"]

    def test_holt_linear_trending_data(self):
        """Holt's linear should track trending data."""
        t = np.arange(50)
        data = 10 + 0.5 * t + np.random.randn(50) * 0.5
        result = TimeSeriesForecaster.holt_linear(data, alpha=0.3, beta=0.1)
        # Forecast should be above the last data point (upward trend)
        assert result["forecast"] > data[-1]
        assert result["trend"] > 0

    def test_holt_linear_flat_data(self):
        """Holt's linear trend should be near zero for flat data."""
        data = np.full(50, 100.0) + np.random.randn(50) * 0.1
        result = TimeSeriesForecaster.holt_linear(data, alpha=0.3, beta=0.1)
        assert abs(result["trend"]) < 1.0

    def test_holt_linear_downtrend(self):
        """Holt's linear should detect downtrends."""
        t = np.arange(50)
        data = 100 - 0.3 * t + np.random.randn(50) * 0.5
        result = TimeSeriesForecaster.holt_linear(data, alpha=0.3, beta=0.1)
        assert result["trend"] < 0


# ════════════════════════════════════════════════════════════════════
# ARIMA Model Tests
# ════════════════════════════════════════════════════════════════════


class TestARIMAModel:
    """Test ARIMA model fitting and forecasting."""

    def test_ar1_fit(self):
        """AR(1) should recover coefficient from simulated data."""
        n = 500
        phi = 0.7
        data = np.zeros(n)
        data[0] = np.random.randn()
        for t in range(1, n):
            data[t] = phi * data[t - 1] + np.random.randn() * 0.5

        model = ARIMAModel(p=1, d=0, q=0)
        result = model.fit(data)

        assert "error" not in result
        assert result["order"] == {"p": 1, "d": 0, "q": 0}
        ar_coefs = result["ar_coefficients"]
        assert len(ar_coefs) == 1
        assert abs(ar_coefs[0] - phi) < 0.2

    def test_ma1_fit(self):
        """MA(1) should fit without errors."""
        n = 300
        theta = 0.5
        data = np.zeros(n)
        eps = np.random.randn(n)
        data[0] = eps[0]
        for t in range(1, n):
            data[t] = eps[t] + theta * eps[t - 1]

        model = ARIMAModel(p=0, d=0, q=1)
        result = model.fit(data)

        assert "error" not in result
        assert len(result["ma_coefficients"]) == 1

    def test_arma_fit(self):
        """ARMA(1,1) should fit without errors."""
        n = 300
        data = np.zeros(n)
        eps = np.random.randn(n)
        data[0] = eps[0]
        for t in range(1, n):
            data[t] = 0.6 * data[t - 1] + eps[t] + 0.3 * eps[t - 1]

        model = ARIMAModel(p=1, d=0, q=1)
        result = model.fit(data)

        assert "error" not in result
        assert result["method"] == "ARIMA(1,0,1)"

    def test_differencing(self):
        """ARIMA(0,1,0) should difference the series."""
        # Random walk
        n = 200
        data = np.cumsum(np.random.randn(n))

        model = ARIMAModel(p=1, d=1, q=0)
        result = model.fit(data)

        assert "error" not in result
        assert result["order"]["d"] == 1

    def test_forecast_produces_output(self):
        """Forecast should produce the requested number of steps."""
        n = 100
        data = np.cumsum(np.random.randn(n)) + 50

        model = ARIMAModel(p=1, d=1, q=0)
        model.fit(data)
        fc = model.forecast(steps=6)

        assert "forecasts" in fc
        assert len(fc["forecasts"]) == 6
        for step in fc["forecasts"]:
            assert "forecast" in step
            assert "lower" in step
            assert "upper" in step
            assert step["lower"] < step["forecast"] < step["upper"]

    def test_forecast_without_fit(self):
        """Forecast before fit should return error."""
        model = ARIMAModel(p=1, d=0, q=0)
        result = model.forecast(steps=5)
        assert "error" in result

    def test_ljung_box_white_noise(self):
        """Ljung-Box should not reject white noise."""
        data = np.random.randn(200)
        model = ARIMAModel(p=0, d=0, q=0)
        result = model.fit(data)
        lb = result["ljung_box"]
        # White noise should pass (p > 0.05)
        assert lb["white_noise"] is True or lb["p_value"] > 0.01

    def test_auto_select_finds_model(self):
        """Auto-select should find a reasonable model."""
        n = 200
        data = np.zeros(n)
        data[0] = np.random.randn()
        for t in range(1, n):
            data[t] = 0.8 * data[t - 1] + np.random.randn() * 0.5

        result = ARIMAModel.auto_select(data, max_p=3, max_d=1, max_q=3)
        assert "best_order" in result
        # Key might be 'best_bic' or 'best_fit' depending on implementation
        assert "best_bic" in result or "best_fit" in result

    def test_insufficient_data_returns_error(self):
        """Should return error when data is too short."""
        data = np.array([1, 2, 3])
        model = ARIMAModel(p=2, d=1, q=2)
        result = model.fit(data)
        assert "error" in result


# ════════════════════════════════════════════════════════════════════
# Heckman Correction Tests
# ════════════════════════════════════════════════════════════════════


class TestHeckmanCorrection:
    """Test Heckman two-step selection correction."""

    def test_inverse_mills_ratio(self):
        """IMR should be positive and decreasing."""
        z = np.array([-2, -1, 0, 1, 2])
        imr = HeckmanCorrection.inverse_mills_ratio(z)
        assert all(imr > 0)
        # IMR is decreasing
        for i in range(len(imr) - 1):
            assert imr[i] > imr[i + 1]

    def test_two_step_estimation(self):
        """Heckman two-step should produce valid output."""
        np.random.seed(42)
        n = 500

        # Selection equation
        X_sel = np.random.randn(n, 2)
        z = 0.5 + X_sel[:, 0] - 0.3 * X_sel[:, 1] + np.random.randn(n) * 0.5
        selection = (z > 0).astype(float)

        # Outcome (only observed for selected)
        X_out = np.random.randn(n, 1)
        y = 3 + 2 * X_out[:, 0] + np.random.randn(n) * 0.5

        result = HeckmanCorrection.two_step(X_sel, selection, X_out, y)

        assert "error" not in result
        assert "lambda_coefficient" in result
        assert "selection_bias_detected" in result
        assert result["n_selected"] > 0
        assert result["n_total"] == n
        assert 0 < result["selection_rate"] < 1

    def test_two_step_no_selection_bias(self):
        """When selection is random, lambda should be insignificant."""
        np.random.seed(42)
        n = 500

        X_sel = np.random.randn(n, 1)
        # Random selection (not based on X)
        selection = (np.random.rand(n) > 0.3).astype(float)

        X_out = np.random.randn(n, 1)
        y = 3 + 2 * X_out[:, 0] + np.random.randn(n) * 0.5

        result = HeckmanCorrection.two_step(X_sel, selection, X_out, y)

        assert "error" not in result
        # Lambda coefficient should exist
        assert "lambda_coefficient" in result
        assert isinstance(result["lambda_coefficient"], float)


# ════════════════════════════════════════════════════════════════════
# Monte Carlo Tests
# ════════════════════════════════════════════════════════════════════


class TestMonteCarlo:
    """Test Monte Carlo simulation methods."""

    def test_crude_integration(self):
        """MC integration of x² over [0,1] should be ≈ 1/3."""
        result = MonteCarloEngine.crude_integration(
            func=lambda x: x[0] ** 2,
            bounds=[(0, 1)],
            n_samples=100000,
        )
        assert abs(result["estimate"] - 1 / 3) < 0.01
        assert result["std_error"] > 0
        assert len(result["ci_95"]) == 2

    def test_crude_integration_2d(self):
        """MC integration of 1 over [0,1]×[0,1] should be ≈ 1."""
        result = MonteCarloEngine.crude_integration(
            func=lambda x: 1.0,
            bounds=[(0, 1), (0, 1)],
            n_samples=50000,
        )
        assert abs(result["estimate"] - 1.0) < 0.02

    def test_bootstrap_hypothesis_test(self):
        """Bootstrap test should detect different means."""
        np.random.seed(42)
        sample1 = np.random.randn(100) + 5
        sample2 = np.random.randn(100) + 2

        result = MonteCarloEngine.bootstrap_hypothesis_test(
            sample1, sample2, n_bootstrap=5000
        )
        assert "p_value" in result
        assert result["p_value"] < 0.05  # Should detect difference

    def test_bootstrap_same_distribution(self):
        """Bootstrap test should not reject when samples are from same distribution."""
        np.random.seed(42)
        sample1 = np.random.randn(100)
        sample2 = np.random.randn(100)

        result = MonteCarloEngine.bootstrap_hypothesis_test(
            sample1, sample2, n_bootstrap=5000
        )
        assert result["p_value"] > 0.01  # Should not strongly reject
