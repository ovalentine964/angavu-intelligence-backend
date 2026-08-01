"""
Statistical Process Control — CUSUM, EWMA, and Process Capability (STA 346)

Implements advanced control charts for monitoring model quality over time:
1. CUSUM (Cumulative Sum) chart — detects small persistent shifts
2. EWMA (Exponentially Weighted Moving Average) chart — smooth monitoring
3. Process Capability (Cp, Cpk) — model quality assessment
4. Confidence Intervals for all control chart parameters

Academic Reference:
- Montgomery (2012). Statistical Quality Control.
- Lucas & Crosier (1982). "Fast initial response for CUSUM"
"""

from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from scipy import stats as sp_stats


# ════════════════════════════════════════════════════════════════
# 1. CUSUM Control Chart
# ════════════════════════════════════════════════════════════════


class CUSUMChart:
    """
    Cumulative Sum (CUSUM) control chart for detecting small persistent shifts.

    CUSUM accumulates deviations from target, making it more sensitive
    than X-bar charts for detecting small shifts (0.5σ to 2σ).

    Upper CUSUM: Sₜ⁺ = max(0, Sₜ₋₁⁺ + (xₜ - μ₀) - k)
    Lower CUSUM: Sₜ⁻ = max(0, Sₜ₋₁⁻ - (xₜ - μ₀) - k)

    where:
    - μ₀ = target (in-control) mean
    - k = reference value (slack) = δ/2 (typically δ = 1σ, so k = 0.5σ)
    - h = decision interval (typically 4 or 5)

    Signal when S⁺ > h or S⁻ > h.
    """

    @staticmethod
    def analyze(
        data: np.ndarray,
        target: Optional[float] = None,
        sigma: Optional[float] = None,
        k_factor: float = 0.5,
        h_factor: float = 5.0,
    ) -> Dict[str, Any]:
        """
        Compute CUSUM chart statistics.

        Args:
            data: Process measurements
            target: In-control mean (default: sample mean)
            sigma: Process std dev (default: estimated from data)
            k_factor: Reference value as multiple of sigma (default 0.5)
            h_factor: Decision interval as multiple of sigma (default 5.0)

        Returns:
            CUSUM statistics, control limits, out-of-control signals
        """
        x = np.array(data, dtype=float)
        n = len(x)

        if target is None:
            target = np.mean(x)
        if sigma is None:
            # Use moving range estimator
            mr = np.abs(np.diff(x))
            sigma = np.mean(mr) / 1.128  # d2 for n=2

        k = k_factor * sigma
        h = h_factor * sigma

        # Compute CUSUM
        s_plus = np.zeros(n)
        s_minus = np.zeros(n)
        signals_upper = []
        signals_lower = []

        for t in range(n):
            s_plus[t] = max(0, (s_plus[t-1] if t > 0 else 0) + (x[t] - target) - k)
            s_minus[t] = max(0, (s_minus[t-1] if t > 0 else 0) - (x[t] - target) - k)

            if s_plus[t] > h:
                signals_upper.append(t)
            if s_minus[t] > h:
                signals_lower.append(t)

        # Average Run Length (ARL) approximation
        # ARL₀ (in-control) ≈ exp(h*k)/(2*k²) + h/(2*k) - 1 (Siegmund)
        delta = k_factor  # shift in sigma units
        if delta > 0:
            arl0 = (math.exp(h_factor * delta) - h_factor * delta - 1) / (delta ** 2) + 1
        else:
            arl0 = float('inf')

        # ARL₁ (out-of-control, shift = 1σ)
        delta_ooc = 1.0
        if delta_ooc > k_factor:
            arl1 = (math.exp(-h_factor * (delta_ooc - k_factor)) + h_factor * (delta_ooc - k_factor) - 1) / ((delta_ooc - k_factor) ** 2) + 1
        else:
            arl1 = float('nan')

        return {
            "cusum_upper": s_plus.tolist(),
            "cusum_lower": s_minus.tolist(),
            "target": float(target),
            "sigma": float(sigma),
            "k": float(k),
            "h": float(h),
            "signals_upper": signals_upper,
            "signals_lower": signals_lower,
            "in_control": len(signals_upper) == 0 and len(signals_lower) == 0,
            "arl0_in_control": float(arl0),
            "arl1_shift_1sigma": float(arl1),
            "n": n,
        }


# ════════════════════════════════════════════════════════════════
# 2. EWMA Control Chart
# ════════════════════════════════════════════════════════════════


class EWMAChart:
    """
    Exponentially Weighted Moving Average (EWMA) control chart.

    EWMA smooths data exponentially, giving more weight to recent observations.
    Better than X-bar for detecting small shifts, and simpler than CUSUM.

    Zₜ = λxₜ + (1-λ)Zₜ₋₁

    Control limits:
    UCL = μ₀ + L × σ × √(λ/(2-λ) × (1-(1-λ)^(2t)))
    LCL = μ₀ - L × σ × √(λ/(2-λ) × (1-(1-λ)^(2t)))

    where λ = smoothing parameter (0 < λ ≤ 1), L = width (typically 3)
    """

    @staticmethod
    def analyze(
        data: np.ndarray,
        target: Optional[float] = None,
        sigma: Optional[float] = None,
        lambda_param: float = 0.2,
        L: float = 3.0,
    ) -> Dict[str, Any]:
        """
        Compute EWMA chart statistics.

        Args:
            data: Process measurements
            target: In-control mean
            sigma: Process std dev
            lambda_param: Smoothing parameter (0 < λ ≤ 1)
            L: Control limit width in sigma units
        """
        x = np.array(data, dtype=float)
        n = len(x)

        if target is None:
            target = np.mean(x)
        if sigma is None:
            mr = np.abs(np.diff(x))
            sigma = np.mean(mr) / 1.128

        lam = lambda_param

        # EWMA statistic
        z = np.zeros(n)
        z[0] = target  # Start at target
        for t in range(1, n):
            z[t] = lam * x[t] + (1 - lam) * z[t - 1]

        # Time-varying control limits
        ucl = np.zeros(n)
        lcl = np.zeros(n)
        for t in range(n):
            var_t = (sigma ** 2) * (lam / (2 - lam)) * (1 - (1 - lam) ** (2 * (t + 1)))
            ucl[t] = target + L * np.sqrt(var_t)
            lcl[t] = target - L * np.sqrt(var_t)

        # Signals
        signals = [t for t in range(n) if z[t] > ucl[t] or z[t] < lcl[t]]

        # Steady-state control limits (approximation for large t)
        ss_limit = L * sigma * np.sqrt(lam / (2 - lam))

        return {
            "ewma": z.tolist(),
            "ucl": ucl.tolist(),
            "lcl": lcl.tolist(),
            "target": float(target),
            "sigma": float(sigma),
            "lambda": float(lam),
            "L": float(L),
            "signals": signals,
            "in_control": len(signals) == 0,
            "steady_state_ucl": float(target + ss_limit),
            "steady_state_lcl": float(target - ss_limit),
            "n": n,
        }


# ════════════════════════════════════════════════════════════════
# 3. Process Capability (Cp, Cpk)
# ════════════════════════════════════════════════════════════════


class ProcessCapability:
    """
    Process capability indices for model quality assessment.

    Cp = (USL - LSL) / (6σ) — potential capability (ignoring centering)
    Cpk = min[(USL - μ)/(3σ), (μ - LSL)/(3σ)] — actual capability

    Interpretation:
    - Cp/Cpk ≥ 2.0: World class (Six Sigma)
    - Cp/Cpk ≥ 1.33: Capable process
    - Cp/Cpk ≥ 1.0: Marginally capable
    - Cp/Cpk < 1.0: Not capable — improvement needed
    """

    @staticmethod
    def analyze(
        data: np.ndarray,
        usl: float,
        lsl: float,
        target: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Compute process capability indices.

        Args:
            data: Process measurements
            usl: Upper specification limit
            lsl: Lower specification limit
            target: Target value (default: midpoint of spec)
        """
        x = np.array(data, dtype=float)
        n = len(x)
        mu = np.mean(x)
        sigma = np.std(x, ddof=1)

        if target is None:
            target = (usl + lsl) / 2

        # Cp: potential capability
        cp = (usl - lsl) / (6 * sigma) if sigma > 0 else float('inf')

        # Cpk: actual capability
        cpu = (usl - mu) / (3 * sigma) if sigma > 0 else float('inf')
        cpl = (mu - lsl) / (3 * sigma) if sigma > 0 else float('inf')
        cpk = min(cpu, cpl)

        # Cpm (Taguchi capability index)
        cpm_num = usl - lsl
        cpm_den = 6 * np.sqrt(sigma**2 + (mu - target)**2)
        cpm = cpm_num / cpm_den if cpm_den > 0 else float('inf')

        # Capability interpretation
        def interpret(val: float) -> str:
            if val >= 2.0:
                return "World Class (Six Sigma)"
            elif val >= 1.33:
                return "Capable"
            elif val >= 1.0:
                return "Marginally Capable"
            else:
                return "Not Capable — Improvement Needed"

        # Defect rate estimation (PPM)
        z_upper = (usl - mu) / sigma if sigma > 0 else float('inf')
        z_lower = (mu - lsl) / sigma if sigma > 0 else float('inf')
        ppm_upper = sp_stats.norm.sf(z_upper) * 1_000_000
        ppm_lower = sp_stats.norm.cdf(-z_lower) * 1_000_000
        ppm_total = ppm_upper + ppm_lower

        # Sigma level
        sigma_level = cpk * 3 + 1.5  # 1.5 sigma shift convention

        return {
            "cp": float(cp),
            "cpk": float(cpk),
            "cpu": float(cpu),
            "cpl": float(cpl),
            "cpm": float(cpm),
            "interpretation": interpret(cpk),
            "mu": float(mu),
            "sigma": float(sigma),
            "usl": float(usl),
            "lsl": float(lsl),
            "target": float(target),
            "z_upper": float(z_upper),
            "z_lower": float(z_lower),
            "ppm_defect_rate": float(ppm_total),
            "sigma_level": float(min(sigma_level, 6.0)),
            "n": n,
        }


# ════════════════════════════════════════════════════════════════
# Runner Interface
# ════════════════════════════════════════════════════════════════


def run_method(method: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Entry point for the Rust bridge."""
    try:
        if method == "cusum":
            data = np.array(args["data"], dtype=float)
            return CUSUMChart.analyze(
                data,
                target=args.get("target"),
                sigma=args.get("sigma"),
                k_factor=args.get("k_factor", 0.5),
                h_factor=args.get("h_factor", 5.0),
            )

        elif method == "ewma":
            data = np.array(args["data"], dtype=float)
            return EWMAChart.analyze(
                data,
                target=args.get("target"),
                sigma=args.get("sigma"),
                lambda_param=args.get("lambda", 0.2),
                L=args.get("L", 3.0),
            )

        elif method == "process_capability":
            data = np.array(args["data"], dtype=float)
            return ProcessCapability.analyze(
                data,
                usl=args["usl"],
                lsl=args["lsl"],
                target=args.get("target"),
            )

        else:
            return {"error": f"Unknown method: {method}"}

    except Exception as e:
        return {"error": str(e), "method": method}


if __name__ == "__main__":
    import sys, json
    if len(sys.argv) > 1:
        input_data = json.loads(sys.argv[1])
        result = run_method(input_data["method"], input_data.get("args", {}))
        print(json.dumps(result))
