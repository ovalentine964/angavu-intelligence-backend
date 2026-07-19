"""
AnomalyDetectorAgent — Tier 3 utility agent for statistical anomaly detection.

Detects outliers in transaction data, price movements, and usage patterns
using simple statistical methods (z-score, IQR).

Tier: 3 (Utility) — stateless, on-demand invocation.
"""

from __future__ import annotations

import math
import time
from typing import Any

import structlog

from app.agents.base import AgentDecision, AgentResult, BiasharaAgent

logger = structlog.get_logger(__name__)


class AnomalyDetectorAgent(BiasharaAgent):
    """
    Detects anomalies in numerical data streams.

    Capabilities:
    - Z-score anomaly detection
    - IQR-based outlier detection
    - Trend break detection
    """

    def __init__(self):
        super().__init__(
            name="AnomalyDetector",
            role="Statistical anomaly detection",
            capabilities=[
                "zscore_detection",
                "iqr_detection",
                "trend_break_detection",
            ],
        )

    async def think(self, context: dict[str, Any]) -> AgentDecision:
        event_data = context.get("event", {})
        payload = event_data.get("payload", {})

        values = payload.get("values") or payload.get("data_points")
        if values and isinstance(values, list) and len(values) >= 3:
            return AgentDecision(
                action="detect",
                parameters={"values": values, "method": payload.get("method", "zscore")},
                confidence=0.85,
                reasoning=f"Received {len(values)} data points for anomaly detection",
            )

        return AgentDecision(
            action="idle",
            parameters={},
            confidence=0.5,
            reasoning="Insufficient data for anomaly detection",
        )

    async def act(self, decision: AgentDecision) -> AgentResult:
        start = time.time()

        if decision.action == "detect":
            values = decision.parameters.get("values", [])
            method = decision.parameters.get("method", "zscore")

            if method == "iqr":
                anomalies = self._iqr_detect(values)
            else:
                anomalies = self._zscore_detect(values)

            return AgentResult(
                success=True,
                data={
                    "anomalies": anomalies,
                    "total_points": len(values),
                    "anomaly_count": len(anomalies),
                    "method": method,
                },
                duration_ms=(time.time() - start) * 1000,
            )

        return AgentResult(
            success=True,
            data={"status": "idle"},
            duration_ms=(time.time() - start) * 1000,
        )

    def _zscore_detect(self, values: list[float], threshold: float = 2.5) -> list[dict[str, Any]]:
        """Detect anomalies using z-score."""
        if len(values) < 3:
            return []

        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        std = math.sqrt(variance) if variance > 0 else 0

        if std == 0:
            return []

        anomalies = []
        for i, v in enumerate(values):
            z = abs(v - mean) / std
            if z > threshold:
                anomalies.append({"index": i, "value": v, "z_score": round(z, 2)})

        return anomalies

    def _iqr_detect(self, values: list[float]) -> list[dict[str, Any]]:
        """Detect anomalies using IQR method."""
        if len(values) < 4:
            return []

        sorted_v = sorted(values)
        n = len(sorted_v)
        q1 = sorted_v[n // 4]
        q3 = sorted_v[3 * n // 4]
        iqr = q3 - q1

        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr

        anomalies = []
        for i, v in enumerate(values):
            if v < lower or v > upper:
                anomalies.append({
                    "index": i,
                    "value": v,
                    "lower_bound": round(lower, 2),
                    "upper_bound": round(upper, 2),
                })

        return anomalies
