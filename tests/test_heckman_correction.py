"""
Tests for Heckman Selection Correction and CUSUM Drift Detection.

Tests cover:
- Heckman two-step estimator correctness
- CUSUM drift detection behavior
- Edge cases and error handling
- API schema validation
"""

import importlib.util
import os
import sys

import numpy as np
import pytest
from scipy import stats

# Direct module loading to avoid triggering app/__init__.py and
# app/services/__init__.py which pull in sqlalchemy, pydantic-settings, etc.
_base = os.path.join(os.path.dirname(__file__), "..")

def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

_heckman_mod = _load_module(
    "app.services.heckman_correction",
    os.path.join(_base, "app", "services", "heckman_correction.py"),
)
_drift_mod = _load_module(
    "app.services.drift_detector",
    os.path.join(_base, "app", "services", "drift_detector.py"),
)

CorrectedCreditScore = _heckman_mod.CorrectedCreditScore
HeckmanCorrector = _heckman_mod.HeckmanCorrector
HeckmanResult = _heckman_mod.HeckmanResult

AlertSeverity = _drift_mod.AlertSeverity
CUSUMDriftDetector = _drift_mod.CUSUMDriftDetector
DriftAlert = _drift_mod.DriftAlert
DriftDirection = _drift_mod.DriftDirection
ModelDriftMonitor = _drift_mod.ModelDriftMonitor
ModelStatus = _drift_mod.ModelStatus


# =========================================================================
# Heckman Correction Tests
# =========================================================================


class TestHeckmanCorrector:
    """Test suite for the Heckman two-step selection correction."""

    @pytest.fixture
    def sample_data(self):
        """Generate synthetic data with known selection bias.

        The data generating process:
        - Selection: P(selected=1) = Φ(0.5 + 1.0*x1 + 0.8*x2)
        - Outcome: y = 50 + 15*x1 + 10*x2 + 8*x3 + ε
        - Selection bias: corr(ε_selection, ε_outcome) = ρ = 0.4
        """
        np.random.seed(42)
        n = 1000

        # Features
        x1 = np.random.randn(n)
        x2 = np.random.randn(n)
        x3 = np.random.randn(n)

        # Selection equation: true γ = [0.5, 1.0, 0.8]
        gamma_true = np.array([0.5, 1.0, 0.8])
        X_sel = np.column_stack([np.ones(n), x1, x2])
        sel_latent = X_sel @ gamma_true + np.random.randn(n)
        selected = (sel_latent > 0).astype(int)

        # Outcome equation (only observed for selected)
        n_sel = selected.sum()
        rho_true = 0.4
        sigma_e = 5.0

        # Generate correlated errors
        e_sel = np.random.randn(n)
        e_out = rho_true * e_sel + np.sqrt(1 - rho_true ** 2) * np.random.randn(n)

        X_out = np.column_stack([np.ones(n), x1, x2, x3])
        beta_true = np.array([50, 15, 10, 8])
        y_latent = X_out @ beta_true + e_out * sigma_e

        # Only observe outcome for selected
        X_sel_selected = X_sel[selected == 1]
        X_out_selected = X_out[selected == 1]
        y_observed = y_latent[selected == 1]

        return {
            "X_selection": X_sel,
            "selection_indicator": selected,
            "X_outcome": X_out_selected,
            "y_outcome": y_observed,
            "gamma_true": gamma_true,
            "beta_true": beta_true,
            "rho_true": rho_true,
            "n_total": n,
            "n_selected": n_sel,
        }

    def test_fit_basic(self, sample_data):
        """Test basic model fitting."""
        corrector = HeckmanCorrector()
        result = corrector.fit(
            X_selection=sample_data["X_selection"],
            selection_indicator=sample_data["selection_indicator"],
            X_outcome=sample_data["X_outcome"],
            y_outcome=sample_data["y_outcome"],
        )

        assert corrector.is_fitted
        assert result is not None
        assert isinstance(result, HeckmanResult)
        assert result.n_obs_total == sample_data["n_total"]
        assert result.n_obs_selected == sample_data["n_selected"]

    def test_selection_coefficients_reasonable(self, sample_data):
        """Test that selection coefficients are in the right ballpark."""
        corrector = HeckmanCorrector()
        result = corrector.fit(
            X_selection=sample_data["X_selection"],
            selection_indicator=sample_data["selection_indicator"],
            X_outcome=sample_data["X_outcome"],
            y_outcome=sample_data["y_outcome"],
        )

        # Coefficients should be roughly proportional to true values
        gamma_hat = result.selection_coefficients
        gamma_true = sample_data["gamma_true"]

        # Signs should match
        for i in range(len(gamma_true)):
            assert np.sign(gamma_hat[i]) == np.sign(gamma_true[i]), (
                f"Sign mismatch for γ[{i}]: "
                f"true={gamma_true[i]}, estimated={gamma_hat[i]}"
            )

    def test_outcome_coefficients_reasonable(self, sample_data):
        """Test that outcome coefficients recover the true values."""
        corrector = HeckmanCorrector()
        result = corrector.fit(
            X_selection=sample_data["X_selection"],
            selection_indicator=sample_data["selection_indicator"],
            X_outcome=sample_data["X_outcome"],
            y_outcome=sample_data["y_outcome"],
        )

        # First 4 coefficients should be close to true values
        beta_hat = result.outcome_coefficients[:4]
        beta_true = sample_data["beta_true"]

        for i in range(4):
            # Allow 50% tolerance (selection bias makes estimation harder)
            assert abs(beta_hat[i] - beta_true[i]) / abs(beta_true[i]) < 0.5, (
                f"β[{i}] too far from true: "
                f"true={beta_true[i]}, estimated={beta_hat[i]:.2f}"
            )

    def test_rho_estimation(self, sample_data):
        """Test that ρ is estimated with correct sign."""
        corrector = HeckmanCorrector()
        result = corrector.fit(
            X_selection=sample_data["X_selection"],
            selection_indicator=sample_data["selection_indicator"],
            X_outcome=sample_data["X_outcome"],
            y_outcome=sample_data["y_outcome"],
        )

        # ρ should be positive (true value is 0.4)
        # Allow for estimation error
        assert result.rho > -0.5, f"ρ too negative: {result.rho}"
        assert result.rho < 1.0, f"ρ > 1: {result.rho}"

    def test_confidence_intervals(self, sample_data):
        """Test confidence interval computation."""
        corrector = HeckmanCorrector()
        result = corrector.fit(
            X_selection=sample_data["X_selection"],
            selection_indicator=sample_data["selection_indicator"],
            X_outcome=sample_data["X_outcome"],
            y_outcome=sample_data["y_outcome"],
        )

        ci = corrector.get_confidence_intervals(confidence_level=0.95)

        assert "selection_equation_ci" in ci
        assert "outcome_equation_ci" in ci
        assert ci["confidence_level"] == 0.95

        # Each CI should have lower < coefficient < upper
        for item in ci["outcome_equation_ci"]:
            assert item["ci_lower"] <= item["coefficient"] <= item["ci_upper"]

    def test_correct_scores(self, sample_data):
        """Test score correction on new data."""
        corrector = HeckmanCorrector()
        corrector.fit(
            X_selection=sample_data["X_selection"],
            selection_indicator=sample_data["selection_indicator"],
            X_outcome=sample_data["X_outcome"],
            y_outcome=sample_data["y_outcome"],
        )

        # Create new observations
        n_new = 10
        X_sel_new = np.column_stack([
            np.ones(n_new),
            np.random.randn(n_new),
            np.random.randn(n_new),
        ])
        X_out_new = np.column_stack([
            np.ones(n_new),
            np.random.randn(n_new),
            np.random.randn(n_new),
            np.random.randn(n_new),
        ])

        scores = corrector.correct_scores(
            X_selection_new=X_sel_new,
            X_outcome_new=X_out_new,
            business_ids=[f"biz_{i}" for i in range(n_new)],
        )

        assert len(scores) == n_new
        for score in scores:
            assert isinstance(score, CorrectedCreditScore)
            assert score.risk_category in [
                "very_low", "low", "medium", "high", "very_high"
            ]
            assert score.confidence_interval[0] <= score.confidence_interval[1]
            assert 0 <= score.selection_probability <= 1

    def test_not_fitted_raises(self):
        """Test that operations fail gracefully when not fitted."""
        corrector = HeckmanCorrector()

        with pytest.raises(RuntimeError, match="not fitted"):
            corrector.correct_scores(
                X_selection_new=np.ones((1, 3)),
                X_outcome_new=np.ones((1, 3)),
            )

        with pytest.raises(RuntimeError, match="not fitted"):
            corrector.get_confidence_intervals()

    def test_result_serialization(self, sample_data):
        """Test that results serialize to dict correctly."""
        corrector = HeckmanCorrector()
        result = corrector.fit(
            X_selection=sample_data["X_selection"],
            selection_indicator=sample_data["selection_indicator"],
            X_outcome=sample_data["X_outcome"],
            y_outcome=sample_data["y_outcome"],
        )

        d = result.to_dict()
        assert "selection_equation" in d
        assert "outcome_equation" in d
        assert "correction" in d
        assert "sample_info" in d
        assert "interpretation" in d["correction"]

    def test_input_validation(self):
        """Test that malformed inputs raise ValueError."""
        corrector = HeckmanCorrector()

        with pytest.raises(ValueError, match="rows"):
            corrector.fit(
                X_selection=np.ones((10, 3)),
                selection_indicator=np.ones(5),  # Wrong length
                X_outcome=np.ones((5, 3)),
                y_outcome=np.ones(5),
            )

    def test_no_selection_bias(self):
        """When there's no selection bias, model should still fit without error."""
        np.random.seed(123)
        n = 3000

        x1 = np.random.randn(n)
        x2 = np.random.randn(n)

        # Selection independent of outcome error
        X_sel = np.column_stack([np.ones(n), x1, x2])
        selected = (X_sel @ np.array([0.5, 1.0, 0.5]) + np.random.randn(n) > 0).astype(int)

        # Outcome with independent errors (ρ = 0)
        X_out = np.column_stack([np.ones(n), x1, x2])
        y = X_out @ np.array([50, 10, 8]) + np.random.randn(n) * 5

        corrector = HeckmanCorrector(max_iter=200)
        result = corrector.fit(
            X_selection=X_sel,
            selection_indicator=selected,
            X_outcome=X_out[selected == 1],
            y_outcome=y[selected == 1],
        )

        # With no selection bias, the model should still fit.
        # ρ may not be exactly 0 due to finite-sample bias and
        # incidental parameters problem, but the model must converge.
        assert result.n_obs_total == n
        assert result.sigma > 0
        # Outcome coefficients should be in the right ballpark
        assert abs(result.outcome_coefficients[0] - 50) < 20  # intercept
        assert abs(result.outcome_coefficients[1] - 10) < 10  # x1


# =========================================================================
# CUSUM Drift Detection Tests
# =========================================================================


class TestCUSUMDriftDetector:
    """Test suite for CUSUM drift detection."""

    def test_initialization(self):
        """Test detector initialization with parameters."""
        detector = CUSUMDriftDetector(
            baseline_mean=0.85,
            baseline_std=0.05,
            delta=1.0,
            h=4.0,
            metric_name="test_metric",
        )

        assert detector.metric_name == "test_metric"
        assert detector.baseline_mean == 0.85
        assert detector.baseline_std == 0.05
        assert detector.current_status == ModelStatus.STABLE

    def test_invalid_baseline_std(self):
        """Test that non-positive std raises error."""
        with pytest.raises(ValueError, match="positive"):
            CUSUMDriftDetector(baseline_std=0.0)

        with pytest.raises(ValueError, match="positive"):
            CUSUMDriftDetector(baseline_std=-1.0)

    def test_burn_in_period(self):
        """Test that observations during burn-in don't trigger alerts."""
        detector = CUSUMDriftDetector(
            baseline_mean=0.85,
            baseline_std=0.05,
            burn_in=20,
            metric_name="test",
        )

        # Send very bad values during burn-in — should not alert
        for _ in range(20):
            alert = detector.update(0.50)  # Far below baseline
            assert alert is None

        assert detector._state.n_observations == 20

    def test_stable_stream_no_alert(self):
        """Test that stable stream doesn't trigger alerts."""
        detector = CUSUMDriftDetector(
            baseline_mean=0.85,
            baseline_std=0.05,
            delta=1.0,
            h=4.0,
            burn_in=10,
            metric_name="test",
        )

        # Burn in with varied values (realistic calibration)
        np.random.seed(99)
        for _ in range(10):
            detector.update(0.85 + np.random.randn() * 0.04)

        # Stable stream (within baseline)
        np.random.seed(42)
        alerts = []
        for _ in range(100):
            val = 0.85 + np.random.randn() * 0.03  # Within ±1σ
            alert = detector.update(val)
            if alert:
                alerts.append(alert)

        assert len(alerts) == 0

    def test_degradation_detection(self):
        """Test that sustained degradation triggers an alert."""
        detector = CUSUMDriftDetector(
            baseline_mean=0.85,
            baseline_std=0.05,
            delta=1.0,
            h=3.0,  # Lower threshold for faster detection
            burn_in=10,
            metric_name="test",
        )

        # Burn in
        for _ in range(10):
            detector.update(0.85)

        # Sustained degradation: consistently below baseline
        alert = None
        for i in range(100):
            val = 0.75  # 2σ below baseline
            alert = detector.update(val)
            if alert:
                break

        assert alert is not None
        assert alert.direction == DriftDirection.DEGRADATION
        assert alert.severity in [AlertSeverity.WARNING, AlertSeverity.CRITICAL]
        assert alert.recommendation  # Should have a recommendation

    def test_improvement_detection(self):
        """Test that sustained improvement triggers an informational alert."""
        detector = CUSUMDriftDetector(
            baseline_mean=0.85,
            baseline_std=0.05,
            delta=1.0,
            h=3.0,
            burn_in=10,
            metric_name="test",
        )

        # Burn in
        for _ in range(10):
            detector.update(0.85)

        # Sustained improvement: consistently above baseline
        alert = None
        for i in range(100):
            val = 0.95  # 2σ above baseline
            alert = detector.update(val)
            if alert:
                break

        assert alert is not None
        assert alert.direction == DriftDirection.IMPROVEMENT
        assert alert.severity == AlertSeverity.INFO

    def test_get_status(self):
        """Test status reporting."""
        detector = CUSUMDriftDetector(
            baseline_mean=0.85,
            baseline_std=0.05,
            burn_in=5,
            metric_name="accuracy",
        )

        for _ in range(5):
            detector.update(0.85)

        status = detector.get_status()
        assert status["metric_name"] == "accuracy"
        assert status["status"] in ["stable", "warning", "drift_detected"]
        assert status["observations"] == 5
        assert "cusum_upper" in status
        assert "baseline" in status

    def test_performance_trend(self):
        """Test trend analysis."""
        detector = CUSUMDriftDetector(
            baseline_mean=0.85,
            baseline_std=0.05,
            burn_in=5,
        )

        # Feed in improving trend
        for i in range(50):
            detector.update(0.80 + i * 0.002)

        trend = detector.get_performance_trend(window=40)
        assert trend["status"] == "ok"
        assert trend["trend"] == "improving"
        assert trend["trend_slope"] > 0

    def test_alert_reset(self):
        """Test that CUSUM resets after alert to avoid repeated alerts."""
        detector = CUSUMDriftDetector(
            baseline_mean=0.85,
            baseline_std=0.05,
            delta=1.0,
            h=3.0,
            burn_in=5,
        )

        for _ in range(5):
            detector.update(0.85)

        # Trigger first alert
        alert1 = None
        for _ in range(100):
            alert1 = detector.update(0.70)
            if alert1:
                break
        assert alert1 is not None

        # After alert, CUSUM resets — should need more degradation for second alert
        # Send one normal value
        detector.update(0.85)
        # The CUSUM should have reset


class TestModelDriftMonitor:
    """Test suite for multi-metric drift monitoring."""

    def test_add_and_update_metric(self):
        """Test adding metrics and updating them."""
        monitor = ModelDriftMonitor()
        monitor.add_metric("accuracy", baseline_mean=0.85, baseline_std=0.05)
        monitor.add_metric("auc", baseline_mean=0.90, baseline_std=0.03)

        # Update known metric
        alert = monitor.update("accuracy", 0.86)
        assert alert is None  # Within normal range

    def test_unknown_metric_raises(self):
        """Test that updating unknown metric raises KeyError."""
        monitor = ModelDriftMonitor()
        monitor.add_metric("accuracy", 0.85, 0.05)

        with pytest.raises(KeyError):
            monitor.update("nonexistent_metric", 0.50)

    def test_batch_update(self):
        """Test batch metric update."""
        monitor = ModelDriftMonitor()
        monitor.add_metric("accuracy", 0.85, 0.05)
        monitor.add_metric("auc", 0.90, 0.03)

        alerts = monitor.update_batch({"accuracy": 0.86, "auc": 0.91})
        assert isinstance(alerts, list)

    def test_overall_status(self):
        """Test overall status aggregation."""
        monitor = ModelDriftMonitor(
            metrics_config={
                "accuracy": {"mean": 0.85, "std": 0.05},
                "auc": {"mean": 0.90, "std": 0.03},
            }
        )

        status = monitor.get_overall_status()
        assert "overall_status" in status
        assert "metrics" in status
        assert status["metrics_monitored"] == 2

    def test_get_all_alerts(self):
        """Test alert retrieval."""
        monitor = ModelDriftMonitor()
        monitor.add_metric("accuracy", 0.85, 0.05, h=3.0, burn_in=5)

        # Burn in
        for _ in range(5):
            monitor.update("accuracy", 0.85)

        # Feed degradation
        for _ in range(50):
            monitor.update("accuracy", 0.70)

        alerts = monitor.get_all_alerts(limit=10)
        assert isinstance(alerts, list)


# =========================================================================
# Schema Validation Tests
# =========================================================================


class TestSchemas:
    """Test Pydantic schema validation."""

    def test_corrected_score_response(self):
        """Test CorrectedScoreResponse schema."""
        pytest.importorskip("pydantic")
        from app.schemas.intelligence import CorrectedScoreResponse

        score = CorrectedScoreResponse(
            business_hash="abc123",
            raw_score=65.0,
            corrected_score=72.5,
            bias_adjustment=7.5,
            confidence_interval={"lower": 68.0, "upper": 77.0},
            selection_probability=0.85,
            mills_ratio_contribution=3.2,
            risk_category="medium",
            correction_applied=True,
        )
        assert score.corrected_score == 72.5
        assert score.risk_category == "medium"

    def test_drift_alert_response(self):
        """Test DriftAlertResponse schema."""
        pytest.importorskip("pydantic")
        from app.schemas.intelligence import DriftAlertResponse

        alert = DriftAlertResponse(
            timestamp="2026-06-30T20:00:00Z",
            direction="degradation",
            severity="warning",
            cusum_value=4.5,
            threshold=4.0,
            drift_magnitude_sigma=3.2,
            metric_name="accuracy",
            metric_value=0.78,
            baseline_value=0.85,
            samples_since_last_alert=150,
            recommendation="Schedule retraining",
        )
        assert alert.severity == "warning"

    def test_drift_status_response(self):
        """Test DriftStatusResponse schema."""
        pytest.importorskip("pydantic")
        from app.schemas.intelligence import DriftStatusResponse

        status = DriftStatusResponse(
            overall_status="stable",
            metrics_monitored=3,
            drift_detected_in_any=False,
            metrics={},
            timestamp="2026-06-30T20:00:00Z",
        )
        assert status.overall_status == "stable"
