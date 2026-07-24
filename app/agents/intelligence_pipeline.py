"""
Intelligence Pipeline — Drift detection and model monitoring.

Provides drift monitoring for intelligence models (AlamaScore, etc.)
to detect when model predictions diverge from actual outcomes.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class DriftAlert:
    """An alert indicating model drift."""
    model_name: str
    drift_magnitude: float
    direction: str  # over_predicting, under_predicting
    severity: str  # low, medium, high, critical
    metric_name: str
    metric_value: float
    baseline_value: float
    recommendation: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_name": self.model_name,
            "drift_magnitude": self.drift_magnitude,
            "direction": self.direction,
            "severity": self.severity,
            "metric_name": self.metric_name,
            "metric_value": self.metric_value,
            "baseline_value": self.baseline_value,
            "recommendation": self.recommendation,
            "timestamp": self.timestamp,
        }


class IntelligenceDriftMonitor:
    """
    Monitors intelligence model predictions vs actual outcomes.

    Tracks prediction accuracy over time and raises alerts
    when drift exceeds configurable thresholds.
    """

    def __init__(self, drift_threshold: float = 0.1):
        self._drift_threshold = drift_threshold
        self._predictions: dict[str, list[tuple[float, float]]] = defaultdict(list)  # model -> [(predicted, actual)]
        self._alerts: list[DriftAlert] = []
        self._drift_detected: dict[str, bool] = {}

    async def check_alama_score(
        self,
        predicted_score: int,
        actual_outcome: int,
    ) -> None:
        """Check AlamaScore prediction against actual outcome."""
        model_name = "alama_score"
        self._predictions[model_name].append((float(predicted_score), float(actual_outcome)))

        # Keep last 100 predictions
        if len(self._predictions[model_name]) > 100:
            self._predictions[model_name] = self._predictions[model_name][-50:]

        # Check for drift
        predictions = self._predictions[model_name]
        if len(predictions) >= 10:
            errors = [abs(p - a) / max(a, 1) for p, a in predictions[-20:]]
            avg_error = sum(errors) / len(errors)

            if avg_error > self._drift_threshold:
                self._drift_detected[model_name] = True
                alert = DriftAlert(
                    model_name=model_name,
                    drift_magnitude=avg_error,
                    direction="over_predicting" if sum(p - a for p, a in predictions[-20:]) > 0 else "under_predicting",
                    severity="high" if avg_error > 0.2 else "medium",
                    metric_name="mean_absolute_percentage_error",
                    metric_value=avg_error,
                    baseline_value=self._drift_threshold,
                    recommendation="Retrain model with recent data",
                )
                self._alerts.append(alert)
                logger.warning("alama_score_drift_detected", drift=avg_error)
            else:
                self._drift_detected[model_name] = False

    def get_status(self) -> dict[str, Any]:
        """Get drift monitor status."""
        return {
            "overall_status": "drift_detected" if any(self._drift_detected.values()) else "stable",
            "drift_detected_in_any": any(self._drift_detected.values()),
            "models_monitored": list(self._predictions.keys()),
            "total_alerts": len(self._alerts),
            "per_model": {
                name: {"drift_detected": detected}
                for name, detected in self._drift_detected.items()
            },
        }

    def generate_swahili_alert(self, model_name: str, drift_pct: float, domain: str) -> str:
        """Generate a Swahili alert message for drift."""
        return (
            f"Onyo: Mtindo wa {model_name} una mabadiliko ya {drift_pct:.1f}%. "
            f"Utafiti mpya unahitajika kwa {domain}."
        )


# Global singleton
_drift_monitor: IntelligenceDriftMonitor | None = None


def get_intelligence_drift_monitor() -> IntelligenceDriftMonitor:
    """Get the global intelligence drift monitor."""
    global _drift_monitor
    if _drift_monitor is None:
        _drift_monitor = IntelligenceDriftMonitor()
    return _drift_monitor
