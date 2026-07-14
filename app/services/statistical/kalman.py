"""
Kalman Filter — GDP Nowcasting and Economic Indicator Smoothing.

Implements the Kalman filter for real-time estimation of latent
economic variables from noisy, mixed-frequency observations.

Academic Foundation:
- Kalman, R.E. (1960). A new approach to linear filtering and prediction
  problems. ASME Journal of Basic Engineering, 82(1), 35-45.
- STA 244 (Time Series Analysis): State-space models, Kalman filtering,
  nowcasting from mixed-frequency data
- ECO 205 (Macroeconomics): GDP nowcasting, business cycle extraction,
  trend-cycle decomposition
- ECO 322 (Advanced Macroeconomics): Dynamic factor models, MIDAS
  (Mixed Data Sampling) for bridging daily→quarterly

Use Cases:
1. GDP Nowcasting: Estimate current-quarter GDP from daily transactions
2. Smoothing noisy economic indicators (inflation, employment)
3. Extracting trend from cycle (business cycle analysis)
4. Missing data imputation in economic time series

The Kalman filter is the optimal linear estimator for state-space models:
    x_{t+1} = A x_t + B u_t + w_t    (state transition)
    y_t = C x_t + v_t                  (observation)

where w_t ~ N(0, Q), v_t ~ N(0, R)

Buyers: KNBS, CBK, Treasury, IMF, World Bank
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class KalmanState:
    """State of the Kalman filter at a single time step.

    Attributes:
        timestamp: Time of this state estimate
        state_estimate: Posterior state estimate (x̂_{t|t})
        covariance: Posterior error covariance (P_{t|t})
        innovation: Observation residual (y_t - C x̂_{t|t-1})
        innovation_covariance: Innovation covariance (S_t)
        log_likelihood: Log-likelihood of observation at this step
        kalman_gain: Kalman gain matrix at this step
    """
    timestamp: datetime
    state_estimate: np.ndarray
    covariance: np.ndarray
    innovation: Optional[np.ndarray] = None
    innovation_covariance: Optional[np.ndarray] = None
    log_likelihood: float = 0.0
    kalman_gain: Optional[np.ndarray] = None


@dataclass
class KalmanFilterResult:
    """Complete result from a Kalman filter run.

    Attributes:
        filtered_states: List of posterior state estimates
        smoothed_states: List of smoothed state estimates (RTS smoother)
        state_names: Names of state variables
        forecast: One-step-ahead forecasts
        filtered_values: Key filtered values for business consumption
        log_likelihood: Total log-likelihood
        n_observations: Number of observations processed
    """
    filtered_states: List[KalmanState]
    smoothed_states: Optional[List[KalmanState]]
    state_names: List[str]
    forecast: Dict[str, Any]
    filtered_values: Dict[str, Any]
    log_likelihood: float
    n_observations: int
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state_names": self.state_names,
            "n_observations": self.n_observations,
            "log_likelihood": round(self.log_likelihood, 2),
            "filtered_values": self.filtered_values,
            "forecast": self.forecast,
            "generated_at": self.generated_at.isoformat(),
        }


# ---------------------------------------------------------------------------
# Kalman Filter Implementation
# ---------------------------------------------------------------------------

class KalmanFilter:
    """
    General-purpose Kalman filter for state-space models.

    State-space model:
        x_{t+1} = A x_t + B u_t + w_t,  w_t ~ N(0, Q)
        y_t     = C x_t + v_t,           v_t ~ N(0, R)

    Supports:
    - Time-varying system matrices
    - Missing observations (NaN handling)
    - Maximum likelihood estimation of parameters
    - RTS smoother for retrospective state estimation
    - One-step-ahead forecasting

    Args:
        A: State transition matrix (n_states × n_states)
        C: Observation matrix (n_obs × n_states)
        Q: Process noise covariance (n_states × n_states)
        R: Observation noise covariance (n_obs × n_obs)
        B: Control input matrix (optional)
        x0: Initial state estimate
        P0: Initial error covariance
    """

    def __init__(
        self,
        A: np.ndarray,
        C: np.ndarray,
        Q: np.ndarray,
        R: np.ndarray,
        B: Optional[np.ndarray] = None,
        x0: Optional[np.ndarray] = None,
        P0: Optional[np.ndarray] = None,
    ):
        self.A = np.atleast_2d(A)
        self.C = np.atleast_2d(C)
        self.Q = np.atleast_2d(Q)
        self.R = np.atleast_2d(R)
        self.B = B

        n_states = self.A.shape[0]
        self.n_states = n_states
        self.n_obs = self.C.shape[0]

        # Initial state
        self.x = x0 if x0 is not None else np.zeros(n_states)
        self.x = np.atleast_1d(self.x)

        # Initial covariance (large = uncertain)
        self.P = P0 if P0 is not None else np.eye(n_states) * 100.0
        self.P = np.atleast_2d(self.P)

        # State history
        self._history: List[KalmanState] = []
        self._total_ll = 0.0

    def predict(
        self, u: Optional[np.ndarray] = None
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Prediction step: x̂_{t|t-1} = A x̂_{t-1|t-1} + B u_t

        Returns:
            (predicted_state, predicted_covariance)
        """
        # State prediction
        x_pred = self.A @ self.x
        if self.B is not None and u is not None:
            x_pred += self.B @ u

        # Covariance prediction
        P_pred = self.A @ self.P @ self.A.T + self.Q

        return x_pred, P_pred

    def update(
        self,
        y: np.ndarray,
        x_pred: np.ndarray,
        P_pred: np.ndarray,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, float]:
        """
        Update step: incorporate observation y_t.

        Kalman gain: K = P C' (C P C' + R)⁻¹
        State update: x̂_{t|t} = x̂_{t|t-1} + K (y_t - C x̂_{t|t-1})
        Covariance update: P_{t|t} = (I - K C) P_{t|t-1}

        Args:
            y: Observation vector
            x_pred: Predicted state
            P_pred: Predicted covariance

        Returns:
            (updated_state, updated_covariance, kalman_gain, log_likelihood)
        """
        # Innovation (observation residual)
        y_pred = self.C @ x_pred
        innovation = y - y_pred

        # Innovation covariance
        S = self.C @ P_pred @ self.C.T + self.R

        # Kalman gain
        try:
            S_inv = np.linalg.inv(S)
            K = P_pred @ self.C.T @ S_inv
        except np.linalg.LinAlgError:
            K = np.zeros((self.n_states, self.n_obs))

        # State update
        x_update = x_pred + K @ innovation

        # Covariance update (Joseph form for numerical stability)
        I_KC = np.eye(self.n_states) - K @ self.C
        P_update = I_KC @ P_pred @ I_KC.T + K @ self.R @ K.T

        # Log-likelihood
        try:
            sign, logdet = np.linalg.slogdet(S)
            ll = -0.5 * (
                self.n_obs * np.log(2 * np.pi)
                + logdet
                + float(innovation.T @ S_inv @ innovation)
            )
        except Exception:
            ll = 0.0

        return x_update, P_update, K, ll

    def filter(
        self,
        observations: np.ndarray,
        controls: Optional[np.ndarray] = None,
        timestamps: Optional[List[datetime]] = None,
    ) -> KalmanFilterResult:
        """
        Run the Kalman filter on a sequence of observations.

        Args:
            observations: Observation matrix (T × n_obs). NaN rows are treated as missing.
            controls: Control input matrix (T × n_controls), optional
            timestamps: List of timestamps, optional

        Returns:
            KalmanFilterResult with filtered states and diagnostics
        """
        T = observations.shape[0]
        self._history = []
        self._total_ll = 0.0

        forecasts = []
        filtered_values = {}

        for t in range(T):
            y_t = observations[t]
            u_t = controls[t] if controls is not None else None
            ts = timestamps[t] if timestamps else datetime.now(timezone.utc)

            # Predict
            x_pred, P_pred = self.predict(u_t)
            forecasts.append(x_pred.copy())

            # Check for missing observations
            valid_mask = ~np.isnan(y_t)
            if np.any(valid_mask):
                # Create observation matrices for valid observations only
                C_valid = self.C[valid_mask]
                R_valid = self.R[np.ix_(valid_mask, valid_mask)]
                y_valid = y_t[valid_mask]

                # Temporarily replace C and R for this step
                C_orig, R_orig = self.C, self.R
                self.C = C_valid
                self.R = R_valid

                x_update, P_update, K, ll = self.update(y_valid, x_pred, P_pred)

                self.C, self.R = C_orig, R_orig
                self._total_ll += ll
            else:
                # No observation — use prediction as update
                x_update = x_pred
                P_update = P_pred
                K = np.zeros((self.n_states, self.n_obs))
                ll = 0.0

            # Store state
            state = KalmanState(
                timestamp=ts,
                state_estimate=x_update.copy(),
                covariance=P_update.copy(),
                innovation=(y_t - self.C @ x_pred) if np.any(valid_mask) else None,
                log_likelihood=ll,
                kalman_gain=K.copy(),
            )
            self._history.append(state)

            # Update internal state
            self.x = x_update
            self.P = P_update

        # Extract filtered values for key states
        if self._history:
            final_state = self._history[-1].state_estimate
            for i, name in enumerate(self._get_state_names()):
                if i < len(final_state):
                    filtered_values[name] = float(final_state[i])

        # One-step-ahead forecast
        x_next, P_next = self.predict()
        forecast = {}
        state_names = self._get_state_names()
        for i, name in enumerate(state_names):
            if i < len(x_next):
                forecast[name] = {
                    "estimate": float(x_next[i]),
                    "std_error": float(np.sqrt(P_next[i, i])),
                    "ci_lower": float(x_next[i] - 1.96 * np.sqrt(P_next[i, i])),
                    "ci_upper": float(x_next[i] + 1.96 * np.sqrt(P_next[i, i])),
                }

        result = KalmanFilterResult(
            filtered_states=self._history,
            smoothed_states=None,
            state_names=state_names,
            forecast=forecast,
            filtered_values=filtered_values,
            log_likelihood=self._total_ll,
            n_observations=T,
        )

        logger.info(
            "kalman_filter_complete",
            n_observations=T,
            log_likelihood=round(self._total_ll, 2),
            final_state={k: round(v, 4) for k, v in filtered_values.items()},
        )

        return result

    def smooth(
        self,
        observations: np.ndarray,
        controls: Optional[np.ndarray] = None,
        timestamps: Optional[List[datetime]] = None,
    ) -> List[KalmanState]:
        """
        Run the Rauch-Tung-Striebel (RTS) smoother.

        The smoother uses both forward (filter) and backward passes
        to compute the optimal state estimate given ALL observations
        (not just past observations as in filtering).

        Smoother equations:
            G_t = P_{t|t} A' P_{t+1|t}⁻¹
            x̂_{t|T} = x̂_{t|t} + G_t (x̂_{t+1|T} - x̂_{t+1|t})
            P_{t|T} = P_{t|t} + G_t (P_{t+1|T} - P_{t+1|t}) G_t'

        Args:
            observations: Observation matrix (T × n_obs)
            controls: Control inputs (optional)
            timestamps: Timestamps (optional)

        Returns:
            List of smoothed KalmanState
        """
        # Forward pass (filter)
        filter_result = self.filter(observations, controls, timestamps)
        filtered = filter_result.filtered_states

        if len(filtered) < 2:
            return filtered

        T = len(filtered)

        # Initialize smoothed states with filtered states
        smoothed = [KalmanState(
            timestamp=s.timestamp,
            state_estimate=s.state_estimate.copy(),
            covariance=s.covariance.copy(),
        ) for s in filtered]

        # Backward pass
        for t in range(T - 2, -1, -1):
            x_t = filtered[t].state_estimate
            P_t = filtered[t].covariance
            x_t1_pred = self.A @ x_t
            P_t1_pred = self.A @ P_t @ self.A.T + self.Q

            # Smoother gain
            try:
                G = P_t @ self.A.T @ np.linalg.inv(P_t1_pred)
            except np.linalg.LinAlgError:
                G = np.zeros_like(P_t)

            # Smoothed state
            x_smooth = x_t + G @ (smoothed[t + 1].state_estimate - x_t1_pred)
            P_smooth = P_t + G @ (smoothed[t + 1].covariance - P_t1_pred) @ G.T

            smoothed[t] = KalmanState(
                timestamp=filtered[t].timestamp,
                state_estimate=x_smooth,
                covariance=P_smooth,
            )

        return smoothed

    def _get_state_names(self) -> List[str]:
        """Get state variable names (generic if not overridden)."""
        return [f"state_{i}" for i in range(self.n_states)]


# ---------------------------------------------------------------------------
# GDP Nowcasting Kalman Filter
# ---------------------------------------------------------------------------

class GDPNowcastingKalmanFilter(KalmanFilter):
    """
    Kalman filter specialized for GDP nowcasting.

    State-space model for mixed-frequency GDP estimation:
    - State: [GDP_trend, GDP_cycle, inflation, employment_index]
    - Observations: daily revenue (→ quarterly GDP), monthly CPI, etc.

    The model bridges daily transaction data to quarterly GDP using
    the Kalman filter's ability to handle mixed-frequency data.

    Model:
        State: x_t = [gdp_level, gdp_growth, cycle, trend]
        x_{t+1} = A x_t + w_t
        y_t = C x_t + v_t

    where:
        - GDP level follows a random walk with drift
        - GDP growth is persistent (AR(1))
        - Cycle follows a damped oscillator
        - Trend is a local linear trend

    Observations:
        - y_1 = daily revenue (high frequency, noisy proxy for GDP)
        - y_2 = monthly price index (medium frequency)
    """

    def __init__(
        self,
        initial_gdp: float = 0.0,
        initial_growth: float = 0.02,
        process_noise: float = 0.01,
        observation_noise_revenue: float = 0.1,
        observation_noise_price: float = 0.05,
    ):
        # State: [gdp_level, gdp_growth, cycle, trend]
        n_states = 4

        # State transition: random walk + growth persistence + cycle
        A = np.array([
            [1.0, 1.0, 0.0, 0.0],   # gdp_level += growth + cycle
            [0.0, 0.8, 0.0, 0.0],   # growth is persistent (AR(1))
            [0.0, 0.0, 0.9, 0.1],   # cycle: damped oscillation
            [0.0, 0.0, -0.1, 0.9],  # cycle: damped oscillation (imaginary part)
        ])

        # Observation: daily revenue maps to GDP level
        C = np.array([
            [1.0, 0.0, 0.5, 0.0],   # revenue ≈ GDP + cycle component
            [0.0, 0.0, 0.0, 0.0],   # price index (unused placeholder)
        ])

        # Process noise
        Q = np.eye(n_states) * process_noise
        Q[0, 0] = process_noise * 2  # GDP level more uncertain

        # Observation noise
        R = np.diag([observation_noise_revenue, observation_noise_price])

        # Initial state
        x0 = np.array([initial_gdp, initial_growth, 0.0, 0.0])

        # Initial covariance (uncertain about level, confident about growth)
        P0 = np.diag([100.0, 0.1, 1.0, 1.0])

        super().__init__(A=A, C=C, Q=Q, R=R, x0=x0, P0=P0)

    def _get_state_names(self) -> List[str]:
        return ["gdp_level", "gdp_growth", "business_cycle", "trend"]

    def nowcast_from_daily_revenue(
        self,
        daily_revenues: np.ndarray,
        price_index: Optional[np.ndarray] = None,
        timestamps: Optional[List[datetime]] = None,
    ) -> KalmanFilterResult:
        """
        Nowcast GDP from daily revenue data.

        Args:
            daily_revenues: Daily revenue series (normalized)
            price_index: Optional monthly price index
            timestamps: Optional timestamps

        Returns:
            KalmanFilterResult with GDP nowcast
        """
        T = len(daily_revenues)

        # Normalize revenue to GDP-scale
        rev_mean = np.nanmean(daily_revenues)
        rev_std = np.nanstd(daily_revenues) or 1.0
        normalized_rev = (daily_revenues - rev_mean) / rev_std

        # Build observation matrix
        observations = np.zeros((T, 2))
        observations[:, 0] = normalized_rev

        if price_index is not None:
            # Price index is lower frequency — fill with NaN for missing
            for t in range(T):
                if t < len(price_index):
                    observations[t, 1] = price_index[t]
                else:
                    observations[t, 1] = np.nan

        # Update observation matrix for revenue-only observations
        self.C = np.array([
            [1.0, 0.0, 0.5, 0.0],
            [0.0, 0.0, 0.0, 0.0],
        ])

        result = self.filter(observations, timestamps=timestamps)

        # Rescale filtered values back to original scale
        if "gdp_level" in result.filtered_values:
            result.filtered_values["gdp_level_raw"] = result.filtered_values["gdp_level"]
            result.filtered_values["gdp_level"] = (
                result.filtered_values["gdp_level"] * rev_std + rev_mean
            )

        return result


# ---------------------------------------------------------------------------
# Economic Indicator Smoother
# ---------------------------------------------------------------------------

class EconomicIndicatorSmoother:
    """
    Kalman smoother for noisy economic indicators.

    Smooths noisy high-frequency indicators (daily revenue, weekly
    employment) into clean trend estimates. Uses the RTS smoother
    for optimal retrospective estimates.

    Use Cases:
    - Smooth daily revenue into weekly/monthly trends
    - Extract trend from noisy inflation data
    - Denoise employment indicators
    - Impute missing economic data

    Usage:
        smoother = EconomicIndicatorSmoother()
        result = smoother.smooth_series(
            noisy_data=daily_revenue,
            indicator_name="daily_revenue",
        )
        trend = result.filtered_values["trend"]
    """

    def __init__(self, process_noise: float = 0.01, observation_noise: float = 0.1):
        self.process_noise = process_noise
        self.observation_noise = observation_noise

    def smooth_series(
        self,
        noisy_data: np.ndarray,
        indicator_name: str = "indicator",
        timestamps: Optional[List[datetime]] = None,
    ) -> KalmanFilterResult:
        """
        Smooth a noisy economic time series.

        Uses a local level model:
            x_{t+1} = x_t + w_t,  w_t ~ N(0, Q)
            y_t = x_t + v_t,      v_t ~ N(0, R)

        Args:
            noisy_data: Noisy observation series
            indicator_name: Name of the indicator
            timestamps: Optional timestamps

        Returns:
            KalmanFilterResult with smoothed trend
        """
        # Local level model
        A = np.array([[1.0]])
        C = np.array([[1.0]])
        Q = np.array([[self.process_noise]])
        R = np.array([[self.observation_noise]])

        kf = KalmanFilter(A=A, C=C, Q=Q, R=R)

        observations = noisy_data.reshape(-1, 1)
        smoothed_states = kf.smooth(observations, timestamps=timestamps)

        # Extract trend
        trend = np.array([s.state_estimate[0] for s in smoothed_states])

        # Build result
        filtered_values = {
            "trend_latest": float(trend[-1]) if len(trend) > 0 else 0.0,
            "trend_mean": float(np.mean(trend)) if len(trend) > 0 else 0.0,
            "noise_reduction_pct": round(
                (1 - np.std(np.diff(trend)) / max(np.std(np.diff(noisy_data)), 1e-10)) * 100, 1
            ),
        }

        forecast = {
            "next_period": {
                "estimate": float(trend[-1]) if len(trend) > 0 else 0.0,
                "std_error": float(np.sqrt(self.process_noise)),
            }
        }

        return KalmanFilterResult(
            filtered_states=kf._history,
            smoothed_states=smoothed_states,
            state_names=["trend"],
            forecast=forecast,
            filtered_values=filtered_values,
            log_likelihood=kf._total_ll,
            n_observations=len(noisy_data),
        )

    def extract_business_cycle(
        self,
        gdp_series: np.ndarray,
        timestamps: Optional[List[datetime]] = None,
    ) -> Dict[str, Any]:
        """
        Extract business cycle component from GDP series.

        Uses a trend-cycle decomposition:
            y_t = trend_t + cycle_t
            trend_{t+1} = trend_t + drift + w_t
            cycle_{t+1} = ρ cos(λ) cycle_t + ρ sin(λ) cycle*_t + ε_t

        Args:
            gdp_series: GDP time series
            timestamps: Optional timestamps

        Returns:
            Dict with trend, cycle, and phase classification
        """
        T = len(gdp_series)

        # State: [trend, cycle_cos, cycle_sin]
        A = np.array([
            [1.0, 0.0, 0.0],    # trend: random walk
            [0.0, 0.95, 0.1],   # cycle: damped oscillation
            [0.0, -0.1, 0.95],  # cycle: damped oscillation
        ])
        C = np.array([[1.0, 1.0, 0.0]])  # observation = trend + cycle
        Q = np.diag([0.01, 0.05, 0.05])
        R = np.array([[0.1]])

        kf = KalmanFilter(A=A, C=C, Q=Q, R=R)
        observations = gdp_series.reshape(-1, 1)
        result = kf.filter(observations, timestamps=timestamps)

        # Extract components
        trend = []
        cycle = []
        for state in kf._history:
            trend.append(float(state.state_estimate[0]))
            cycle.append(float(state.state_estimate[1]))

        trend_arr = np.array(trend)
        cycle_arr = np.array(cycle)

        # Classify business cycle phase
        if len(cycle_arr) >= 2:
            recent_cycle = np.mean(cycle_arr[-3:])
            cycle_trend = cycle_arr[-1] - cycle_arr[-3] if len(cycle_arr) >= 3 else 0

            if recent_cycle > 0 and cycle_trend > 0:
                phase = "expansion"
            elif recent_cycle > 0 and cycle_trend < 0:
                phase = "peak"
            elif recent_cycle < 0 and cycle_trend < 0:
                phase = "contraction"
            elif recent_cycle < 0 and cycle_trend > 0:
                phase = "trough"
            else:
                phase = "indeterminate"
        else:
            phase = "insufficient_data"

        return {
            "trend": trend_arr.tolist(),
            "cycle": cycle_arr.tolist(),
            "phase": phase,
            "current_cycle_value": float(cycle_arr[-1]) if len(cycle_arr) > 0 else 0.0,
            "trend_growth": float(
                (trend_arr[-1] - trend_arr[0]) / max(abs(trend_arr[0]), 1e-10) * 100
            ) if len(trend_arr) > 1 else 0.0,
            "n_observations": T,
        }


# ---------------------------------------------------------------------------
# Factory Functions
# ---------------------------------------------------------------------------

def create_gdp_nowcasting_filter(
    initial_gdp: float = 0.0,
    initial_growth: float = 0.02,
) -> GDPNowcastingKalmanFilter:
    """Create a GDP nowcasting Kalman filter with default parameters."""
    return GDPNowcastingKalmanFilter(
        initial_gdp=initial_gdp,
        initial_growth=initial_growth,
    )


def create_indicator_smoother(
    process_noise: float = 0.01,
    observation_noise: float = 0.1,
) -> EconomicIndicatorSmoother:
    """Create an economic indicator smoother with specified noise levels."""
    return EconomicIndicatorSmoother(
        process_noise=process_noise,
        observation_noise=observation_noise,
    )
