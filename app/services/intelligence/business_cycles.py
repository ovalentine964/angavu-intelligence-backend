"""
Business Cycle Analysis — ECO 322: Advanced Macroeconomics.

Business cycle indicators, leading/lagging indicators, and
macroeconomic nowcasting for Biashara Intelligence's GDP Estimator.

Academic Foundation:
- ECO 322: Advanced Macroeconomics — Dynamic AD-AS, New Keynesian
  Phillips Curve, business cycle theory (real business cycles, New
  Keynesian), nowcasting methodology, monetary policy transmission

Key Applications:
1. Business cycle phase detection (expansion, peak, contraction, trough)
2. Leading/lagging/coincident indicator construction
3. Composite Economic Index from transaction data
4. Recession probability estimation
5. Phillips Curve trade-off analysis

This module is wired into GDPEstimatorService for cycle analysis.
"""

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import structlog
from scipy import stats as sp_stats

logger = structlog.get_logger(__name__)


class BusinessCycleAnalyzer:
    """
    Business cycle analysis engine.

    Implements ECO 322 concepts:
    - Business cycle phases: expansion, peak, contraction, trough
    - Leading indicators: predict turning points 3-6 months ahead
    - Coincident indicators: confirm current phase
    - Lagging indicators: confirm phase after the fact
    - Composite index: weighted average of indicators
    """

    # Indicator classification
    LEADING_INDICATORS = [
        "new_business_registrations",
        "average_transaction_value_trend",
        "digital_payment_adoption_rate",
        "credit_demand_index",
        "inventory_buildup_rate",
    ]

    COINCIDENT_INDICATORS = [
        "total_transaction_volume",
        "active_business_count",
        "total_revenue",
        "employment_level",
    ]

    LAGGING_INDICATORS = [
        "average_loan_size",
        "unemployment_duration",
        "price_level_change",
        "interest_rate",
    ]

    @classmethod
    def detect_cycle_phase(
        cls,
        revenue_series: np.ndarray,
        window: int = 7,
    ) -> Dict[str, Any]:
        """
        Detect current business cycle phase from revenue data.

        Uses Hodrick-Prescott filter to separate trend from cycle,
        then classifies phase based on cycle component.

        Phases (ECO 322 § Business Cycles):
        - Expansion: cycle > 0 and rising (GDP above trend, growing)
        - Peak: cycle > 0 and falling (GDP above trend, slowing)
        - Contraction: cycle < 0 and falling (GDP below trend, shrinking)
        - Trough: cycle < 0 and rising (GDP below trend, recovering)

        Args:
            revenue_series: Daily or weekly revenue time series
            window: Smoothing window for cycle detection

        Returns:
            Dict with cycle phase, indicators, and confidence
        """
        if len(revenue_series) < 14:
            return {
                "phase": "indeterminate",
                "confidence": 0.0,
                "error": "Need at least 14 observations",
            }

        # HP filter decomposition
        from app.services.intelligence.biashara_pulse import _hodrick_prescott_filter
        trend, cycle = _hodrick_prescott_filter(revenue_series, lambd=1600)

        # Recent cycle values
        recent_cycle = cycle[-window:]
        prev_cycle = cycle[-2 * window:-window] if len(cycle) >= 2 * window else cycle[:window]

        current_cycle = float(np.mean(recent_cycle))
        cycle_slope = float(np.mean(np.diff(recent_cycle)))

        # Phase classification
        if current_cycle > 0 and cycle_slope > 0:
            phase = "expansion"
            confidence = min(1.0, abs(cycle_slope) / max(abs(np.std(cycle)), 1))
        elif current_cycle > 0 and cycle_slope <= 0:
            phase = "peak"
            confidence = min(1.0, abs(current_cycle) / max(abs(np.std(cycle)), 1))
        elif current_cycle < 0 and cycle_slope < 0:
            phase = "contraction"
            confidence = min(1.0, abs(cycle_slope) / max(abs(np.std(cycle)), 1))
        elif current_cycle < 0 and cycle_slope >= 0:
            phase = "trough"
            confidence = min(1.0, abs(current_cycle) / max(abs(np.std(cycle)), 1))
        else:
            phase = "stable"
            confidence = 0.5

        # Cycle amplitude
        cycle_amplitude = float(np.max(cycle) - np.min(cycle))
        cycle_volatility = float(np.std(cycle))

        return {
            "phase": phase,
            "confidence": round(confidence, 3),
            "current_cycle_value": round(current_cycle, 4),
            "cycle_slope": round(cycle_slope, 6),
            "cycle_amplitude": round(cycle_amplitude, 4),
            "cycle_volatility": round(cycle_volatility, 4),
            "trend_value": round(float(trend[-1]), 2),
            "observations": len(revenue_series),
            "method": "ECO 322 — HP Filter Business Cycle Detection",
        }

    @classmethod
    def composite_economic_index(
        cls,
        indicators: Dict[str, np.ndarray],
        weights: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        """
        Construct Composite Economic Index from multiple indicators.

        ECO 322 § Nowcasting: Combines leading, coincident, and
        lagging indicators into a single index using weighted
        standardization.

        Method:
        1. Standardize each indicator (z-score)
        2. Apply weights (leading = 0.5, coincident = 0.35, lagging = 0.15)
        3. Average weighted z-scores
        4. Normalize to 0-100 scale

        Args:
            indicators: Dict of indicator_name → time series
            weights: Optional custom weights (default: equal within category)

        Returns:
            Dict with composite index, components, and interpretation
        """
        if not indicators:
            return {"error": "No indicators provided"}

        # Default weights
        if weights is None:
            weights = {}
            for name in indicators:
                if name in cls.LEADING_INDICATORS:
                    weights[name] = 0.5 / max(len([n for n in indicators if n in cls.LEADING_INDICATORS]), 1)
                elif name in cls.COINCIDENT_INDICATORS:
                    weights[name] = 0.35 / max(len([n for n in indicators if n in cls.COINCIDENT_INDICATORS]), 1)
                else:
                    weights[name] = 0.15 / max(len([n for n in indicators if n not in cls.LEADING_INDICATORS and n not in cls.COINCIDENT_INDICATORS]), 1)

        # Standardize each indicator
        standardized = {}
        for name, series in indicators.items():
            if len(series) < 2:
                continue
            mean = np.mean(series)
            std = np.std(series)
            if std > 0:
                z = (series - mean) / std
                standardized[name] = float(z[-1])  # Most recent value
            else:
                standardized[name] = 0.0

        # Weighted composite
        total_weight = sum(weights.get(name, 0) for name in standardized)
        if total_weight <= 0:
            return {"error": "No valid indicators"}

        composite = sum(
            standardized[name] * weights.get(name, 0)
            for name in standardized
        ) / total_weight

        # Normalize to 0-100 (using logistic transform)
        index_value = 100 / (1 + np.exp(-composite))

        # Interpretation
        if index_value > 65:
            interpretation = "Strong expansion — economic activity well above normal"
        elif index_value > 55:
            interpretation = "Moderate expansion — economy growing above trend"
        elif index_value > 45:
            interpretation = "Stable — economy near trend"
        elif index_value > 35:
            interpretation = "Moderate slowdown — economy below trend"
        else:
            interpretation = "Contraction — economic activity significantly below normal"

        return {
            "composite_index": round(index_value, 1),
            "standardized_components": {
                name: round(val, 3) for name, val in standardized.items()
            },
            "weights_used": {name: round(w, 4) for name, w in weights.items() if name in standardized},
            "interpretation": interpretation,
            "n_indicators": len(standardized),
            "method": "ECO 322 — Composite Economic Index",
        }

    @classmethod
    def recession_probability(
        cls,
        revenue_series: np.ndarray,
        transaction_series: np.ndarray,
        lookback_months: int = 6,
    ) -> Dict[str, Any]:
        """
        Estimate recession probability from transaction data.

        ECO 322 § Recession Forecasting: Uses multiple signals:
        1. Revenue decline (2+ consecutive months of falling revenue)
        2. Transaction volume decline (fewer transactions)
        3. Business closures (inactive businesses)
        4. Yield curve analog (short vs long-term revenue trends)

        Args:
            revenue_series: Monthly revenue totals
            transaction_series: Monthly transaction counts
            lookback_months: Months to analyze

        Returns:
            Dict with recession probability and contributing factors
        """
        if len(revenue_series) < 3:
            return {"recession_probability": 0.0, "error": "Insufficient data"}

        n = min(len(revenue_series), lookback_months)
        recent_rev = revenue_series[-n:]
        recent_txns = transaction_series[-n:] if len(transaction_series) >= n else None

        signals = 0
        total_signals = 4

        # Signal 1: Revenue decline trend
        if len(recent_rev) >= 3:
            x = np.arange(len(recent_rev))
            slope, _, r_value, p_value, _ = sp_stats.linregress(x, recent_rev)
            if slope < 0 and p_value < 0.10:
                signals += 1

        # Signal 2: Consecutive monthly declines
        declines = sum(1 for i in range(1, len(recent_rev)) if recent_rev[i] < recent_rev[i - 1])
        if declines >= len(recent_rev) * 0.6:
            signals += 1

        # Signal 3: Transaction volume decline
        if recent_txns is not None and len(recent_txns) >= 3:
            x = np.arange(len(recent_txns))
            slope_txn, _, _, p_txn, _ = sp_stats.linregress(x, recent_txns)
            if slope_txn < 0 and p_txn < 0.10:
                signals += 1

        # Signal 4: Revenue below 6-month average
        if len(revenue_series) >= 6:
            avg_6m = np.mean(revenue_series[-6:])
            if recent_rev[-1] < avg_6m * 0.90:
                signals += 1

        # Probability estimate
        recession_prob = signals / total_signals

        return {
            "recession_probability": round(recession_prob, 3),
            "signals_triggered": signals,
            "total_signals": total_signals,
            "risk_level": (
                "high" if recession_prob >= 0.75
                else "elevated" if recession_prob >= 0.50
                else "moderate" if recession_prob >= 0.25
                else "low"
            ),
            "revenue_trend": "declining" if signals >= 2 else "stable",
            "method": "ECO 322 — Recession Probability Model",
        }

    @classmethod
    def phillips_curve_analysis(
        cls,
        inflation_series: np.ndarray,
        unemployment_proxy: np.ndarray,
    ) -> Dict[str, Any]:
        """
        Phillips Curve trade-off analysis.

        ECO 322 § New Keynesian Phillips Curve:
        π_t = β·E_t[π_{t+1}] + κ·(y_t - y_n)

        Simplified: Inverse relationship between inflation and
        unemployment (or economic activity).

        For informal economy: uses price changes (inflation proxy)
        and activity levels (employment proxy).

        Args:
            inflation_series: Monthly inflation/price change rates
            unemployment_proxy: Activity levels (inverse of unemployment)

        Returns:
            Dict with Phillips Curve parameters and trade-off
        """
        if len(inflation_series) < 6 or len(unemployment_proxy) < 6:
            return {"error": "Need at least 6 observations"}

        n = min(len(inflation_series), len(unemployment_proxy))
        inf = inflation_series[-n:]
        unemp = unemployment_proxy[-n:]

        # OLS: inflation = α + β * activity + ε
        X = np.column_stack([np.ones(n), unemp])
        try:
            beta = np.linalg.lstsq(X, inf, rcond=None)[0]
            residuals = inf - X @ beta
            r_squared = 1 - np.sum(residuals ** 2) / max(np.sum((inf - np.mean(inf)) ** 2), 1e-10)
        except np.linalg.LinAlgError:
            return {"error": "Estimation failed"}

        slope = float(beta[1])
        # Negative slope = standard Phillips Curve (inflation-activity trade-off)
        has_tradeoff = slope < 0

        return {
            "slope": round(slope, 6),
            "intercept": round(float(beta[0]), 6),
            "r_squared": round(float(r_squared), 4),
            "has_phillips_tradeoff": has_tradeoff,
            "interpretation": (
                "Standard Phillips Curve trade-off detected: higher activity associated with higher inflation."
                if has_tradeoff
                else "No Phillips Curve trade-off: activity and inflation move together (supply shocks dominant)."
            ),
            "method": "ECO 322 — Phillips Curve Analysis",
        }

    @classmethod
    def leading_indicator_report(
        cls,
        indicators: Dict[str, np.ndarray],
    ) -> Dict[str, Any]:
        """
        Construct and interpret leading economic indicators.

        ECO 322 § Leading Indicators: Variables that predict future
        economic activity. In the informal economy:
        - New business registrations → future economic activity
        - Digital payment adoption → modernization trend
        - Credit demand → investment intentions
        - Average transaction value → consumer confidence

        Args:
            indicators: Dict of indicator_name → monthly time series

        Returns:
            Dict with leading index, trend signals, and forecast
        """
        results = {}
        signals = []

        for name, series in indicators.items():
            if len(series) < 3:
                continue

            # Trend analysis
            x = np.arange(len(series))
            slope, intercept, r_value, p_value, std_err = sp_stats.linregress(x, series)

            # Recent vs historical
            recent = float(np.mean(series[-3:]))
            historical = float(np.mean(series))

            trend_signal = "rising" if slope > 0 and p_value < 0.10 else "falling" if slope < 0 and p_value < 0.10 else "flat"

            results[name] = {
                "current_value": round(float(series[-1]), 4),
                "trend": trend_signal,
                "slope": round(float(slope), 6),
                "r_squared": round(float(r_value ** 2), 4),
                "recent_vs_historical": round(recent / max(historical, 1e-10), 3),
            }

            if trend_signal == "rising":
                signals.append(1)
            elif trend_signal == "falling":
                signals.append(-1)
            else:
                signals.append(0)

        # Composite signal
        if signals:
            avg_signal = np.mean(signals)
            if avg_signal > 0.3:
                outlook = "positive"
            elif avg_signal < -0.3:
                outlook = "negative"
            else:
                outlook = "neutral"
        else:
            outlook = "insufficient_data"

        return {
            "indicators": results,
            "composite_signal": round(float(np.mean(signals)), 3) if signals else 0,
            "outlook": outlook,
            "n_indicators": len(results),
            "method": "ECO 322 — Leading Indicator Analysis",
        }
