"""
Intelligence Pipeline — Drift monitoring for intelligence products.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)

# Global instance
_drift_monitor = None


@dataclass
class DriftSignal:
    """A drift detection signal."""
    metric_name: str
    current_value: float
    baseline_value: float
    drift_magnitude: float
    detected_at: float = field(default_factory=time.time)


class IntelligenceDriftMonitor:
    """
    Monitors intelligence product outputs for drift.

    Tracks prediction accuracy over time and raises alerts
    when model performance degrades beyond thresholds.
    """

    def __init__(self):
        self._baselines: dict[str, float] = {}
        self._current_values: dict[str, float] = {}
        self._signals: list[DriftSignal] = []
        self._drift_threshold = 0.15

    async def check_alama_score(
        self,
        predicted_score: int,
        actual_outcome: int,
    ) -> None:
        """Check Alama Score predictions for drift."""
        error = abs(predicted_score - actual_outcome) / max(actual_outcome, 1)
        self._current_values["alama_score_error"] = error

        baseline = self._baselines.get("alama_score_error", 0.1)
        if abs(error - baseline) > self._drift_threshold:
            signal = DriftSignal(
                metric_name="alama_score_error",
                current_value=error,
                baseline_value=baseline,
                drift_magnitude=abs(error - baseline),
            )
            self._signals.append(signal)
            logger.warning("alama_score_drift_detected", magnitude=signal.drift_magnitude)

    async def check_soko_pulse(
        self,
        predicted_price: float,
        actual_price: float,
    ) -> None:
        """Check Soko Pulse price predictions for drift."""
        error = abs(predicted_price - actual_price) / max(actual_price, 1)
        self._current_values["soko_pulse_error"] = error

        baseline = self._baselines.get("soko_pulse_error", 0.1)
        if abs(error - baseline) > self._drift_threshold:
            signal = DriftSignal(
                metric_name="soko_pulse_error",
                current_value=error,
                baseline_value=baseline,
                drift_magnitude=abs(error - baseline),
            )
            self._signals.append(signal)

    def set_baseline(self, metric_name: str, value: float) -> None:
        """Set baseline value for a metric."""
        self._baselines[metric_name] = value

    def get_status(self) -> dict:
        """Get drift detection status."""
        drift_detected = any(
            s.drift_magnitude > self._drift_threshold for s in self._signals[-10:]
        )
        return {
            "overall_status": "drift_detected" if drift_detected else "stable",
            "drift_detected_in_any": drift_detected,
            "baselines": dict(self._baselines),
            "current_values": dict(self._current_values),
            "recent_signals": len(self._signals),
        }


def get_intelligence_drift_monitor() -> IntelligenceDriftMonitor:
    """Get or create the global drift monitor."""
    global _drift_monitor
    if _drift_monitor is None:
        _drift_monitor = IntelligenceDriftMonitor()
    return _drift_monitor
