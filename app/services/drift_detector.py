"""
CUSUM Drift Detection for Model Monitoring — Msaidizi / Biashara AI

Implements Cumulative Sum (CUSUM) control charts for detecting concept drift
in credit scoring and other ML models. When model predictions degrade over
time (concept drift), CUSUM detects the shift before it impacts business
outcomes, triggering retraining alerts.

This implementation provides:
- Online CUSUM monitoring (updates incrementally, no batch re-scan)
- Two-sided detection (both improvement and degradation)
- Configurable sensitivity (δ) and false-alarm rate (ARL₀)
- Alert generation with severity levels
- Model performance tracking history

References:
    - Page, E.S. (1954). Continuous inspection schemes. Biometrika, 41(1/2), 100-115.
    - Hawkins, D.M. & Olwell, D.H. (1998). Cumulative Sum Charts and
      Charting for Quality Improvement. Springer.
    - Gama, J. et al. (2014). A survey on concept drift adaptation. ACM
      Computing Surveys, 46(4), 1-37.

Typical usage:
    detector = CUSUMDriftDetector(baseline_mean=0.85, baseline_std=0.05)
    for prediction, actual in stream:
        alert = detector.update(prediction, actual)
        if alert:
            retrain_model()
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Deque, Dict, List, Optional, Tuple

import numpy as np
import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Constants & Enums
# ---------------------------------------------------------------------------

class DriftDirection(str, Enum):
    """Direction of detected drift."""
    DEGRADATION = "degradation"  # Performance getting worse
    IMPROVEMENT = "improvement"  # Performance getting better
    NONE = "none"


class AlertSeverity(str, Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class ModelStatus(str, Enum):
    """Current model monitoring status."""
    STABLE = "stable"
    WARNING = "warning"
    DRIFT_DETECTED = "drift_detected"
    RETRAINING_REQUIRED = "retraining_required"


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class DriftAlert:
    """An alert generated when drift is detected.

    Attributes:
        timestamp: When the alert was generated
        direction: Direction of drift (degradation/improvement)
        severity: Alert severity level
        cusum_value: Current CUSUM statistic at detection
        threshold: The threshold that was breached
        drift_magnitude: Estimated magnitude of the drift (in σ units)
        metric_name: Which metric triggered the alert
        metric_value: Current value of the metric
        baseline_value: Expected baseline value
        samples_since_last_alert: How many observations since last alert
        recommendation: Recommended action
    """
    timestamp: datetime
    direction: DriftDirection
    severity: AlertSeverity
    cusum_value: float
    threshold: float
    drift_magnitude: float
    metric_name: str
    metric_value: float
    baseline_value: float
    samples_since_last_alert: int
    recommendation: str

    def to_dict(self) -> Dict[str, Any]:
        """Serialize alert to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "direction": self.direction.value,
            "severity": self.severity.value,
            "cusum_value": round(self.cusum_value, 6),
            "threshold": round(self.threshold, 6),
            "drift_magnitude_sigma": round(self.drift_magnitude, 4),
            "metric_name": self.metric_name,
            "metric_value": round(self.metric_value, 6),
            "baseline_value": round(self.baseline_value, 6),
            "samples_since_last_alert": self.samples_since_last_alert,
            "recommendation": self.recommendation,
        }


@dataclass
class CUSUMState:
    """Internal state of a single CUSUM chart.

    Tracks cumulative sums for both upper (degradation) and
    lower (improvement) sides.
    """
    s_upper: float = 0.0  # CUSUM for detecting upward shifts
    s_lower: float = 0.0  # CUSUM for detecting downward shifts
    n_observations: int = 0
    n_alerts: int = 0
    last_alert_index: int = -1
    running_mean: float = 0.0
    running_m2: float = 0.0  # For Welford's online variance


@dataclass
class ModelPerformanceSnapshot:
    """Point-in-time snapshot of model performance.

    Attributes:
        timestamp: When the snapshot was taken
        metric_name: Name of the tracked metric
        metric_value: Current metric value
        cusum_upper: Current upper CUSUM value
        cusum_lower: Current lower CUSUM value
        baseline_mean: Current baseline mean
        baseline_std: Current baseline standard deviation
        z_score: Standardized metric value
        status: Model status at this point
    """
    timestamp: datetime
    metric_name: str
    metric_value: float
    cusum_upper: float
    cusum_lower: float
    baseline_mean: float
    baseline_std: float
    z_score: float
    status: ModelStatus


# ---------------------------------------------------------------------------
# CUSUM Drift Detector
# ---------------------------------------------------------------------------

class CUSUMDriftDetector:
    """CUSUM-based drift detector for model performance monitoring.

    Monitors one or more performance metrics using CUSUM control charts.
    Detects both gradual degradation (the primary concern) and sudden
    improvements in model performance.

    The CUSUM statistic accumulates deviations from the expected baseline:
        S_upper(t) = max(0, S_upper(t-1) + (x_t - μ₀)/σ₀ - k)
        S_lower(t) = min(0, S_lower(t-1) + (x_t - μ₀)/σ₀ + k)

    Where:
        μ₀ = baseline mean performance
        σ₀ = baseline standard deviation
        k = allowance (slack parameter, typically δ/2)
        δ = detectable shift size (in σ units)

    An alert fires when |S| > h (the decision threshold).

    Args:
        baseline_mean: Expected metric value under no drift
        baseline_std: Expected metric variability under no drift
        delta: Minimum shift to detect, in standard deviation units (default: 1.0)
        h: Decision threshold in σ units (default: 4.0, gives ARL₀ ≈ 167)
        burn_in: Number of initial observations to calibrate (default: 30)
        metric_name: Name of the metric being monitored
        adaptive_baseline: Whether to update baseline using running stats
        window_size: Size of the sliding window for adaptive baseline
    """

    def __init__(
        self,
        baseline_mean: float = 0.85,
        baseline_std: float = 0.05,
        delta: float = 1.0,
        h: float = 4.0,
        burn_in: int = 30,
        metric_name: str = "accuracy",
        adaptive_baseline: bool = False,
        window_size: int = 200,
    ):
        if baseline_std <= 0:
            raise ValueError("baseline_std must be positive")

        self.baseline_mean = baseline_mean
        self.baseline_std = baseline_std
        self.delta = delta
        self.h = h
        self.burn_in = burn_in
        self.metric_name = metric_name
        self.adaptive_baseline = adaptive_baseline
        self.window_size = window_size

        # CUSUM allowance (slack parameter)
        self.k = delta / 2.0

        # Decision threshold in standardized units
        self.threshold = h

        # State
        self._state = CUSUMState(running_mean=baseline_mean)
        self._burn_in_values: List[float] = []
        self._history: Deque[ModelPerformanceSnapshot] = deque(maxlen=1000)
        self._alerts: List[DriftAlert] = []
        self._recent_values: Deque[float] = deque(maxlen=window_size)

        logger.info(
            "cusum_initialized",
            metric=metric_name,
            baseline_mean=baseline_mean,
            baseline_std=baseline_std,
            delta=delta,
            h=h,
        )

    @property
    def current_status(self) -> ModelStatus:
        """Current monitoring status."""
        if self._state.s_upper > self.threshold * 0.8:
            return ModelStatus.DRIFT_DETECTED
        elif self._state.s_upper > self.threshold * 0.5:
            return ModelStatus.WARNING
        elif self._state.n_alerts > 0:
            # Check if last alert was recent
            return ModelStatus.WARNING
        return ModelStatus.STABLE

    @property
    def alert_history(self) -> List[DriftAlert]:
        """All generated alerts."""
        return list(self._alerts)

    @property
    def performance_history(self) -> List[ModelPerformanceSnapshot]:
        """Performance snapshot history."""
        return list(self._history)

    def update(
        self,
        metric_value: float,
        prediction: Optional[float] = None,
        actual: Optional[float] = None,
    ) -> Optional[DriftAlert]:
        """Process a new observation and check for drift.

        This is the main entry point for online monitoring. Call this
        each time a new model prediction is evaluated.

        Args:
            metric_value: The observed performance metric (e.g., accuracy, AUC)
            prediction: Optional raw prediction value
            actual: Optional actual outcome value

        Returns:
            DriftAlert if drift detected, None otherwise
        """
        self._state.n_observations += 1
        self._recent_values.append(metric_value)

        # --- Burn-in phase: collect samples to calibrate ---
        if self._state.n_observations <= self.burn_in:
            self._burn_in_values.append(metric_value)
            if self._state.n_observations == self.burn_in:
                self._calibrate_baseline()
            return None

        # --- Update running statistics (Welford's algorithm) ---
        n = self._state.n_observations
        delta_val = metric_value - self._state.running_mean
        self._state.running_mean += delta_val / n
        delta_val2 = metric_value - self._state.running_mean
        self._state.running_m2 += delta_val * delta_val2

        # Adaptive baseline update
        if self.adaptive_baseline and len(self._recent_values) >= 50:
            recent = np.array(self._recent_values)
            self.baseline_mean = float(np.mean(recent[-100:]))
            self.baseline_std = max(float(np.std(recent[-100:])), 1e-6)

        # --- Standardize the observation ---
        z = (metric_value - self.baseline_mean) / max(self.baseline_std, 1e-10)

        # --- Update CUSUM statistics ---
        # Upper CUSUM: detects degradation (metric dropping below baseline)
        # For accuracy-like metrics (higher = better), degradation means z < 0
        # We use the convention: S accumulates negative z-scores
        self._state.s_upper = max(
            0, self._state.s_upper + (-z) - self.k
        )
        # Lower CUSUM: detects improvement (metric rising above baseline)
        self._state.s_lower = min(
            0, self._state.s_lower + (-z) + self.k
        )

        # --- Record snapshot ---
        status = self._evaluate_status()
        snapshot = ModelPerformanceSnapshot(
            timestamp=datetime.now(timezone.utc),
            metric_name=self.metric_name,
            metric_value=metric_value,
            cusum_upper=self._state.s_upper,
            cusum_lower=self._state.s_lower,
            baseline_mean=self.baseline_mean,
            baseline_std=self.baseline_std,
            z_score=z,
            status=status,
        )
        self._history.append(snapshot)

        # --- Check for alerts ---
        alert = self._check_alert(metric_value, z)
        if alert:
            self._alerts.append(alert)
            # Reset CUSUM after alert (avoid repeated alerts)
            self._state.s_upper = 0.0
            self._state.s_lower = 0.0
            self._state.last_alert_index = self._state.n_observations
            self._state.n_alerts += 1

            logger.warning(
                "drift_detected",
                metric=self.metric_name,
                direction=alert.direction.value,
                severity=alert.severity.value,
                drift_magnitude=round(alert.drift_magnitude, 4),
                cusum_value=round(alert.cusum_value, 4),
            )

        return alert

    def get_status(self) -> Dict[str, Any]:
        """Get current monitoring status as a dictionary.

        Returns:
            Dictionary with current CUSUM state, statistics, and status
        """
        recent_mean = (
            float(np.mean(list(self._recent_values)))
            if self._recent_values
            else self.baseline_mean
        )
        recent_std = (
            float(np.std(list(self._recent_values)))
            if len(self._recent_values) > 1
            else self.baseline_std
        )

        return {
            "metric_name": self.metric_name,
            "status": self.current_status.value,
            "observations": self._state.n_observations,
            "alerts_total": self._state.n_alerts,
            "samples_since_last_alert": (
                self._state.n_observations - self._state.last_alert_index
                if self._state.last_alert_index >= 0
                else self._state.n_observations
            ),
            "cusum_upper": round(self._state.s_upper, 6),
            "cusum_lower": round(self._state.s_lower, 6),
            "threshold": round(self.threshold, 4),
            "baseline": {
                "mean": round(self.baseline_mean, 6),
                "std": round(self.baseline_std, 6),
                "delta": self.delta,
                "allowance_k": round(self.k, 4),
            },
            "recent_performance": {
                "mean": round(recent_mean, 6),
                "std": round(recent_std, 6),
                "window_size": len(self._recent_values),
            },
            "drift_detected": self.current_status in (
                ModelStatus.DRIFT_DETECTED,
                ModelStatus.RETRAINING_REQUIRED,
            ),
            "last_alert": (
                self._alerts[-1].to_dict() if self._alerts else None
            ),
        }

    def get_performance_trend(
        self, window: int = 50
    ) -> Dict[str, Any]:
        """Get performance trend over recent observations.

        Args:
            window: Number of recent observations to analyze

        Returns:
            Dictionary with trend analysis
        """
        if not self._history:
            return {"status": "no_data", "window": window}

        recent = list(self._history)[-window:]
        values = [s.metric_value for s in recent]
        z_scores = [s.z_score for s in recent]

        if len(values) < 2:
            return {"status": "insufficient_data", "n_observations": len(values)}

        # Linear trend
        x = np.arange(len(values))
        coeffs = np.polyfit(x, values, 1)
        slope = coeffs[0]

        # Trend classification
        if slope > 0.001:
            trend = "improving"
        elif slope < -0.001:
            trend = "degrading"
        else:
            trend = "stable"

        return {
            "status": "ok",
            "window": len(values),
            "current_value": round(values[-1], 6),
            "mean": round(float(np.mean(values)), 6),
            "std": round(float(np.std(values)), 6),
            "min": round(float(np.min(values)), 6),
            "max": round(float(np.max(values)), 6),
            "trend": trend,
            "trend_slope": round(float(slope), 8),
            "mean_z_score": round(float(np.mean(z_scores)), 4),
            "latest_z_score": round(z_scores[-1], 4),
            "observations_outside_2sigma": int(
                np.sum(np.abs(np.array(z_scores)) > 2)
            ),
        }

    # -------------------------------------------------------------------
    # Private Methods
    # -------------------------------------------------------------------

    def _calibrate_baseline(self) -> None:
        """Calibrate baseline from burn-in observations.

        If burn-in values have near-zero variance (e.g., all identical),
        the original baseline_std parameter is preserved to avoid
        division-by-near-zero in standardization.
        """
        values = np.array(self._burn_in_values)
        self.baseline_mean = float(np.mean(values))
        calibrated_std = float(np.std(values))

        # Use calibrated std only if it's meaningfully non-zero;
        # otherwise keep the original baseline_std to avoid z-scores
        # blowing up when burn-in values are identical.
        if calibrated_std > 1e-4:
            self.baseline_std = calibrated_std
        # else: keep the original baseline_std

        self._state.running_mean = self.baseline_mean

        logger.info(
            "cusum_calibrated",
            metric=self.metric_name,
            baseline_mean=round(self.baseline_mean, 6),
            baseline_std=round(self.baseline_std, 6),
            n_burn_in=len(values),
            calibrated_from_data=calibrated_std > 1e-4,
        )

    def _evaluate_status(self) -> ModelStatus:
        """Evaluate current status based on CUSUM values."""
        if self._state.s_upper > self.threshold:
            return ModelStatus.DRIFT_DETECTED
        elif self._state.s_upper > self.threshold * 0.5:
            return ModelStatus.WARNING
        return ModelStatus.STABLE

    def _check_alert(
        self, metric_value: float, z_score: float
    ) -> Optional[DriftAlert]:
        """Check if an alert should be generated.

        Args:
            metric_value: Current metric value
            z_score: Standardized metric value

        Returns:
            DriftAlert if threshold breached, None otherwise
        """
        now = datetime.now(timezone.utc)
        samples_since = (
            self._state.n_observations - self._state.last_alert_index
            if self._state.last_alert_index >= 0
            else self._state.n_observations
        )

        # Check upper CUSUM (degradation)
        if self._state.s_upper > self.threshold:
            drift_mag = self._state.s_upper / max(self.baseline_std, 1e-10)
            severity = self._classify_severity(drift_mag)

            return DriftAlert(
                timestamp=now,
                direction=DriftDirection.DEGRADATION,
                severity=severity,
                cusum_value=self._state.s_upper,
                threshold=self.threshold,
                drift_magnitude=drift_mag,
                metric_name=self.metric_name,
                metric_value=metric_value,
                baseline_value=self.baseline_mean,
                samples_since_last_alert=samples_since,
                recommendation=self._recommend_action(
                    DriftDirection.DEGRADATION, severity
                ),
            )

        # Check lower CUSUM (improvement — informational)
        if abs(self._state.s_lower) > self.threshold:
            drift_mag = abs(self._state.s_lower) / max(self.baseline_std, 1e-10)

            return DriftAlert(
                timestamp=now,
                direction=DriftDirection.IMPROVEMENT,
                severity=AlertSeverity.INFO,
                cusum_value=self._state.s_lower,
                threshold=self.threshold,
                drift_magnitude=drift_mag,
                metric_name=self.metric_name,
                metric_value=metric_value,
                baseline_value=self.baseline_mean,
                samples_since_last_alert=samples_since,
                recommendation=(
                    "Model performance has improved significantly. "
                    "Consider updating the baseline to reflect new performance level."
                ),
            )

        return None

    def _classify_severity(self, drift_magnitude: float) -> AlertSeverity:
        """Classify alert severity based on drift magnitude.

        Args:
            drift_magnitude: Magnitude of drift in σ units

        Returns:
            AlertSeverity level
        """
        if drift_magnitude > 6.0:
            return AlertSeverity.CRITICAL
        elif drift_magnitude > 3.0:
            return AlertSeverity.WARNING
        else:
            return AlertSeverity.INFO

    def _recommend_action(
        self, direction: DriftDirection, severity: AlertSeverity
    ) -> str:
        """Generate recommended action based on drift characteristics.

        Args:
            direction: Direction of drift
            severity: Severity of the alert

        Returns:
            Human-readable recommendation string
        """
        if direction == DriftDirection.IMPROVEMENT:
            return (
                "Performance has improved. Update the baseline to reflect "
                "the new performance level and continue monitoring."
            )

        if severity == AlertSeverity.CRITICAL:
            return (
                "CRITICAL: Significant model degradation detected. "
                "Immediately retrain the model with recent data. "
                "Consider pausing automated credit decisions until retrained."
            )
        elif severity == AlertSeverity.WARNING:
            return (
                "WARNING: Model performance is declining. Schedule model "
                "retraining within 24-48 hours. Investigate potential causes "
                "(data distribution changes, feature drift, etc.)."
            )
        else:
            return (
                "INFO: Minor performance shift detected. Continue monitoring. "
                "If trend persists, investigate data quality and consider "
                "incremental model update."
            )


# ---------------------------------------------------------------------------
# Multi-Metric Drift Monitor
# ---------------------------------------------------------------------------

class ModelDriftMonitor:
    """Monitors multiple model metrics simultaneously.

    Manages CUSUM detectors for multiple performance metrics (accuracy,
    AUC, precision, recall, calibration, etc.) and provides a unified
    view of model health.

    Args:
        metrics_config: Dict mapping metric names to their baseline config
                        e.g., {"accuracy": {"mean": 0.85, "std": 0.05},
                               "auc": {"mean": 0.90, "std": 0.03}}
        delta: Default shift detection threshold (σ units)
        h: Default decision threshold
        burn_in: Default burn-in period
    """

    def __init__(
        self,
        metrics_config: Optional[Dict[str, Dict[str, float]]] = None,
        delta: float = 1.0,
        h: float = 4.0,
        burn_in: int = 30,
    ):
        self._detectors: Dict[str, CUSUMDriftDetector] = {}
        self._delta = delta
        self._h = h
        self._burn_in = burn_in

        if metrics_config:
            for name, config in metrics_config.items():
                self.add_metric(
                    name,
                    baseline_mean=config.get("mean", 0.85),
                    baseline_std=config.get("std", 0.05),
                )

    def add_metric(
        self,
        name: str,
        baseline_mean: float = 0.85,
        baseline_std: float = 0.05,
        delta: Optional[float] = None,
        h: Optional[float] = None,
        burn_in: Optional[int] = None,
    ) -> None:
        """Add a metric to monitor.

        Args:
            name: Metric name
            baseline_mean: Expected value under no drift
            baseline_std: Expected variability
            delta: Override default shift detection threshold
            h: Override default decision threshold
            burn_in: Override default burn-in period
        """
        self._detectors[name] = CUSUMDriftDetector(
            baseline_mean=baseline_mean,
            baseline_std=baseline_std,
            delta=delta or self._delta,
            h=h or self._h,
            burn_in=burn_in if burn_in is not None else self._burn_in,
            metric_name=name,
        )
        logger.info("drift_monitor_metric_added", metric=name)

    def update(
        self, metric_name: str, value: float
    ) -> Optional[DriftAlert]:
        """Update a specific metric and check for drift.

        Args:
            metric_name: Name of the metric to update
            value: Observed metric value

        Returns:
            DriftAlert if detected, None otherwise

        Raises:
            KeyError: If metric_name not registered
        """
        if metric_name not in self._detectors:
            raise KeyError(f"Metric '{metric_name}' not registered. "
                           f"Available: {list(self._detectors.keys())}")
        return self._detectors[metric_name].update(value)

    def update_batch(
        self, metrics: Dict[str, float]
    ) -> List[DriftAlert]:
        """Update multiple metrics at once.

        Args:
            metrics: Dict mapping metric names to values

        Returns:
            List of any alerts generated
        """
        alerts = []
        for name, value in metrics.items():
            if name in self._detectors:
                alert = self._detectors[name].update(value)
                if alert:
                    alerts.append(alert)
        return alerts

    def get_overall_status(self) -> Dict[str, Any]:
        """Get unified status across all monitored metrics.

        Returns:
            Dictionary with overall model health status
        """
        metric_statuses = {}
        any_drift = False
        any_warning = False

        for name, detector in self._detectors.items():
            status = detector.get_status()
            metric_statuses[name] = status

            if status["drift_detected"]:
                any_drift = True
            elif detector.current_status == ModelStatus.WARNING:
                any_warning = True

        if any_drift:
            overall = ModelStatus.DRIFT_DETECTED.value
        elif any_warning:
            overall = ModelStatus.WARNING.value
        else:
            overall = ModelStatus.STABLE.value

        return {
            "overall_status": overall,
            "metrics_monitored": len(self._detectors),
            "drift_detected_in_any": any_drift,
            "metrics": metric_statuses,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def get_all_alerts(
        self, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get recent alerts across all metrics.

        Args:
            limit: Maximum number of alerts to return

        Returns:
            List of alert dictionaries, sorted by timestamp descending
        """
        all_alerts = []
        for detector in self._detectors.values():
            for alert in detector.alert_history:
                all_alerts.append(alert.to_dict())

        # Sort by timestamp descending
        all_alerts.sort(key=lambda a: a["timestamp"], reverse=True)
        return all_alerts[:limit]
