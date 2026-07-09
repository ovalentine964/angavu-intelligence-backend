"""
PredictionAgent — Tier 3 utility agent for price/demand forecasting.

Wraps statistical forecasting models (moving average, exponential smoothing,
linear regression). Used by IntelligenceGenerator and domain agents.

Tier: 3 (Utility) — stateless, on-demand invocation.
"""

from __future__ import annotations

import statistics
import time
from typing import Any, Dict, List

import structlog

from app.agents.base import (
    AgentDecision, AgentEvent, AgentResult, BiasharaAgent,
)

logger = structlog.get_logger(__name__)


class PredictionAgent(BiasharaAgent):
    """
    Runs lightweight forecasting models on time-series data.

    Methods:
    - Simple Moving Average (SMA)
    - Exponential Smoothing (ETS)
    - Linear Trend Extrapolation
    - Seasonal decomposition (basic)

    Tier: 3 (Utility) — stateless
    """

    name = "PredictionAgent"
    role = "Forecasting and prediction specialist"
    tier = 3
    capabilities = [
        "price_forecasting",
        "demand_prediction",
        "trend_analysis",
        "moving_average",
        "exponential_smoothing",
        "linear_regression",
        "seasonal_analysis",
    ]

    def __init__(self):
        super().__init__(name=self.name, role=self.role, capabilities=self.capabilities)

    async def think(self, context: Dict[str, Any]) -> AgentDecision:
        event = context.get("event", {})
        payload = event.get("payload", {})
        action = payload.get("action", "forecast")

        if action in ("forecast", "predict", "price_forecast", "demand_forecast"):
            return AgentDecision(
                action="run_forecast",
                parameters={
                    "values": payload.get("values", []),
                    "periods": payload.get("periods", 7),
                    "method": payload.get("method", "exponential_smoothing"),
                    "metric_name": payload.get("metric_name", "price"),
                },
                confidence=0.85,
                reasoning="Running forecast model on time-series data",
            )
        return AgentDecision(action="noop", parameters={}, confidence=0.5, reasoning="No prediction requested")

    async def act(self, decision: AgentDecision) -> AgentResult:
        start = time.time()
        action = decision.action
        params = decision.parameters

        try:
            if action == "run_forecast":
                values = params.get("values", [])
                periods = params.get("periods", 7)
                method = params.get("method", "exponential_smoothing")
                metric_name = params.get("metric_name", "price")

                forecast = self._forecast(values, periods, method)
                duration_ms = (time.time() - start) * 1000

                return AgentResult(
                    success=True,
                    data={
                        "metric_name": metric_name,
                        "method": method,
                        "historical_count": len(values),
                        "forecast_periods": periods,
                        "forecast": forecast,
                        "confidence_interval": self._confidence_interval(values, forecast),
                    },
                    duration_ms=duration_ms,
                )
            elif action == "noop":
                return AgentResult(success=True, data=None, duration_ms=(time.time() - start) * 1000)
            else:
                return AgentResult(success=False, error=f"Unknown action: {action}", duration_ms=(time.time() - start) * 1000)
        except Exception as exc:
            return AgentResult(success=False, error=str(exc), duration_ms=(time.time() - start) * 1000)

    def _forecast(self, values: List[float], periods: int, method: str) -> List[Dict[str, Any]]:
        """Run the specified forecast method."""
        if not values or periods <= 0:
            return []

        if method == "moving_average":
            return self._moving_average_forecast(values, periods)
        elif method == "exponential_smoothing":
            return self._exponential_smoothing_forecast(values, periods)
        elif method == "linear":
            return self._linear_forecast(values, periods)
        else:
            return self._exponential_smoothing_forecast(values, periods)

    def _moving_average_forecast(self, values: List[float], periods: int, window: int = 5) -> List[Dict[str, Any]]:
        """Simple moving average forecast."""
        if len(values) < window:
            window = max(1, len(values))

        last_avg = statistics.mean(values[-window:])
        results = []
        extended = list(values)

        for i in range(periods):
            forecast_val = statistics.mean(extended[-window:])
            results.append({
                "period": i + 1,
                "forecast": round(forecast_val, 2),
                "method": "moving_average",
            })
            extended.append(forecast_val)

        return results

    def _exponential_smoothing_forecast(self, values: List[float], periods: int, alpha: float = 0.3) -> List[Dict[str, Any]]:
        """Exponential smoothing forecast."""
        if not values:
            return []

        # Calculate smoothed values
        smoothed = values[0]
        for v in values[1:]:
            smoothed = alpha * v + (1 - alpha) * smoothed

        # Forecast is flat at last smoothed value (simple exponential smoothing)
        results = []
        for i in range(periods):
            results.append({
                "period": i + 1,
                "forecast": round(smoothed, 2),
                "method": "exponential_smoothing",
                "alpha": alpha,
            })

        return results

    def _linear_forecast(self, values: List[float], periods: int) -> List[Dict[str, Any]]:
        """Linear trend extrapolation forecast."""
        if len(values) < 2:
            return [{"period": i + 1, "forecast": round(values[0] if values else 0, 2), "method": "linear"} for i in range(periods)]

        n = len(values)
        x_mean = (n - 1) / 2
        y_mean = statistics.mean(values)

        # Calculate slope and intercept
        numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        slope = numerator / denominator if denominator != 0 else 0
        intercept = y_mean - slope * x_mean

        results = []
        for i in range(periods):
            x = n + i
            forecast_val = intercept + slope * x
            results.append({
                "period": i + 1,
                "forecast": round(max(0, forecast_val), 2),
                "method": "linear",
                "trend": "increasing" if slope > 0 else "decreasing" if slope < 0 else "flat",
            })

        return results

    def _confidence_interval(self, historical: List[float], forecast: List[Dict], confidence: float = 0.95) -> Dict[str, Any]:
        """Calculate simple confidence intervals based on historical variance."""
        if len(historical) < 2:
            return {"lower": 0, "upper": 0, "confidence": confidence}

        stdev = statistics.stdev(historical)
        # 95% CI ≈ 1.96 * stdev
        z = 1.96 if confidence >= 0.95 else 1.65

        intervals = []
        for f in forecast:
            val = f.get("forecast", 0)
            intervals.append({
                "period": f["period"],
                "lower": round(max(0, val - z * stdev), 2),
                "upper": round(val + z * stdev, 2),
            })

        return {"intervals": intervals, "confidence": confidence, "historical_stdev": round(stdev, 2)}
