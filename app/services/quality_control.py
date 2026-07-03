"""
Statistical Quality Control — STA 346: Statistical Quality Control.

SPC charts (X-bar, R, p, np), CUSUM, and process capability analysis
for Angavu Intelligence's data pipeline monitoring.

Academic Foundation:
- STA 346: Statistical Quality Control & Acceptance Sampling — Control
  charts for variables (X-bar, R, S) and attributes (p, np, c, u),
  CUSUM and EWMA charts for detecting small shifts, process capability
  indices (Cp, Cpk, Cpm), acceptance sampling plans (single, double,
  multiple), operating characteristic curves

Key Applications:
1. Data pipeline monitoring: SPC charts on transaction volumes
2. Anomaly detection: CUSUM for detecting shifts in data quality
3. Process capability: Is the pipeline meeting quality targets?
4. Acceptance sampling: Validate data quality before publishing

This module is wired into DataPipeline for quality monitoring.
"""

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import structlog

logger = structlog.get_logger(__name__)

# Control chart constants (for subgroup size n)
# Source: Montgomery, D.C. "Introduction to Statistical Quality Control"
A2_VALUES = {2: 1.880, 3: 1.023, 4: 0.729, 5: 0.577, 6: 0.483,
             7: 0.419, 8: 0.373, 9: 0.337, 10: 0.308}
D3_VALUES = {2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0.076, 8: 0.136, 9: 0.184, 10: 0.223}
D4_VALUES = {2: 3.267, 3: 2.574, 4: 2.282, 5: 2.114, 6: 2.004,
             7: 1.924, 8: 1.864, 9: 1.816, 10: 1.777}


class SPCChart:
    """
    Statistical Process Control charts for data quality monitoring.

    Implements STA 346 control chart methods:
    - X-bar chart: Monitor process mean
    - R chart: Monitor process variability
    - p chart: Monitor proportion nonconforming
    - np chart: Monitor number nonconforming
    - CUSUM: Detect small persistent shifts
    - EWMA: Exponentially weighted moving average

    Applied to Angavu Intelligence:
    - X-bar on daily revenue: Detect shifts in business activity
    - p chart on data completeness: Monitor missing data rate
    - CUSUM on transaction volumes: Detect gradual quality degradation
    """

    @staticmethod
    def xbar_chart(
        subgroups: List[np.ndarray],
        sigma_known: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        X-bar control chart for monitoring process mean.

        Center line: X̄̄ = mean of subgroup means
        UCL = X̄̄ + A₂·R̄ (or X̄̄ + 3σ/√n if σ known)
        LCL = X̄̄ - A₂·R̄

        Args:
            subgroups: List of subgroup data arrays
            sigma_known: Known process standard deviation (optional)

        Returns:
            Dict with control limits, center line, out-of-control points
        """
        if not subgroups:
            return {"error": "No subgroups provided"}

        k = len(subgroups)
        n = len(subgroups[0])

        # Subgroup means and ranges
        means = np.array([np.mean(sg) for sg in subgroups])
        ranges = np.array([np.max(sg) - np.min(sg) for sg in subgroups])

        xbar_bar = float(np.mean(means))
        rbar = float(np.mean(ranges))

        # Control limits
        if sigma_known and n in A2_VALUES:
            # Use known sigma
            ucl = xbar_bar + 3 * sigma_known / np.sqrt(n)
            lcl = xbar_bar - 3 * sigma_known / np.sqrt(n)
        elif n in A2_VALUES:
            a2 = A2_VALUES[n]
            ucl = xbar_bar + a2 * rbar
            lcl = xbar_bar - a2 * rbar
        else:
            # Fallback: use sample std
            sigma_est = rbar / 1.128 if n == 2 else rbar / (D4_VALUES.get(n, 3) / 3)
            ucl = xbar_bar + 3 * sigma_est / np.sqrt(n)
            lcl = xbar_bar - 3 * sigma_est / np.sqrt(n)

        # Out-of-control points
        ooc = []
        for i, m in enumerate(means):
            if m > ucl or m < lcl:
                ooc.append({
                    "subgroup": i,
                    "mean": round(float(m), 4),
                    "violation": "above_ucl" if m > ucl else "below_lcl",
                })

        # Runs analysis (8 consecutive points on one side of center)
        runs = SPCChart._detect_runs(means, xbar_bar)

        return {
            "chart_type": "X-bar",
            "center_line": round(xbar_bar, 4),
            "ucl": round(ucl, 4),
            "lcl": round(lcl, 4),
            "subgroup_means": [round(float(m), 4) for m in means],
            "subgroup_ranges": [round(float(r), 4) for r in ranges],
            "out_of_control": ooc,
            "runs": runs,
            "n_subgroups": k,
            "subgroup_size": n,
            "in_control": len(ooc) == 0 and len(runs) == 0,
            "process_sigma": round(float(rbar / 1.128), 4) if n <= 2 else round(float(rbar), 4),
            "method": "STA 346 — X-bar Control Chart",
        }

    @staticmethod
    def r_chart(subgroups: List[np.ndarray]) -> Dict[str, Any]:
        """
        R control chart for monitoring process variability.

        Center line: R̄ = mean of subgroup ranges
        UCL = D₄·R̄
        LCL = D₃·R̄

        Args:
            subgroups: List of subgroup data arrays

        Returns:
            Dict with control limits and out-of-control points
        """
        if not subgroups:
            return {"error": "No subgroups provided"}

        k = len(subgroups)
        n = len(subgroups[0])

        ranges = np.array([np.max(sg) - np.min(sg) for sg in subgroups])
        rbar = float(np.mean(ranges))

        d3 = D3_VALUES.get(n, 0)
        d4 = D4_VALUES.get(n, 3.267)

        ucl = d4 * rbar
        lcl = max(0, d3 * rbar)

        ooc = []
        for i, r in enumerate(ranges):
            if r > ucl or r < lcl:
                ooc.append({"subgroup": i, "range": round(float(r), 4)})

        return {
            "chart_type": "R",
            "center_line": round(rbar, 4),
            "ucl": round(ucl, 4),
            "lcl": round(lcl, 4),
            "subgroup_ranges": [round(float(r), 4) for r in ranges],
            "out_of_control": ooc,
            "in_control": len(ooc) == 0,
            "method": "STA 346 — R Control Chart",
        }

    @staticmethod
    def p_chart(
        defect_counts: np.ndarray,
        sample_sizes: np.ndarray,
    ) -> Dict[str, Any]:
        """
        p control chart for proportion nonconforming.

        Center line: p̄ = total defects / total inspected
        UCL = p̄ + 3√(p̄(1-p̄)/nᵢ)
        LCL = max(0, p̄ - 3√(p̄(1-p̄)/nᵢ))

        Args:
            defect_counts: Number of defects per sample
            sample_sizes: Sample sizes

        Returns:
            Dict with control limits and proportions
        """
        total_defects = np.sum(defect_counts)
        total_inspected = np.sum(sample_sizes)
        pbar = total_defects / max(total_inspected, 1)

        proportions = defect_counts / np.maximum(sample_sizes, 1)

        ucl = np.array([pbar + 3 * np.sqrt(pbar * (1 - pbar) / max(n, 1)) for n in sample_sizes])
        lcl = np.array([max(0, pbar - 3 * np.sqrt(pbar * (1 - pbar) / max(n, 1))) for n in sample_sizes])

        ooc = []
        for i, p in enumerate(proportions):
            if p > ucl[i] or p < lcl[i]:
                ooc.append({"sample": i, "proportion": round(float(p), 4)})

        return {
            "chart_type": "p",
            "center_line": round(float(pbar), 4),
            "ucl": [round(float(u), 4) for u in ucl],
            "lcl": [round(float(l), 4) for l in lcl],
            "proportions": [round(float(p), 4) for p in proportions],
            "out_of_control": ooc,
            "in_control": len(ooc) == 0,
            "method": "STA 346 — p Control Chart",
        }

    @staticmethod
    def cusum_chart(
        data: np.ndarray,
        target: float,
        sigma: float,
        k: float = 0.5,
        h: float = 5.0,
    ) -> Dict[str, Any]:
        """
        CUSUM (Cumulative Sum) chart for detecting small persistent shifts.

        Driven by STA 346 § CUSUM Control Charts:
        Cᵢ⁺ = max(0, xᵢ - (target + k·σ) + Cᵢ₋₁⁺)  (upper CUSUM)
        Cᵢ⁻ = max(0, (target - k·σ) - xᵢ + Cᵢ₋₁⁻)  (lower CUSUM)

        Signal when Cᵢ⁺ > h·σ or Cᵢ⁻ > h·σ

        Args:
            data: Time series data
            target: Target value (process mean)
            sigma: Process standard deviation
            k: Reference value (slack, typically 0.5)
            h: Decision interval (typically 5.0)

        Returns:
            Dict with CUSUM values and signal points
        """
        n = len(data)
        cusum_upper = np.zeros(n)
        cusum_lower = np.zeros(n)

        for i in range(n):
            cusum_upper[i] = max(0, data[i] - (target + k * sigma) + (cusum_upper[i - 1] if i > 0 else 0))
            cusum_lower[i] = max(0, (target - k * sigma) - data[i] + (cusum_lower[i - 1] if i > 0 else 0))

        ucl = h * sigma
        signals_upper = [i for i in range(n) if cusum_upper[i] > ucl]
        signals_lower = [i for i in range(n) if cusum_lower[i] > ucl]

        return {
            "chart_type": "CUSUM",
            "target": target,
            "k": k,
            "h": h,
            "ucl": round(ucl, 4),
            "cusum_upper": [round(float(c), 4) for c in cusum_upper],
            "cusum_lower": [round(float(c), 4) for c in cusum_lower],
            "signals_upper": signals_upper,
            "signals_lower": signals_lower,
            "n_signals": len(signals_upper) + len(signals_lower),
            "in_control": len(signals_upper) == 0 and len(signals_lower) == 0,
            "method": "STA 346 — CUSUM Control Chart",
        }

    @staticmethod
    def process_capability(
        data: np.ndarray,
        usl: float,
        lsl: float,
    ) -> Dict[str, Any]:
        """
        Process capability indices.

        Driven by STA 346 § Process Capability:
        - Cp = (USL - LSL) / 6σ  — potential capability
        - Cpk = min((USL - μ)/3σ, (μ - LSL)/3σ) — actual capability
        - Cpm = Cp / √(1 + ((μ - τ)/σ)²) — Taguchi capability

        Interpretation:
        - Cp > 1.33: Capable process
        - Cp > 1.0: Marginally capable
        - Cp < 1.0: Not capable

        Args:
            data: Process data
            usl: Upper specification limit
            lsl: Lower specification limit

        Returns:
            Dict with capability indices and interpretation
        """
        mu = float(np.mean(data))
        sigma = float(np.std(data, ddof=1))

        if sigma < 1e-10:
            return {"error": "Zero variance — cannot compute capability"}

        cp = (usl - lsl) / (6 * sigma)
        cpk_upper = (usl - mu) / (3 * sigma)
        cpk_lower = (mu - lsl) / (3 * sigma)
        cpk = min(cpk_upper, cpk_lower)

        target = (usl + lsl) / 2
        cpm = cp / np.sqrt(1 + ((mu - target) / sigma) ** 2)

        # Defect rate (PPM)
        z_upper = (usl - mu) / sigma
        z_lower = (mu - lsl) / sigma
        ppm = (1 - sp_stats.norm.cdf(z_upper) + sp_stats.norm.cdf(-z_lower)) * 1e6

        if cpk >= 1.33:
            capability = "capable"
        elif cpk >= 1.0:
            capability = "marginally_capable"
        else:
            capability = "not_capable"

        return {
            "Cp": round(float(cp), 4),
            "Cpk": round(float(cpk), 4),
            "Cpm": round(float(cpm), 4),
            "process_mean": round(mu, 4),
            "process_sigma": round(sigma, 4),
            "usl": usl,
            "lsl": lsl,
            "target": target,
            "estimated_ppm": round(float(ppm), 1),
            "capability": capability,
            "method": "STA 346 — Process Capability Analysis",
        }

    @staticmethod
    def _detect_runs(data: np.ndarray, center: float) -> List[Dict[str, Any]]:
        """Detect runs (8+ consecutive points on one side of center)."""
        runs = []
        current_side = None
        current_start = 0
        current_length = 0

        for i, val in enumerate(data):
            side = "above" if val > center else "below"
            if side == current_side:
                current_length += 1
            else:
                if current_length >= 8:
                    runs.append({
                        "start": current_start,
                        "end": i - 1,
                        "length": current_length,
                        "side": current_side,
                    })
                current_side = side
                current_start = i
                current_length = 1

        if current_length >= 8:
            runs.append({
                "start": current_start,
                "end": len(data) - 1,
                "length": current_length,
                "side": current_side,
            })

        return runs


class DataQualityMonitor:
    """
    Data quality monitoring using SPC methods.

    Applies STA 346 control charts to monitor:
    - Transaction data completeness
    - Revenue data consistency
    - Data pipeline health metrics
    """

    @staticmethod
    def monitor_transaction_quality(
        daily_volumes: np.ndarray,
        daily_completeness: np.ndarray,
    ) -> Dict[str, Any]:
        """
        Monitor transaction data quality using SPC.

        Args:
            daily_volumes: Daily transaction volumes
            daily_completeness: Daily data completeness rates (0-1)

        Returns:
            Dict with quality metrics and control chart results
        """
        results = {}

        # Volume monitoring (X-bar with moving range)
        if len(daily_volumes) >= 20:
            # Use moving range for sigma estimation
            mr = np.abs(np.diff(daily_volumes))
            mr_bar = float(np.mean(mr))
            sigma_est = mr_bar / 1.128

            target = float(np.mean(daily_volumes))
            ucl = target + 3 * sigma_est
            lcl = target - 3 * sigma_est

            ooc_volume = int(np.sum((daily_volumes > ucl) | (daily_volumes < lcl)))

            results["volume_control"] = {
                "target": round(target, 2),
                "ucl": round(ucl, 2),
                "lcl": round(lcl, 2),
                "sigma": round(sigma_est, 2),
                "out_of_control_count": ooc_volume,
                "in_control": ooc_volume == 0,
            }

        # Completeness monitoring (p-chart)
        if len(daily_completeness) >= 10:
            defect_rate = 1 - daily_completeness
            results["completeness_control"] = {
                "avg_completeness": round(float(np.mean(daily_completeness)), 4),
                "avg_defect_rate": round(float(np.mean(defect_rate)), 4),
                "min_completeness": round(float(np.min(daily_completeness)), 4),
                "quality_grade": (
                    "A" if np.mean(daily_completeness) > 0.95
                    else "B" if np.mean(daily_completeness) > 0.90
                    else "C" if np.mean(daily_completeness) > 0.80
                    else "D"
                ),
            }

        # CUSUM on volumes for shift detection
        if len(daily_volumes) >= 20:
            target = float(np.mean(daily_volumes))
            sigma = float(np.std(daily_volumes))
            cusum_result = SPCChart.cusum_chart(daily_volumes, target, sigma)
            results["cusum_shift_detection"] = {
                "in_control": cusum_result["in_control"],
                "n_signals": cusum_result["n_signals"],
            }

        return {
            "quality_report": results,
            "overall_quality": "good" if all(
                v.get("in_control", True) for v in results.values()
                if isinstance(v, dict)
            ) else "needs_attention",
            "method": "STA 346 — Data Quality SPC Monitoring",
        }
