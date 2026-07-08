"""
Time Series Analysis Module — STA 244 Time Series Analysis & Forecasting.

Extracted from statistical_foundation.py for modularity.

This module provides the time series analysis building blocks.
Full ARIMA/VAR/cointegration implementations live in
econometric_engine.py (ARIMAModel, VARModel, CointegrationTester).

Re-exports key classes from econometric_engine for convenience.

Academic Foundation:
- STA 244: Time Series Analysis & Forecasting → ARIMA/SARIMA,
  exponential smoothing (Holt-Winters), seasonal decomposition,
  ACF/PACF, unit root tests, cointegration
- ECO 424: Econometrics → VAR models, Granger causality

Usage:
    from app.services.time_series import ARIMAModel, VARModel
"""

# Re-export from econometric_engine for backward compatibility
from app.services.econometric_engine import (
    ARIMAModel,
    CointegrationTester,
    VARModel,
)

__all__ = ["ARIMAModel", "VARModel", "CointegrationTester"]
