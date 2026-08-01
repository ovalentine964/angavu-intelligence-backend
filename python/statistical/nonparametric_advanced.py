"""
Advanced Non-Parametric Methods for Angavu Intelligence Backend

Implements additional distribution-free methods:

1. Sign Test — simplest non-parametric test for median
2. Runs Test (Wald-Wolfowitz) — randomness/serial independence
3. Mood's Median Test — compare medians across k groups
4. Non-parametric Confidence Intervals — bootstrap-based (percentile, BCa, tilting)
5. Non-parametric Effect Sizes — Cliff's delta, rank-biserial correlation, Vargha-Delaney A

These complement the existing nonparametric.py (KDE, Mann-Whitney, Kruskal-Wallis,
Bootstrap, Permutation) and nonparametric_extended.py (Friedman, KS, AD, LOESS).

Application to Angavu:
- Sign test: robust median comparison when outliers dominate
- Runs test: detect non-random patterns in transaction sequences
- Mood's median: compare medians across worker types (robust to outliers)
- Non-parametric CIs: accurate inference for Gini, Theil, skewed financial stats
- Effect sizes: quantify practical significance beyond p-values

Reference:
- Conover, W.J. (1999). Practical Nonparametric Statistics.
- Cliff, N. (1993). Dominance Statistics.
- Vargha, A. & Delaney, H.D. (2000). The Critique and Comparison of Tests.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import numpy as np
from scipy import stats as sp_stats


# ════════════════════════════════════════════════════════════════
# 1. Sign Test
# ════════════════════════════════════════════════════════════════


class SignTest:
    """
    Sign Test — simplest non-parametric test for median.

    Tests H₀: median = hypothesized value (one-sample) or
    H₀: median difference = 0 (paired samples).

    Only uses the sign of differences, not magnitude — most robust test.
    B ~ Binomial(n, 0.5) under H₀.

    Why use it:
    - When outliers dominate (M-Pesa transactions with fraud spikes)
    - When only ordinal information available
    - When Wilcoxon assumptions (symmetry) are violated
    """

    @staticmethod
    def one_sample(
        data: np.ndarray,
        hypothesized_median: float = 0.0,
        alternative: str = "two-sided",
    ) -> Dict[str, Any]:
        """
        One-sample sign test.

        Args:
            data: observed sample
            hypothesized_median: H₀ value for median
            alternative: 'two-sided', 'less', 'greater'

        Returns:
            Dict with test statistic, p-value, CI
        """
        data = np.asarray(data, dtype=float).ravel()
        diffs = data[data != hypothesized_median] - hypothesized_median
        n = len(diffs)
        if n < 5:
            return {"error": "Need ≥5 non-zero observations", "test_name": "Sign test"}

        n_plus = int(np.sum(diffs > 0))
        n_minus = n - n_plus
        b = min(n_plus, n_minus)

        # Normal approximation for large n
        expected = n / 2.0
        variance = n / 4.0
        z = (b - expected) / math.sqrt(variance) if variance > 0 else 0.0

        # Two-sided p-value
        if alternative == "two-sided":
            p_value = 2 * sp_stats.norm.cdf(-abs(z))
        elif alternative == "greater":
            p_value = sp_stats.norm.cdf(z)
        else:
            p_value = 1 - sp_stats.norm.cdf(z)

        # Exact binomial p-value for small samples
        exact_p = None
        if n <= 30:
            if alternative == "two-sided":
                exact_p = _binomial_two_sided_p(b, n, 0.5)
            elif alternative == "greater":
                exact_p = 1 - sp_stats.binom.cdf(n_plus - 1, n, 0.5)
            else:
                exact_p = sp_stats.binom.cdf(n_plus, n, 0.5)

        # Exact binomial CI for the median (via sign test inversion)
        # Not computed here — use BootstrapInference instead

        return {
            "test_name": "Sign test",
            "n_positive": n_plus,
            "n_negative": n_minus,
            "n_effective": n,
            "b_statistic": int(b),
            "z_score": float(z),
            "p_value": float(p_value),
            "p_value_exact": float(exact_p) if exact_p is not None else None,
            "significant_at_05": p_value < 0.05,
            "alternative": alternative,
        }

    @staticmethod
    def paired(
        sample1: np.ndarray,
        sample2: np.ndarray,
        alternative: str = "two-sided",
    ) -> Dict[str, Any]:
        """
        Paired sign test: test median difference = 0.

        Args:
            sample1, sample2: paired observations
            alternative: 'two-sided', 'less', 'greater'

        Returns:
            Dict with test results
        """
        sample1 = np.asarray(sample1, dtype=float).ravel()
        sample2 = np.asarray(sample2, dtype=float).ravel()
        if len(sample1) != len(sample2):
            return {"error": "Samples must have equal length"}

        diffs = sample1 - sample2
        result = SignTest.one_sample(diffs, 0.0, alternative)
        result["test_name"] = "Paired sign test"
        result["median_difference"] = float(np.median(diffs))
        return result


# ════════════════════════════════════════════════════════════════
# 2. Runs Test (Wald-Wolfowitz)
# ════════════════════════════════════════════════════════════════


class RunsTest:
    """
    Wald-Wolfowitz Runs Test — test for randomness / serial independence.

    Tests H₀: the sequence is random (independent observations).

    A "run" is a maximal sequence of consecutive same-type elements.
    Too few runs → trend/periodicity; too many runs → oscillation.

    Why use it:
    - Detect non-random patterns in daily transaction counts
    - Test if income data shows temporal clustering
    - Verify that time series residuals are independent
    """

    @staticmethod
    def test(
        data: np.ndarray,
        cutoff: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Runs test for randomness.

        Args:
            data: 1D sequence of observations
            cutoff: threshold (default: median). Values ≥ cutoff are "above".

        Returns:
            Dict with runs count, z-score, p-value
        """
        data = np.asarray(data, dtype=float).ravel()
        n = len(data)
        if n < 10:
            return {"error": "Need ≥10 observations", "test_name": "Runs test"}

        if cutoff is None:
            cutoff = float(np.median(data))

        # Convert to binary sequence
        binary = (data >= cutoff).astype(int)

        # Count runs
        runs = 1
        for i in range(1, n):
            if binary[i] != binary[i - 1]:
                runs += 1

        n1 = int(np.sum(binary == 1))
        n0 = n - n1

        if n1 == 0 or n0 == 0:
            return {
                "test_name": "Runs test",
                "error": "All values on same side of cutoff — no runs possible",
            }

        # Expected runs and variance under H₀
        expected_runs = (2.0 * n1 * n0) / n + 1
        var_runs = (2.0 * n1 * n0 * (2.0 * n1 * n0 - n)) / (n * n * (n - 1))
        sd_runs = math.sqrt(abs(var_runs))

        z = (runs - expected_runs) / sd_runs if sd_runs > 0 else 0.0
        p_value = 2 * sp_stats.norm.cdf(-abs(z))

        # Interpretation
        if runs < expected_runs:
            pattern = "clustering/trend (fewer runs than expected)"
        elif runs > expected_runs:
            pattern = "oscillation/alternating (more runs than expected)"
        else:
            pattern = "consistent with randomness"

        return {
            "test_name": "Runs test (Wald-Wolfowitz)",
            "n": n,
            "n_above": n1,
            "n_below": n0,
            "observed_runs": runs,
            "expected_runs": float(expected_runs),
            "z_score": float(z),
            "p_value": float(p_value),
            "significant_at_05": p_value < 0.05,
            "cutoff": float(cutoff),
            "pattern": pattern,
        }


# ════════════════════════════════════════════════════════════════
# 3. Mood's Median Test
# ════════════════════════════════════════════════════════════════


class MoodsMedianTest:
    """
    Mood's Median Test — compare medians across k groups.

    Tests H₀: all groups have the same median.

    Uses a contingency table: count observations above/below the grand
    median in each group, then apply chi-square test.

    Why use it:
    - More robust than Kruskal-Wallis when extreme outliers exist
    - Simple to understand: just counts above/below median
    - Works with ordinal data
    """

    @staticmethod
    def test(*groups: np.ndarray) -> Dict[str, Any]:
        """
        Mood's median test.

        Args:
            *groups: two or more groups to compare

        Returns:
            Dict with chi-square, p-value, contingency table
        """
        groups = [np.asarray(g, dtype=float).ravel() for g in groups]
        k = len(groups)
        if k < 2:
            return {"error": "Need ≥2 groups", "test_name": "Mood's median test"}
        for i, g in enumerate(groups):
            if len(g) < 3:
                return {"error": f"Group {i} needs ≥3 observations"}

        # Grand median
        all_data = np.concatenate(groups)
        grand_median = float(np.median(all_data))

        # Contingency table
        above = np.array([int(np.sum(g > grand_median)) for g in groups])
        below = np.array([int(np.sum(g <= grand_median)) for g in groups])
        group_sizes = np.array([len(g) for g in groups])
        n_above = int(np.sum(above))
        n_below = int(np.sum(below))
        n = n_above + n_below

        # Chi-square statistic
        chi2 = 0.0
        for i in range(k):
            e_above = group_sizes[i] * n_above / n
            e_below = group_sizes[i] * n_below / n
            if e_above > 0:
                chi2 += (above[i] - e_above) ** 2 / e_above
            if e_below > 0:
                chi2 += (below[i] - e_below) ** 2 / e_below

        df = k - 1
        p_value = 1 - sp_stats.chi2.cdf(chi2, df)

        # Effect size: Cramér's V
        v = math.sqrt(chi2 / (n * (min(2, k) - 1))) if n > 0 else 0

        # Group medians
        group_medians = [float(np.median(g)) for g in groups]

        return {
            "test_name": "Mood's median test",
            "grand_median": grand_median,
            "chi_square": float(chi2),
            "df": df,
            "p_value": float(p_value),
            "significant_at_05": p_value < 0.05,
            "cramers_v": float(v),
            "contingency_table": {
                "above": above.tolist(),
                "below": below.tolist(),
                "group_sizes": group_sizes.tolist(),
                "total_above": n_above,
                "total_below": n_below,
            },
            "group_medians": group_medians,
        }


# ════════════════════════════════════════════════════════════════
# 4. Non-parametric Confidence Intervals
# ════════════════════════════════════════════════════════════════


class NonparametricCI:
    """
    Non-parametric confidence intervals using bootstrap methods.

    Provides multiple bootstrap CI methods:
    - Percentile: simplest, uses quantiles of bootstrap distribution
    - BCa: bias-corrected and accelerated, second-order accurate
    - Studentized: uses bootstrap t-statistics, better for skewed stats

    These are essential for:
    - Gini coefficient CIs (heavily skewed sampling distribution)
    - Theil index CIs (requires log-transform)
    - Any complex statistic without closed-form SE
    """

    @staticmethod
    def bootstrap_ci(
        data: np.ndarray,
        statistic: Callable[[np.ndarray], float],
        method: str = "bca",
        n_bootstrap: int = 5000,
        confidence: float = 0.95,
        seed: int = 42,
    ) -> Dict[str, Any]:
        """
        Bootstrap confidence interval.

        Args:
            data: 1D observations
            statistic: function(data) -> scalar
            method: 'percentile', 'bca', or 'studentized'
            n_bootstrap: number of resamples
            confidence: confidence level
            seed: random seed

        Returns:
            Dict with estimate, CI bounds, method details
        """
        data = np.asarray(data, dtype=float).ravel()
        n = len(data)
        if n < 5:
            return {"error": "Need ≥5 observations"}

        rng = np.random.RandomState(seed)
        estimate = float(statistic(data))

        # Generate bootstrap samples
        boot_stats = np.empty(n_bootstrap)
        for b in range(n_bootstrap):
            resample = rng.choice(data, size=n, replace=True)
            boot_stats[b] = statistic(resample)

        alpha = 1 - confidence

        if method == "percentile":
            ci_lo = float(np.percentile(boot_stats, 100 * alpha / 2))
            ci_hi = float(np.percentile(boot_stats, 100 * (1 - alpha / 2)))

        elif method == "bca":
            # Bias-correction factor z₀
            prop_below = np.mean(boot_stats < estimate)
            prop_below = np.clip(prop_below, 1e-10, 1 - 1e-10)
            z0 = sp_stats.norm.ppf(prop_below)

            # Acceleration factor (jackknife)
            jack_stats = np.empty(n)
            for i in range(n):
                jack_stats[i] = statistic(np.delete(data, i))
            jack_mean = np.mean(jack_stats)
            num = np.sum((jack_mean - jack_stats) ** 3)
            den = 6.0 * (np.sum((jack_mean - jack_stats) ** 2) ** 1.5)
            a = num / den if abs(den) > 1e-15 else 0.0

            # Adjusted percentiles
            z_lo = sp_stats.norm.ppf(alpha / 2)
            z_hi = sp_stats.norm.ppf(1 - alpha / 2)
            p_lo = sp_stats.norm.cdf(z0 + (z0 + z_lo) / (1 - a * (z0 + z_lo)))
            p_hi = sp_stats.norm.cdf(z0 + (z0 + z_hi) / (1 - a * (z0 + z_hi)))
            p_lo = np.clip(p_lo, 0.001, 0.999)
            p_hi = np.clip(p_hi, 0.001, 0.999)

            ci_lo = float(np.percentile(boot_stats, 100 * p_lo))
            ci_hi = float(np.percentile(boot_stats, 100 * p_hi))

        elif method == "studentized":
            # Studentized bootstrap (bootstrap-t)
            boot_t = np.empty(n_bootstrap)
            for b in range(n_bootstrap):
                resample = rng.choice(data, size=n, replace=True)
                stat_b = statistic(resample)
                # Estimate SE of stat_b via inner bootstrap (limited for speed)
                inner_stats = np.empty(200)
                for j in range(200):
                    inner_resample = rng.choice(resample, size=n, replace=True)
                    inner_stats[j] = statistic(inner_resample)
                se_b = np.std(inner_stats, ddof=1)
                boot_t[b] = (stat_b - estimate) / se_b if se_b > 0 else 0

            t_lo = np.percentile(boot_t, 100 * alpha / 2)
            t_hi = np.percentile(boot_t, 100 * (1 - alpha / 2))
            boot_se = float(np.std(boot_stats, ddof=1))
            ci_lo = estimate - t_hi * boot_se
            ci_hi = estimate - t_lo * boot_se

        else:
            return {"error": f"Unknown method: {method}. Use 'percentile', 'bca', or 'studentized'"}

        return {
            "estimate": estimate,
            "ci_lower": float(ci_lo),
            "ci_upper": float(ci_hi),
            "confidence": confidence,
            "method": method,
            "bootstrap_se": float(np.std(boot_stats, ddof=1)),
            "n_bootstrap": n_bootstrap,
            "n_observations": n,
        }

    @staticmethod
    def median_ci(
        data: np.ndarray,
        confidence: float = 0.95,
        method: str = "exact",
    ) -> Dict[str, Any]:
        """
        Confidence interval for the median.

        Args:
            data: observations
            confidence: confidence level
            method: 'exact' (binomial), 'bootstrap', or 'interpolation'

        Returns:
            Dict with median, CI bounds
        """
        data = np.asarray(data, dtype=float).ravel()
        n = len(data)
        if n < 3:
            return {"error": "Need ≥3 observations"}

        sorted_data = np.sort(data)
        median_val = float(np.median(data))
        alpha = 1 - confidence

        if method == "exact":
            # Exact CI using binomial distribution
            # Find indices j, k such that P(X_(j) ≤ median ≤ X_(k)) = confidence
            for j in range(n):
                k = n - 1 - j
                if k <= j:
                    break
                p_coverage = 1 - sp_stats.binom.cdf(j, n, 0.5) - sp_stats.binom.sf(k, n, 0.5)
                if p_coverage >= confidence:
                    return {
                        "median": median_val,
                        "ci_lower": float(sorted_data[j]),
                        "ci_upper": float(sorted_data[k]),
                        "confidence": float(p_coverage),
                        "method": "exact",
                        "n": n,
                    }
            # Fallback
            return {
                "median": median_val,
                "ci_lower": float(sorted_data[0]),
                "ci_upper": float(sorted_data[-1]),
                "confidence": 1.0,
                "method": "exact_fallback",
                "n": n,
            }

        elif method == "bootstrap":
            result = NonparametricCI.bootstrap_ci(
                data, np.median, method="bca", confidence=confidence
            )
            result["median"] = median_val
            return result

        else:
            # Interpolation-based (simplified)
            return NonparametricCI.bootstrap_ci(
                data, np.median, method="percentile", confidence=confidence
            )


# ════════════════════════════════════════════════════════════════
# 5. Non-parametric Effect Sizes
# ════════════════════════════════════════════════════════════════


class NonparametricEffectSize:
    """
    Non-parametric effect size measures.

    These quantify practical significance without distributional assumptions:
    - Cliff's delta: dominance measure, P(X>Y) - P(X<Y)
    - Rank-biserial correlation: from Mann-Whitney U
    - Vargha-Delaney A: P(X > Y), common language effect size

    Why non-parametric effect sizes:
    - Cohen's d assumes normality — misleading for skewed data
    - Cliff's delta works for any distribution
    - Directly interpretable: "X dominates Y by δ%"
    """

    @staticmethod
    def cliffs_delta(
        sample1: np.ndarray,
        sample2: np.ndarray,
    ) -> Dict[str, Any]:
        """
        Cliff's delta — dominance effect size.

        δ = (# pairs where x > y - # pairs where x < y) / (n₁ × n₂)

        Range: [-1, 1]
        - δ = 1: all x > y (complete dominance)
        - δ = 0: no dominance (stochastic equality)
        - δ = -1: all y > x

        Interpretation (|δ|):
        - < 0.147: negligible
        - < 0.33: small
        - < 0.474: medium
        - ≥ 0.474: large
        """
        sample1 = np.asarray(sample1, dtype=float).ravel()
        sample2 = np.asarray(sample2, dtype=float).ravel()
        n1, n2 = len(sample1), len(sample2)

        if n1 < 3 or n2 < 3:
            return {"error": "Need ≥3 per group", "effect_size": "Cliff's delta"}

        # Count dominance
        dominates = 0
        dominated_by = 0
        for x in sample1:
            for y in sample2:
                if x > y:
                    dominates += 1
                elif x < y:
                    dominated_by += 1

        delta = (dominates - dominated_by) / (n1 * n2)

        # Interpretation
        abs_delta = abs(delta)
        if abs_delta < 0.147:
            label = "negligible"
        elif abs_delta < 0.33:
            label = "small"
        elif abs_delta < 0.474:
            label = "medium"
        else:
            label = "large"

        # Bootstrap CI for delta
        def delta_stat(data):
            # Reconstruct from combined data (approximate)
            return delta  # Use analytical SE instead

        # Analytical SE (Sen & Hammer, 1966)
        # Complex formula; use bootstrap instead
        rng = np.random.RandomState(42)
        boot_deltas = np.empty(2000)
        for b in range(2000):
            r1 = rng.choice(sample1, size=n1, replace=True)
            r2 = rng.choice(sample2, size=n2, replace=True)
            d = 0
            for x in r1:
                for y in r2:
                    if x > y:
                        d += 1
                    elif x < y:
                        d -= 1
            boot_deltas[b] = d / (n1 * n2)

        ci_lo = float(np.percentile(boot_deltas, 2.5))
        ci_hi = float(np.percentile(boot_deltas, 97.5))

        return {
            "effect_size": "Cliff's delta",
            "delta": float(delta),
            "magnitude": label,
            "ci_lower_95": ci_lo,
            "ci_upper_95": ci_hi,
            "n1": n1,
            "n2": n2,
            "dominance_count": dominates,
            "dominated_count": dominated_by,
        }

    @staticmethod
    def rank_biserial_correlation(
        sample1: np.ndarray,
        sample2: np.ndarray,
    ) -> Dict[str, Any]:
        """
        Rank-biserial correlation — effect size from Mann-Whitney U.

        r = 2U/(n₁n₂) - 1

        Range: [-1, 1], directly interpretable as:
        - Probability of superiority: P(X > Y) = (r + 1) / 2
        """
        sample1 = np.asarray(sample1, dtype=float).ravel()
        sample2 = np.asarray(sample2, dtype=float).ravel()
        n1, n2 = len(sample1), len(sample2)

        result = sp_stats.mannwhitneyu(sample1, sample2, alternative="two-sided")
        U = result.statistic
        r = 2 * U / (n1 * n2) - 1
        p_superiority = (r + 1) / 2

        if abs(r) < 0.1:
            label = "negligible"
        elif abs(r) < 0.3:
            label = "small"
        elif abs(r) < 0.5:
            label = "medium"
        else:
            label = "large"

        return {
            "effect_size": "Rank-biserial correlation",
            "r": float(r),
            "magnitude": label,
            "U_statistic": float(U),
            "p_superiority": float(p_superiority),
            "n1": n1,
            "n2": n2,
        }

    @staticmethod
    def vargha_delaney_a(
        sample1: np.ndarray,
        sample2: np.ndarray,
    ) -> Dict[str, Any]:
        """
        Vargha-Delaney A — P(X > Y) common language effect size.

        A = U / (n₁ × n₂)

        Range: [0, 1]
        - A = 0.5: no effect (stochastic equality)
        - A = 1.0: all X > Y
        - A = 0.0: all Y > X

        Interpretation:
        - |A - 0.5| < 0.06: negligible
        - |A - 0.5| < 0.14: small
        - |A - 0.5| < 0.21: medium
        - |A - 0.5| ≥ 0.21: large
        """
        sample1 = np.asarray(sample1, dtype=float).ravel()
        sample2 = np.asarray(sample2, dtype=float).ravel()
        n1, n2 = len(sample1), len(sample2)

        result = sp_stats.mannwhitneyu(sample1, sample2, alternative="two-sided")
        U = result.statistic
        A = U / (n1 * n2)

        deviation = abs(A - 0.5)
        if deviation < 0.06:
            label = "negligible"
        elif deviation < 0.14:
            label = "small"
        elif deviation < 0.21:
            label = "medium"
        else:
            label = "large"

        return {
            "effect_size": "Vargha-Delaney A",
            "A": float(A),
            "magnitude": label,
            "interpretation": f"P(sample1 > sample2) = {A:.3f}",
            "n1": n1,
            "n2": n2,
        }


# ════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════


def _binomial_two_sided_p(b: int, n: int, p: float) -> float:
    """Two-sided exact binomial p-value: P(|B - np| ≥ |b - np|)."""
    expected = n * p
    dev = abs(b - expected)
    prob = 0.0
    for k in range(n + 1):
        if abs(k - expected) >= dev:
            prob += sp_stats.binom.pmf(k, n, p)
    return min(1.0, prob)


# ════════════════════════════════════════════════════════════════
# Runner Interface
# ════════════════════════════════════════════════════════════════


def run_method(method: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Entry point for the Rust bridge."""
    try:
        if method == "sign_test":
            data = np.array(args["data"], dtype=float)
            return SignTest.one_sample(
                data,
                hypothesized_median=args.get("hypothesized_median", 0.0),
                alternative=args.get("alternative", "two-sided"),
            )

        elif method == "sign_test_paired":
            s1 = np.array(args["sample1"], dtype=float)
            s2 = np.array(args["sample2"], dtype=float)
            return SignTest.paired(s1, s2, alternative=args.get("alternative", "two-sided"))

        elif method == "runs_test":
            data = np.array(args["data"], dtype=float)
            return RunsTest.test(data, cutoff=args.get("cutoff"))

        elif method == "moods_median_test":
            groups = [np.array(g, dtype=float) for g in args["groups"]]
            return MoodsMedianTest.test(*groups)

        elif method == "nonparametric_ci":
            data = np.array(args["data"], dtype=float)
            stat_name = args.get("statistic", "median")
            stat_fn = {"mean": np.mean, "median": np.median, "std": np.std}.get(stat_name, np.median)
            return NonparametricCI.bootstrap_ci(
                data, stat_fn,
                method=args.get("ci_method", "bca"),
                confidence=args.get("confidence", 0.95),
            )

        elif method == "median_ci":
            data = np.array(args["data"], dtype=float)
            return NonparametricCI.median_ci(
                data,
                confidence=args.get("confidence", 0.95),
                method=args.get("ci_method", "exact"),
            )

        elif method == "cliffs_delta":
            s1 = np.array(args["sample1"], dtype=float)
            s2 = np.array(args["sample2"], dtype=float)
            return NonparametricEffectSize.cliffs_delta(s1, s2)

        elif method == "rank_biserial":
            s1 = np.array(args["sample1"], dtype=float)
            s2 = np.array(args["sample2"], dtype=float)
            return NonparametricEffectSize.rank_biserial_correlation(s1, s2)

        elif method == "vargha_delaney_a":
            s1 = np.array(args["sample1"], dtype=float)
            s2 = np.array(args["sample2"], dtype=float)
            return NonparametricEffectSize.varga_delaney_a(s1, s2)

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
