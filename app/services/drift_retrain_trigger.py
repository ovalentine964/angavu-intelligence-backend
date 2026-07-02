"""
Drift-to-Retrain Auto-Trigger — Closes the drift detection loop.

When the CUSUM drift detector fires a WARNING or CRITICAL alert,
this module automatically enqueues a model training task.

Loop closed:
    Model predictions → CUSUM monitoring → Drift detected →
    Task enqueued → Training loop runs → New model deployed ↻

Usage:
    from app.services.drift_retrain_trigger import setup_drift_auto_retrain

    monitor = ModelDriftMonitor(metrics_config={...})
    await setup_drift_auto_retrain(monitor, model_type="credit_scoring")
"""

from __future__ import annotations

import structlog

from app.services.drift_detector import (
    AlertSeverity,
    DriftAlert,
    DriftDirection,
    ModelDriftMonitor,
)
from app.services.task_queue import get_task_queue

logger = structlog.get_logger(__name__)


async def _handle_drift_alert(alert: DriftAlert) -> None:
    """
    Callback invoked when drift is detected.

    Enqueues a model_training task in the background task queue,
    which triggers the full training loop (signal capture → data
    pipeline → training → evaluation → experiment → deployment →
    monitoring).
    """
    task_queue = get_task_queue()

    payload = {
        "model_type": alert.metric_name,
        "trigger": "drift_alert",
        "alert": alert.to_dict(),
    }

    task_id = await task_queue.enqueue("model_training", payload, priority=0)

    logger.info(
        "drift_retrain_enqueued",
        task_id=task_id,
        metric=alert.metric_name,
        severity=alert.severity.value,
        drift_magnitude=round(alert.drift_magnitude, 4),
    )


async def setup_drift_auto_retrain(
    monitor: ModelDriftMonitor,
    model_type: str | None = None,
) -> None:
    """
    Wire a ModelDriftMonitor to automatically trigger retraining.

    Args:
        monitor: The drift monitor to attach the callback to
        model_type: Optional model type hint (defaults to metric name)
    """
    monitor.set_drift_callback(_handle_drift_alert)

    logger.info(
        "drift_auto_retrain_configured",
        metrics_monitored=len(monitor._detectors),
        model_type=model_type,
    )
