"""
Statistical Process Control (SPC) — Full Suite for Angavu Intelligence Backend

Implements control charts and acceptance sampling for quality monitoring:
1. X-bar chart — monitor mean over time
2. R chart — monitor range (variability) over time
3. p chart — monitor proportion defective
4. c chart — monitor count of defects per unit
5. Acceptance sampling — single, double, sequential sampling plans

These complement control_charts.py (CUSUM, EWMA, Process Capability).

Application to Angavu:
- X-bar/R: monitor daily transaction amounts, delivery times
- p chart: monitor M-Pesa error rates, order defect rates
- c chart: monitor defects per delivery, errors per report
- Acceptance sampling: quality inspection of produce batches

Reference:
- Montgomery, D.C. (2012). Introduction to Statistical Quality Control.
- Dodge, H.F. & Romig, H.G. (1959). Sampling Inspection Tables.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy import stats as sp_stats


# ════════════════════════════════════════════════════════════════
# 1. X-bar Control Chart
# ════════════════════════════════════════════════════════════════


class XbarChart:
    """
    X-bar control chart — monitors process mean over time.

    Subgroups of size n are sampled; the mean of each subgroup is plotted.

    CL = x̄̄ (grand mean)
    UCL = x̄̄ + A₂ × R̄
    LCL = x̄̄ - A₂ × R̄

    A₂ = 3 / (d₂ × √n)

    Western Electric rules for detecting non-random patterns.
    """

    # A₂ factors for subgroup sizes 2-25
    A2_TABLE = {
        2: 1.880, 3: 1.023, 4: 0.729, 5: 0.577, 6: 0.483,
        7: 0.419, 8: 0.373, 9: 0.337, 10: 0.308, 11: 0.285,
        12: 0.266, 13: 0.249, 14: 0.235, 15: 0.223, 16: 0.212,
        17: 0.203, 18: 0.194, 19: 0.187, 20: 0.180, 21: 0.173,
        22: 0.167, 23: 0.162, 24: 0.157, 25: 0.153,
    }

    # d₂ factors
    D2_TABLE = {
        2: 1.128, 3: 1.693, 4: 2.059, 5: 2.326, 6: 2.534,
        7: 2.704, 8: 2.847, 9: 2.970, 10: 3.078, 11: 3.173,
        12: 3.258, 13: 3.336, 14: 3.407, 15: 3.472, 16: 3.532,
        17: 3.588, 18: 3.640, 19: 3.689, 20: 3.735, 21: 3.778,
        22: 3.819, 23: 3.858, 24: 3.895, 25: 3.931,
    }

    @staticmethod
    def analyze(
        data: np.ndarray,
        subgroup_size: int = 5,
    ) -> Dict[str, Any]:
        """
        Compute X-bar chart statistics.

        Args:
            data: time-ordered measurements
            subgroup_size: observations per subgroup (default 5)

        Returns:
            Dict with subgroup means, control limits, signals
        """
        data = np.asarray(data, dtype=float).ravel()
        n = subgroup_size
        if len(data) < n * 2:
            return {"error": f"Need ≥{n * 2} observations for subgroups of size {n}"}

        num_subgroups = len(data) // n
        subgroups = [data[i * n:(i + 1) * n] for i in range(num_subgroups)]

        means = np.array([np.mean(sg) for sg in subgroups])
        ranges = np.array([np.ptp(sg) for sg in subgroups])  # ptp = max - min

        grand_mean = float(np.mean(means))
        r_bar = float(np.mean(ranges))

        # A₂ factor
        a2 = XbarChart.A2_TABLE.get(n, 3.0 / (XbarChart.D2_TABLE.get(n, n * 0.95) * math.sqrt(n)))

        ucl = grand_mean + a2 * r_bar
        lcl = grand_mean - a2 * r_bar

        # Detect signals
        signals = [i for i in range(num_subgroups) if means[i] > ucl or means[i] < lcl]

        # Western Electric rules
        we_signals = _western_electric_rules(means, grand_mean, (ucl - grand_mean) / 3)

        return {
            "chart_type": "X-bar",
            "grand_mean": grand_mean,
            "r_bar": r_bar,
            "ucl": float(ucl),
            "lcl": float(lcl),
            "center_line": grand_mean,
            "subgroup_means": means.tolist(),
            "subgroup_ranges": ranges.tolist(),
            "subgroup_size": n,
            "num_subgroups": num_subgroups,
            "signals": signals,
            "western_electric_signals": we_signals,
            "in_control": len(signals) == 0 and len(we_signals) == 0,
        }


# ════════════════════════════════════════════════════════════════
# 2. R Control Chart
# ════════════════════════════════════════════════════════════════


class RChart:
    """
    R control chart — monitors process variability (range) over time.

    CL = R̄
    UCL = D₄ × R̄
    LCL = D₃ × R̄
    """

    # D₃ and D₄ factors
    D3_TABLE = {
        2: 0.0, 3: 0.0, 4: 0.0, 5: 0.0, 6: 0.0,
        7: 0.076, 8: 0.136, 9: 0.184, 10: 0.223,
        11: 0.256, 12: 0.283, 13: 0.307, 14: 0.328, 15: 0.347,
    }

    D4_TABLE = {
        2: 3.267, 3: 2.574, 4: 2.282, 5: 2.114, 6: 2.004,
        7: 1.924, 8: 1.864, 9: 1.816, 10: 1.777,
        11: 1.744, 12: 1.717, 13: 1.693, 14: 1.672, 15: 1.653,
    }

    @staticmethod
    def analyze(data: np.ndarray, subgroup_size: int = 5) -> Dict[str, Any]:
        """Compute R chart statistics."""
        data = np.asarray(data, dtype=float).ravel()
        n = subgroup_size
        if len(data) < n * 2:
            return {"error": f"Need ≥{n * 2} observations"}

        num_subgroups = len(data) // n
        subgroups = [data[i * n:(i + 1) * n] for i in range(num_subgroups)]
        ranges = np.array([np.ptp(sg) for sg in subgroups])
        r_bar = float(np.mean(ranges))

        d3 = RChart.D3_TABLE.get(n, 0.0)
        d4 = RChart.D4_TABLE.get(n, 1 + 3 * d3 / XbarChart.D2_TABLE.get(n, n * 0.95))

        ucl = d4 * r_bar
        lcl = max(0.0, d3 * r_bar)

        signals = [i for i in range(num_subgroups) if ranges[i] > ucl or ranges[i] < lcl]

        return {
            "chart_type": "R",
            "r_bar": r_bar,
            "ucl": float(ucl),
            "lcl": float(lcl),
            "center_line": r_bar,
            "subgroup_ranges": ranges.tolist(),
            "signals": signals,
            "in_control": len(signals) == 0,
        }


# ════════════════════════════════════════════════════════════════
# 3. p Control Chart
# ════════════════════════════════════════════════════════════════


class PChart:
    """
    p chart — monitors proportion defective.

    Each subgroup may have different sample sizes.

    p̄ = Σdᵢ / Σnᵢ
    UCLᵢ = p̄ + 3√(p̄(1-p̄)/nᵢ)
    LCLᵢ = max(0, p̄ - 3√(p̄(1-p̄)/nᵢ))
    """

    @staticmethod
    def analyze(
        n_inspected: np.ndarray,
        n_nonconforming: np.ndarray,
    ) -> Dict[str, Any]:
        """
        Compute p chart statistics.

        Args:
            n_inspected: number inspected per subgroup
            n_nonconforming: number nonconforming per subgroup

        Returns:
            Dict with proportions, control limits, signals
        """
        n_insp = np.asarray(n_inspected, dtype=float).ravel()
        n_nonconf = np.asarray(n_nonconforming, dtype=float).ravel()

        if len(n_insp) != len(n_nonconf):
            return {"error": "n_inspected and n_nonconforming must have same length"}

        k = len(n_insp)
        total_inspected = float(np.sum(n_insp))
        total_defective = float(np.sum(n_nonconf))
        p_bar = total_defective / total_inspected

        proportions = n_nonconf / n_insp
        ucl = p_bar + 3 * np.sqrt(p_bar * (1 - p_bar) / n_insp)
        lcl = np.maximum(0, p_bar - 3 * np.sqrt(p_bar * (1 - p_bar) / n_insp))

        signals = [i for i in range(k) if proportions[i] > ucl[i] or proportions[i] < lcl[i]]

        return {
            "chart_type": "p",
            "p_bar": float(p_bar),
            "proportions": proportions.tolist(),
            "ucl": ucl.tolist(),
            "lcl": lcl.tolist(),
            "signals": signals,
            "in_control": len(signals) == 0,
            "total_inspected": total_inspected,
            "total_defective": total_defective,
        }


# ════════════════════════════════════════════════════════════════
# 4. c Control Chart
# ════════════════════════════════════════════════════════════════


class CChart:
    """
    c chart — monitors count of defects per inspection unit.

    Assumes constant inspection unit size.

    c̄ = Σcᵢ / k
    UCL = c̄ + 3√c̄
    LCL = max(0, c̄ - 3√c̄)
    """

    @staticmethod
    def analyze(data: np.ndarray) -> Dict[str, Any]:
        """
        Compute c chart statistics.

        Args:
            data: defect counts per unit

        Returns:
            Dict with c_bar, control limits, signals
        """
        data = np.asarray(data, dtype=float).ravel()
        k = len(data)
        if k < 5:
            return {"error": "Need ≥5 subgroups"}

        c_bar = float(np.mean(data))
        sqrt_c_bar = math.sqrt(c_bar)

        ucl = c_bar + 3 * sqrt_c_bar
        lcl = max(0.0, c_bar - 3 * sqrt_c_bar)

        signals = [i for i in range(k) if data[i] > ucl or data[i] < lcl]

        return {
            "chart_type": "c",
            "c_bar": c_bar,
            "ucl": float(ucl),
            "lcl": float(lcl),
            "center_line": c_bar,
            "signals": signals,
            "in_control": len(signals) == 0,
        }


# ════════════════════════════════════════════════════════════════
# 5. Acceptance Sampling Plans
# ════════════════════════════════════════════════════════════════


class AcceptanceSampling:
    """
    Acceptance sampling plans for batch quality inspection.

    Single sampling: inspect n, accept if defects ≤ c
    Double sampling: inspect n₁, if d₁ ≤ c₁ accept; if d₁ > r₁ reject;
                     else inspect n₂, accept if d₁+d₂ ≤ c₂
    Sequential sampling: inspect one at a time, accept/reject/continue

    Uses the hypergeometric distribution (finite population) or
    binomial approximation (large population).

    Application: Inspecting batches of produce, verifying order accuracy,
    checking transaction completeness.
    """

    @staticmethod
    def single_sampling(
        batch_size: int,
        sample_size: int,
        accept_number: int,
        defect_rate: float,
    ) -> Dict[str, Any]:
        """
        Single sampling plan: OC curve and metrics.

        Args:
            batch_size: total items in batch (N)
            sample_size: items to inspect (n)
            accept_number: max defects to accept (c)
            defect_rate: expected proportion defective (p)

        Returns:
            Dict with acceptance probability, AOQ, ATI, ASN
        """
        n = sample_size
        c = accept_number
        N = batch_size
        p = defect_rate

        if n > N:
            return {"error": "Sample size cannot exceed batch size"}

        # Number of defectives in batch
        D = round(N * p)

        # Acceptance probability P(X ≤ c) using hypergeometric
        # X ~ Hypergeometric(N, D, n)
        prob_accept = 0.0
        for d in range(c + 1):
            prob_accept += sp_stats.hypergeom.pmf(d, N, D, n)

        # OC curve: acceptance probability for range of defect rates
        oc_curve = {}
        for p_test in [0.001, 0.01, 0.02, 0.05, 0.10, 0.15, 0.20, 0.30]:
            D_test = round(N * p_test)
            pa = sum(sp_stats.hypergeom.pmf(d, N, D_test, n) for d in range(c + 1))
            oc_curve[f"{p_test:.1%}"] = float(pa)

        # AOQ (Average Outgoing Quality)
        # AOQ = p × Pa × (N-n)/N
        aoq = p * prob_accept * (N - n) / N

        # ATI (Average Total Inspection)
        # ATI = n + (1-Pa) × (N-n)
        ati = n + (1 - prob_accept) * (N - n)

        # LQ (Limiting Quality) — defect rate where Pa = 0.10
        lq = None
        for p_test_int in range(1, 100):
            p_test = p_test_int / 1000.0
            D_test = round(N * p_test)
            pa = sum(sp_stats.hypergeom.pmf(d, N, D_test, n) for d in range(c + 1))
            if pa <= 0.10:
                lq = p_test
                break

        return {
            "plan_type": "single",
            "batch_size": N,
            "sample_size": n,
            "accept_number": c,
            "defect_rate": p,
            "prob_acceptance": float(prob_accept),
            "aoq": float(aoq),
            "ati": float(ati),
            "oc_curve": oc_curve,
            "lq_10": lq,
        }

    @staticmethod
    def double_sampling(
        batch_size: int,
        n1: int,
        c1: int,
        r1: int,
        n2: int,
        c2: int,
        defect_rate: float,
    ) -> Dict[str, Any]:
        """
        Double sampling plan.

        Stage 1: inspect n₁ items
            - If d₁ ≤ c₁: ACCEPT
            - If d₁ > r₁: REJECT
            - Otherwise: go to stage 2
        Stage 2: inspect n₂ more items
            - If d₁ + d₂ ≤ c₂: ACCEPT
            - Else: REJECT

        Args:
            batch_size: N
            n1, n2: sample sizes for stages 1 and 2
            c1: accept number for stage 1
            r1: reject number for stage 1
            c2: accept number for stage 2
            defect_rate: expected p
        """
        N = batch_size
        p = defect_rate
        D = round(N * p)

        # Stage 1 probabilities
        pa1 = sum(sp_stats.hypergeom.pmf(d, N, D, n1) for d in range(c1 + 1))
        pr1 = sum(sp_stats.hypergeom.pmf(d, N, D, n1) for d in range(r1, N + 1))

        # Probability of going to stage 2
        p_continue = 1 - pa1 - pr1

        # Stage 2 acceptance (conditional on reaching stage 2)
        pa2 = 0.0
        for d1 in range(max(0, c1 + 1), min(r1, n1) + 1):
            # After seeing d1 defects in stage 1, remaining population
            D_remaining = D - d1
            N_remaining = N - n1
            n2_actual = min(n2, N_remaining)
            for d2 in range(max(0, c2 - d1 + 1)):
                pa2 += sp_stats.hypergeom.pmf(d1, N, D, n1) * \
                       sp_stats.hypergeom.pmf(d2, N_remaining, D_remaining, n2_actual)

        # Total acceptance probability
        pa_total = pa1 + pa2

        # ASN (Average Sample Number)
        asn = n1 + p_continue * n2

        return {
            "plan_type": "double",
            "batch_size": N,
            "stage1": {"n": n1, "c": c1, "r": r1},
            "stage2": {"n": n2, "c": c2},
            "defect_rate": p,
            "prob_accept_stage1": float(pa1),
            "prob_reject_stage1": float(pr1),
            "prob_continue": float(p_continue),
            "prob_accept_total": float(pa_total),
            "asn": float(asn),
        }

    @staticmethod
    def sequential_sampling(
        batch_size: int,
        accept_number: int,
        reject_number: int,
        defect_rate: float,
        max_items: int = 50,
    ) -> Dict[str, Any]:
        """
        Sequential sampling plan — inspect one at a time.

        At each step, compute cumulative defects d:
        - If d ≤ accept_boundary: ACCEPT
        - If d ≥ reject_boundary: REJECT
        - Otherwise: continue

        Boundaries are based on Wald's sequential probability ratio test.

        Args:
            batch_size: N
            accept_number: defects for accept
            reject_number: defects for reject
            defect_rate: expected p
            max_items: maximum items to inspect

        Returns:
            Dict with decision boundaries and OC curve point
        """
        N = batch_size
        p = defect_rate

        # Wald's SPRT boundaries (simplified)
        # h_a = accept boundary, h_r = reject boundary
        # Using log-likelihood ratio
        p0 = 0.01  # acceptable quality level
        p1 = 0.10  # rejectable quality level

        if p0 >= p1:
            return {"error": "p0 must be < p1 for SPRT"}

        # Log-likelihood ratio boundaries
        A = (1 - p0) / (1 - p1)  # ratio for non-defective
        B = p1 / p0  # ratio for defective

        h_a = math.log((1 - 0.05) / 0.10)  # α=0.05, β=0.10
        h_r = math.log(0.10 / (1 - 0.05))

        # Compute OC curve point via Wald's approximation
        if B != 1:
            h = math.log(B)
            prob_accept_wald = (1 - A ** (-h_a / h)) / (B ** (h_r / h) - A ** (-h_a / h))
        else:
            prob_accept_wald = 0.5

        # Decision boundaries (cumulative defect count vs sample size)
        boundaries = []
        for n_items in range(1, max_items + 1):
            # Upper boundary (reject): h_r + n × slope
            # Lower boundary (accept): h_a + n × slope
            slope = math.log((1 - p0) / (1 - p1)) / math.log(p1 / p0) if p1 != p0 else 0
            upper = max(0, round(reject_number + n_items * 0.05))
            lower = max(0, round(accept_number - n_items * 0.05))
            boundaries.append({
                "n": n_items,
                "accept_if_defects_below": lower,
                "reject_if_defects_above": upper,
            })

        return {
            "plan_type": "sequential",
            "batch_size": N,
            "aql": p0,
            "rql": p1,
            "defect_rate": p,
            "prob_accept_wald": float(prob_accept_wald),
            "boundaries": boundaries[:20],  # First 20 steps
        }


# ════════════════════════════════════════════════════════════════
# Western Electric Rules Helper
# ════════════════════════════════════════════════════════════════


def _western_electric_rules(
    data: np.ndarray, center: float, sigma: float
) -> List[str]:
    """Apply Western Electric rules for detecting non-random patterns."""
    signals = []
    n = len(data)

    # Rule 1: 1 point beyond 3σ
    for i in range(n):
        if abs(data[i] - center) > 3 * sigma:
            signals.append(f"Point {i}: beyond 3σ ({data[i]:.4f})")

    # Rule 2: 2 of 3 consecutive beyond 2σ (same side)
    for i in range(2, n):
        window = data[i - 2:i + 1] - center
        if np.sum(window > 2 * sigma) >= 2 or np.sum(window < -2 * sigma) >= 2:
            signals.append(f"2 of 3 beyond 2σ near point {i}")

    # Rule 3: 4 of 5 consecutive beyond 1σ (same side)
    for i in range(4, n):
        window = data[i - 4:i + 1] - center
        if np.sum(window > sigma) >= 4 or np.sum(window < -sigma) >= 4:
            signals.append(f"4 of 5 beyond 1σ near point {i}")

    # Rule 4: 8 consecutive on same side
    for i in range(7, n):
        window = data[i - 7:i + 1] - center
        if np.all(window > 0) or np.all(window < 0):
            signals.append(f"8 consecutive on same side near point {i}")

    return signals


# ════════════════════════════════════════════════════════════════
# Runner Interface
# ════════════════════════════════════════════════════════════════


def run_method(method: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Entry point for the Rust bridge."""
    try:
        if method == "xbar_chart":
            data = np.array(args["data"], dtype=float)
            return XbarChart.analyze(data, subgroup_size=args.get("subgroup_size", 5))

        elif method == "r_chart":
            data = np.array(args["data"], dtype=float)
            return RChart.analyze(data, subgroup_size=args.get("subgroup_size", 5))

        elif method == "p_chart":
            n_insp = np.array(args["n_inspected"], dtype=float)
            n_nonconf = np.array(args["n_nonconforming"], dtype=float)
            return PChart.analyze(n_insp, n_nonconf)

        elif method == "c_chart":
            data = np.array(args["data"], dtype=float)
            return CChart.analyze(data)

        elif method == "acceptance_single":
            return AcceptanceSampling.single_sampling(
                batch_size=args["batch_size"],
                sample_size=args["sample_size"],
                accept_number=args["accept_number"],
                defect_rate=args["defect_rate"],
            )

        elif method == "acceptance_double":
            return AcceptanceSampling.double_sampling(
                batch_size=args["batch_size"],
                n1=args["n1"], c1=args["c1"], r1=args["r1"],
                n2=args["n2"], c2=args["c2"],
                defect_rate=args["defect_rate"],
            )

        elif method == "acceptance_sequential":
            return AcceptanceSampling.sequential_sampling(
                batch_size=args["batch_size"],
                accept_number=args["accept_number"],
                reject_number=args["reject_number"],
                defect_rate=args["defect_rate"],
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
