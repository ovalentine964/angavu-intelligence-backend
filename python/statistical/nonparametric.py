"""
Non-Parametric Methods for Angavu Intelligence Backend (STA 341/342/444)

Implements statistical methods that do NOT assume normality — critical for
Kenyan informal sector data which is typically:
- Heavy-tailed (income distributions)
- Skewed (transaction amounts)
- Multimodal (multiple worker types)
- Categorical (product categories)

Methods:
1. Kernel Density Estimation (KDE) — non-parametric density estimation
2. Mann-Whitney U Test — non-parametric two-sample comparison
3. Kruskal-Wallis Test — non-parametric multi-group comparison
4. Bootstrap Confidence Intervals — distribution-free CI estimation
5. Permutation Tests — exact hypothesis testing without distributional assumptions

Mathematical Justification:
- KDE: f̂(x) = (1/nh) Σ K((x-xᵢ)/h) where K is Gaussian kernel
  - Bandwidth selection via Silverman's rule: h = 0.9 × min(σ, IQR/1.34) × n^(-1/5)
  - Avoids normality assumption for income distributions
- Mann-Whitney U: U = Σᵢ Σⱼ I(xᵢ > yⱼ)
  - Tests H₀: P(X > Y) = 0.5 (stochastic equality)
  - Distribution-free: valid for any continuous distribution
- Kruskal-Wallis: H = (12/(N(N+1))) Σ nᵢ(R̄ᵢ - R̄)²
  - Extension of Mann-Whitney to k groups
  - Tests H₀: all groups have the same distribution
- Bootstrap: Efron's percentile method
  - CI = [θ̂*_(α/2), θ̂*_(1-α/2)]
  - No distributional assumptions, works for any statistic
- Permutation test: exact p-value under H₀
  - Enumerate or Monte Carlo all possible rearrangements

Reference:
- Wasserman, L. (2006). All of Nonparametric Statistics.
- Efron, B. & Tibshirani, R. (1993). An Introduction to the Bootstrap.
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import numpy as np
from scipy import stats as sp_stats


# ════════════════════════════════════════════════════════════════
# 1. Kernel Density Estimation
# ════════════════════════════════════════════════════════════════


class KernelDensityEstimator:
    """
    Non-parametric kernel density estimation.

    Replaces parametric assumptions (normal, lognormal) with data-driven
    density estimation. Critical for income distributions in the informal
    sector which are typically heavy-tailed and multimodal.

    Mathematical basis:
        f̂(x) = (1/nh) Σᵢ K((x - xᵢ)/h)

        where K is the Gaussian kernel: K(u) = (1/√2π) exp(-u²/2)
        and h is the bandwidth selected via Silverman's rule.
    """

    @staticmethod
    def gaussian_kde(
        data: np.ndarray,
        points: Optional[np.ndarray] = None,
        bandwidth: Optional[float] = None,
        n_points: int = 200,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Gaussian kernel density estimation.

        Args:
            data: 1D array of observations
            points: evaluation points (default: linspace over data range)
            bandwidth: smoothing bandwidth (default: Silverman's rule)
            n_points: number of evaluation points if points not provided

        Returns:
            (evaluation_points, density_values)

        Raises:
            ValueError: if data has fewer than 2 points
        """
        data = np.asarray(data, dtype=float).ravel()
        if len(data) < 2:
            raise ValueError("KDE requires at least 2 data points")

        n = len(data)
        sigma = np.std(data, ddof=1)
        iqr = np.subtract(*np.percentile(data, [75, 25]))

        if bandwidth is None:
            # Silverman's rule of thumb
            h = 0.9 * min(sigma, iqr / 1.34 if iqr > 0 else sigma) * n ** (-0.2)
            h = max(h, 1e-10)  # avoid zero bandwidth
        else:
            h = bandwidth

        if points is None:
            margin = 3 * h
            points = np.linspace(data.min() - margin, data.max() + margin, n_points)

        # Compute KDE at each evaluation point
        density = np.zeros(len(points))
        for xi in data:
            density += np.exp(-0.5 * ((points - xi) / h) ** 2)
        density /= (n * h * math.sqrt(2 * math.pi))

        return points, density

    @staticmethod
    def adaptive_bandwidth(
        data: np.ndarray,
        alpha: float = 0.5,
    ) -> np.ndarray:
        """
        Adaptive bandwidth: smaller h in high-density regions, larger in tails.

        hᵢ = h₀ / √(f̂(xᵢ)/g)^α

        where g = geometric mean of {f̂(xᵢ)} and h₀ is the global bandwidth.

        This improves estimation for multimodal distributions (common in
        mixed worker-type income data).

        Args:
            data: 1D array of observations
            alpha: adaptation strength (0 = global, 1 = full adaptation)

        Returns:
            Array of per-point bandwidths
        """
        data = np.asarray(data, dtype=float).ravel()
        n = len(data)

        # Global bandwidth (Silverman)
        sigma = np.std(data, ddof=1)
        h0 = 1.06 * sigma * n ** (-0.2)

        # Pilot density at each data point
        _, pilot_density = KernelDensityEstimator.gaussian_kde(data, points=data, bandwidth=h0)

        # Geometric mean of pilot densities
        log_geo_mean = np.mean(np.log(pilot_density.clip(min=1e-30)))
        geo_mean = np.exp(log_geo_mean)

        # Adaptive bandwidths
        h_adaptive = h0 / np.sqrt((pilot_density / geo_mean) ** alpha + 1e-10)
        return h_adaptive.clip(min=h0 * 0.1, max=h0 * 5.0)

    @staticmethod
    def detect_multimodality(
        data: np.ndarray,
        n_modes_max: int = 5,
        bandwidth: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Detect number of modes in the distribution using KDE.

        Finds local maxima of the kernel density estimate.

        Args:
            data: 1D array of observations
            n_modes_max: maximum number of modes to detect
            bandwidth: KDE bandwidth (default: Silverman's rule)

        Returns:
            Dict with n_modes, mode_locations, mode_heights, is_multimodal
        """
        points, density = KernelDensityEstimator.gaussian_kde(data, bandwidth=bandwidth)

        # Find local maxima
        modes = []
        for i in range(1, len(density) - 1):
            if density[i] > density[i - 1] and density[i] > density[i + 1]:
                modes.append((points[i], density[i]))

        # Sort by density (descending) and keep top n_modes_max
        modes.sort(key=lambda x: x[1], reverse=True)
        modes = modes[:n_modes_max]

        return {
            "n_modes": len(modes),
            "mode_locations": [m[0] for m in modes],
            "mode_heights": [m[1] for m in modes],
            "is_multimodal": len(modes) > 1,
        }


# ════════════════════════════════════════════════════════════════
# 2. Mann-Whitney U Test
# ════════════════════════════════════════════════════════════════


class MannWhitneyTest:
    """
    Mann-Whitney U test (Wilcoxon rank-sum test).

    Non-parametric test for comparing two independent groups.
    Tests H₀: P(X > Y) = 0.5 (stochastic equality).

    Why non-parametric:
    - Income data is heavily skewed → t-test assumptions violated
    - Transaction amounts have heavy tails → normal approximation poor
    - Works for ordinal data (rating scales, Likert items)

    Mathematical basis:
        U = Σᵢ Σⱼ S(xᵢ, yⱼ) where S(a,b) = 1 if a > b, 0.5 if a = b, 0 otherwise

        E[U] = n₁n₂/2
        Var[U] = n₁n₂(n₁+n₂+1)/12  (with tie correction)

        Z = (U - E[U]) / √Var[U] → N(0,1) for large samples
    """

    @staticmethod
    def test(
        sample1: np.ndarray,
        sample2: np.ndarray,
        alternative: str = "two-sided",
    ) -> Dict[str, Any]:
        """
        Perform Mann-Whitney U test.

        Args:
            sample1: first sample
            sample2: second sample
            alternative: 'two-sided', 'less', or 'greater'

        Returns:
            Dict with test statistic, p-value, effect size, interpretation
        """
        sample1 = np.asarray(sample1, dtype=float).ravel()
        sample2 = np.asarray(sample2, dtype=float).ravel()

        n1, n2 = len(sample1), len(sample2)
        if n1 < 3 or n2 < 3:
            return {
                "error": "Need at least 3 observations per group",
                "test_name": "Mann-Whitney U test",
            }

        # Use scipy for exact computation
        result = sp_stats.mannwhitneyu(sample1, sample2, alternative=alternative)

        # Effect size: rank-biserial correlation
        # r = 2U/(n₁n₂) - 1  (ranges from -1 to 1)
        U = result.statistic
        r = 2 * U / (n1 * n2) - 1

        # Common language effect size: P(X > Y)
        # f = U / (n₁n₂)
        f = U / (n1 * n2)

        # Interpretation
        if abs(r) < 0.1:
            effect_label = "negligible"
        elif abs(r) < 0.3:
            effect_label = "small"
        elif abs(r) < 0.5:
            effect_label = "medium"
        else:
            effect_label = "large"

        return {
            "test_name": "Mann-Whitney U test",
            "U_statistic": float(U),
            "p_value": float(result.pvalue),
            "significant_at_05": result.pvalue < 0.05,
            "effect_size_rank_biserial": float(r),
            "effect_size_label": effect_label,
            "common_language_effect_size": float(f),
            "n1": n1,
            "n2": n2,
            "alternative": alternative,
            "median_difference": float(np.median(sample1) - np.median(sample2)),
        }


# ════════════════════════════════════════════════════════════════
# 3. Kruskal-Wallis Test
# ════════════════════════════════════════════════════════════════


class KruskalWallisTest:
    """
    Kruskal-Wallis H test — non-parametric one-way ANOVA.

    Extension of Mann-Whitney to k ≥ 2 groups.
    Tests H₀: all groups have the same distribution.

    Why non-parametric:
    - Compare income across multiple worker types (farmer, boda boda, vendor, etc.)
    - No assumption of normality or equal variances
    - Works with unequal sample sizes

    Mathematical basis:
        H = (12/(N(N+1))) Σᵢ nᵢ(R̄ᵢ - R̄)²

        where R̄ᵢ is the mean rank of group i, R̄ = (N+1)/2

        H ~ χ²(k-1) asymptotically
    """

    @staticmethod
    def test(*groups: np.ndarray, alpha: float = 0.05) -> Dict[str, Any]:
        """
        Perform Kruskal-Wallis H test.

        Args:
            *groups: two or more groups to compare
            alpha: significance level for post-hoc tests

        Returns:
            Dict with H statistic, p-value, effect size, post-hoc comparisons
        """
        groups = [np.asarray(g, dtype=float).ravel() for g in groups]
        k = len(groups)

        if k < 2:
            return {"error": "Need at least 2 groups"}

        for i, g in enumerate(groups):
            if len(g) < 3:
                return {"error": f"Group {i} has fewer than 3 observations"}

        # Kruskal-Wallis test
        result = sp_stats.kruskal(*groups)

        # Effect size: epsilon-squared (ε²)
        # ε² = (H - k + 1) / (N - k)
        N = sum(len(g) for g in groups)
        H = result.statistic
        epsilon_sq = max(0, (H - k + 1) / (N - k))

        # Effect size interpretation
        if epsilon_sq < 0.01:
            effect_label = "negligible"
        elif epsilon_sq < 0.06:
            effect_label = "small"
        elif epsilon_sq < 0.14:
            effect_label = "medium"
        else:
            effect_label = "large"

        # Post-hoc pairwise comparisons (Dunn's test with Bonferroni correction)
        n_comparisons = k * (k - 1) // 2
        post_hoc = []
        if result.pvalue < alpha and k > 2:
            # All-pairs rank comparison
            all_values = np.concatenate(groups)
            all_ranks = sp_stats.rankdata(all_values)

            rank_offset = 0
            group_mean_ranks = []
            for g in groups:
                ng = len(g)
                group_ranks = all_ranks[rank_offset:rank_offset + ng]
                group_mean_ranks.append(np.mean(group_ranks))
                rank_offset += ng

            for i in range(k):
                for j in range(i + 1, k):
                    # Dunn's test: z = (R̄ᵢ - R̄ⱼ) / SE
                    # SE = √(N(N+1)/12 × (1/nᵢ + 1/nⱼ))
                    ni, nj = len(groups[i]), len(groups[j])
                    se = math.sqrt(N * (N + 1) / 12 * (1 / ni + 1 / nj))
                    z = (group_mean_ranks[i] - group_mean_ranks[j]) / se if se > 0 else 0
                    p_unadjusted = 2 * (1 - sp_stats.norm.cdf(abs(z)))
                    p_adjusted = min(1.0, p_unadjusted * n_comparisons)  # Bonferroni

                    post_hoc.append({
                        "group_i": i,
                        "group_j": j,
                        "mean_rank_i": float(group_mean_ranks[i]),
                        "mean_rank_j": float(group_mean_ranks[j]),
                        "z_statistic": float(z),
                        "p_value_adjusted": float(p_adjusted),
                        "significant": p_adjusted < alpha,
                    })

        # Descriptive statistics per group
        group_stats = []
        for i, g in enumerate(groups):
            group_stats.append({
                "group": i,
                "n": len(g),
                "median": float(np.median(g)),
                "mean_rank": float(group_mean_ranks[i]) if result.pvalue < alpha and k > 2 else None,
                "iqr": float(np.subtract(*np.percentile(g, [75, 25]))),
            })

        return {
            "test_name": "Kruskal-Wallis H test",
            "H_statistic": float(H),
            "p_value": float(result.pvalue),
            "significant_at_05": result.pvalue < 0.05,
            "effect_size_epsilon_sq": float(epsilon_sq),
            "effect_size_label": effect_label,
            "n_groups": k,
            "total_n": N,
            "group_statistics": group_stats,
            "post_hoc_comparisons": post_hoc,
        }


# ════════════════════════════════════════════════════════════════
# 4. Bootstrap Confidence Intervals
# ════════════════════════════════════════════════════════════════


class BootstrapInference:
    """
    Bootstrap confidence intervals — distribution-free inference.

    Efron's percentile bootstrap: resample with replacement, compute
    statistic on each resample, take quantiles as CI bounds.

    Why bootstrap:
    - No distributional assumptions (works for Gini, Theil, median, etc.)
    - Works for complex statistics (ratios, nonlinear functions)
    - Better than normal approximation for skewed data
    - Essential for income inequality measures

    Mathematical basis:
        θ̂*_(α/2) and θ̂*_(1-α/2) form the (1-α) CI

        where θ̂*_q is the q-th quantile of the bootstrap distribution

        Coverage: P(θ ∈ CI) → 1-α as n→∞ (for smooth statistics)
    """

    @staticmethod
    def percentile_ci(
        data: np.ndarray,
        statistic: Callable[[np.ndarray], float],
        n_bootstrap: int = 5000,
        confidence: float = 0.95,
        seed: int = 42,
    ) -> Dict[str, Any]:
        """
        Bootstrap percentile confidence interval.

        Args:
            data: 1D array of observations
            statistic: function that computes the statistic of interest
            n_bootstrap: number of bootstrap resamples
            confidence: confidence level (default 0.95)
            seed: random seed for reproducibility

        Returns:
            Dict with estimate, ci_lower, ci_upper, bootstrap_se, bootstrap_distribution
        """
        data = np.asarray(data, dtype=float).ravel()
        n = len(data)
        if n < 2:
            return {"error": "Need at least 2 observations for bootstrap"}

        rng = np.random.RandomState(seed)

        # Original estimate
        estimate = float(statistic(data))

        # Bootstrap resamples
        boot_stats = np.empty(n_bootstrap)
        for b in range(n_bootstrap):
            resample = rng.choice(data, size=n, replace=True)
            boot_stats[b] = statistic(resample)

        # Percentile CI
        alpha = 1 - confidence
        ci_lower = float(np.percentile(boot_stats, 100 * alpha / 2))
        ci_upper = float(np.percentile(boot_stats, 100 * (1 - alpha / 2)))

        # Bootstrap SE
        boot_se = float(np.std(boot_stats, ddof=1))

        # Bias-corrected estimate
        bias = np.mean(boot_stats) - estimate

        return {
            "estimate": estimate,
            "ci_lower": ci_lower,
            "ci_upper": ci_upper,
            "confidence": confidence,
            "bootstrap_se": boot_se,
            "bias": float(bias),
            "n_bootstrap": n_bootstrap,
            "n_observations": n,
        }

    @staticmethod
    def bias_corrected_accelerated_ci(
        data: np.ndarray,
        statistic: Callable[[np.ndarray], float],
        n_bootstrap: int = 5000,
        confidence: float = 0.95,
        seed: int = 42,
    ) -> Dict[str, Any]:
        """
        Bias-corrected and accelerated (BCa) bootstrap CI.

        More accurate than percentile CI for skewed distributions.
        Corrects for both bias and skewness in the bootstrap distribution.

        Args:
            data: 1D array of observations
            statistic: function that computes the statistic of interest
            n_bootstrap: number of bootstrap resamples
            confidence: confidence level
            seed: random seed

        Returns:
            Dict with estimate, ci_lower, ci_upper, bias_correction, acceleration
        """
        data = np.asarray(data, dtype=float).ravel()
        n = len(data)
        if n < 5:
            return {"error": "Need at least 5 observations for BCa bootstrap"}

        rng = np.random.RandomState(seed)

        # Original estimate
        estimate = float(statistic(data))

        # Bootstrap resamples
        boot_stats = np.empty(n_bootstrap)
        for b in range(n_bootstrap):
            resample = rng.choice(data, size=n, replace=True)
            boot_stats[b] = statistic(resample)

        # Bias correction factor z₀
        # z₀ = Φ⁻¹(#(θ̂* < θ̂) / B)
        proportion_below = np.mean(boot_stats < estimate)
        z0 = sp_stats.norm.ppf(proportion_below.clip(1e-10, 1 - 1e-10))

        # Acceleration factor a (using jackknife)
        jackknife_stats = np.empty(n)
        for i in range(n):
            jackknife_sample = np.delete(data, i)
            jackknife_stats[i] = statistic(jackknife_sample)
        jack_mean = np.mean(jackknife_stats)
        num = np.sum((jack_mean - jackknife_stats) ** 3)
        den = 6.0 * (np.sum((jack_mean - jackknife_stats) ** 2) ** 1.5)
        a = num / den if abs(den) > 1e-15 else 0.0

        # Adjusted percentiles
        alpha = 1 - confidence
        z_alpha_lower = sp_stats.norm.ppf(alpha / 2)
        z_alpha_upper = sp_stats.norm.ppf(1 - alpha / 2)

        def adjust_percentile(z):
            p = sp_stats.norm.cdf(z0 + (z0 + z) / (1 - a * (z0 + z)))
            return p.clip(0.001, 0.999)

        p_lower = adjust_percentile(z_alpha_lower)
        p_upper = adjust_percentile(z_alpha_upper)

        ci_lower = float(np.percentile(boot_stats, 100 * p_lower))
        ci_upper = float(np.percentile(boot_stats, 100 * p_upper))

        return {
            "estimate": estimate,
            "ci_lower": ci_lower,
            "ci_upper": ci_upper,
            "confidence": confidence,
            "bias_correction_z0": float(z0),
            "acceleration_a": float(a),
            "n_bootstrap": n_bootstrap,
            "n_observations": n,
        }

    @staticmethod
    def bootstrap_se(
        data: np.ndarray,
        statistic: Callable[[np.ndarray], float],
        n_bootstrap: int = 5000,
        seed: int = 42,
    ) -> float:
        """
        Bootstrap standard error of a statistic.

        Args:
            data: 1D array of observations
            statistic: function that computes the statistic
            n_bootstrap: number of bootstrap resamples
            seed: random seed

        Returns:
            Bootstrap standard error
        """
        data = np.asarray(data, dtype=float).ravel()
        n = len(data)
        rng = np.random.RandomState(seed)

        boot_stats = np.empty(n_bootstrap)
        for b in range(n_bootstrap):
            resample = rng.choice(data, size=n, replace=True)
            boot_stats[b] = statistic(resample)

        return float(np.std(boot_stats, ddof=1))


# ════════════════════════════════════════════════════════════════
# 5. Permutation Tests
# ════════════════════════════════════════════════════════════════


class PermutationTest:
    """
    Permutation (randomization) tests — exact hypothesis testing.

    Distribution-free tests that compute exact p-values by enumerating
    (or Monte Carlo sampling) all possible rearrangements of the data.

    Why permutation tests:
    - Exact p-values (no asymptotic approximation needed)
    - No distributional assumptions
    - Works for any test statistic
    - Valid for small samples (where CLT doesn't apply)

    Mathematical basis:
        Under H₀, the group labels are exchangeable.
        p-value = #(T(π) ≥ T(observed)) / |Π|

        where Π is the set of all permutations (or a Monte Carlo subset)
    """

    @staticmethod
    def two_sample(
        sample1: np.ndarray,
        sample2: np.ndarray,
        statistic: Optional[Callable] = None,
        n_permutations: int = 10000,
        alternative: str = "two-sided",
        seed: int = 42,
    ) -> Dict[str, Any]:
        """
        Permutation test for two independent samples.

        Default statistic: difference in means.

        Args:
            sample1: first sample
            sample2: second sample
            statistic: function(sample1, sample2) -> scalar test statistic
            n_permutations: number of random permutations
            alternative: 'two-sided', 'less', or 'greater'
            seed: random seed

        Returns:
            Dict with observed statistic, p-value, permutation distribution
        """
        sample1 = np.asarray(sample1, dtype=float).ravel()
        sample2 = np.asarray(sample2, dtype=float).ravel()

        n1, n2 = len(sample1), len(sample2)
        combined = np.concatenate([sample1, sample2])
        N = n1 + n2

        if statistic is None:
            def statistic(s1, s2):
                return np.mean(s1) - np.mean(s2)

        # Observed test statistic
        observed = float(statistic(sample1, sample2))

        # Monte Carlo permutation distribution
        rng = np.random.RandomState(seed)
        perm_stats = np.empty(n_permutations)

        for b in range(n_permutations):
            perm = rng.permutation(combined)
            perm_stats[b] = statistic(perm[:n1], perm[n1:])

        # Compute p-value
        if alternative == "two-sided":
            p_value = np.mean(np.abs(perm_stats) >= abs(observed))
        elif alternative == "greater":
            p_value = np.mean(perm_stats >= observed)
        elif alternative == "less":
            p_value = np.mean(perm_stats <= observed)
        else:
            raise ValueError(f"Unknown alternative: {alternative}")

        return {
            "test_name": "Permutation test",
            "observed_statistic": observed,
            "p_value": float(p_value),
            "significant_at_05": p_value < 0.05,
            "n_permutations": n_permutations,
            "n1": n1,
            "n2": n2,
            "alternative": alternative,
            "permutation_mean": float(np.mean(perm_stats)),
            "permutation_std": float(np.std(perm_stats)),
        }

    @staticmethod
    def correlation_test(
        x: np.ndarray,
        y: np.ndarray,
        n_permutations: int = 10000,
        method: str = "spearman",
        seed: int = 42,
    ) -> Dict[str, Any]:
        """
        Permutation test for correlation.

        Tests H₀: X and Y are independent.

        Args:
            x: first variable
            y: second variable
            n_permutations: number of permutations
            method: 'pearson' or 'spearman'
            seed: random seed

        Returns:
            Dict with correlation, p-value, CI
        """
        x = np.asarray(x, dtype=float).ravel()
        y = np.asarray(y, dtype=float).ravel()
        n = len(x)

        if n < 5:
            return {"error": "Need at least 5 observations"}

        # Observed correlation
        if method == "spearman":
            observed_corr, _ = sp_stats.spearmanr(x, y)
        else:
            observed_corr, _ = sp_stats.pearsonr(x, y)

        # Permutation distribution
        rng = np.random.RandomState(seed)
        perm_corrs = np.empty(n_permutations)

        for b in range(n_permutations):
            y_perm = rng.permutation(y)
            if method == "spearman":
                perm_corrs[b], _ = sp_stats.spearmanr(x, y_perm)
            else:
                perm_corrs[b], _ = sp_stats.pearsonr(x, y_perm)

        p_value = float(np.mean(np.abs(perm_corrs) >= abs(observed_corr)))

        # Bootstrap CI for the correlation
        boot_corrs = np.empty(n_permutations)
        for b in range(n_permutations):
            idx = rng.choice(n, size=n, replace=True)
            if method == "spearman":
                boot_corrs[b], _ = sp_stats.spearmanr(x[idx], y[idx])
            else:
                boot_corrs[b], _ = sp_stats.pearsonr(x[idx], y[idx])

        ci_lower = float(np.percentile(boot_corrs, 2.5))
        ci_upper = float(np.percentile(boot_corrs, 97.5))

        return {
            "test_name": f"Permutation test ({method} correlation)",
            "observed_correlation": float(observed_corr),
            "p_value": p_value,
            "significant_at_05": p_value < 0.05,
            "ci_lower_95": ci_lower,
            "ci_upper_95": ci_upper,
            "n_permutations": n_permutations,
            "n_observations": n,
            "method": method,
        }


# ════════════════════════════════════════════════════════════════
# 6. Power Analysis
# ════════════════════════════════════════════════════════════════


class PowerAnalysis:
    """
    Statistical power analysis for sample size determination.

    Ensures that intelligence products have sufficient data for
    reliable inference. Reports when sample sizes are insufficient.

    Mathematical basis:
        Power = P(reject H₀ | H₁ is true) = 1 - β

        For two-sample t-test:
        n = (z_{α/2} + z_β)² × 2σ² / δ²

        where δ is the minimum detectable effect
    """

    @staticmethod
    def two_sample_t_test(
        effect_size: float,
        alpha: float = 0.05,
        power: float = 0.80,
        ratio: float = 1.0,
    ) -> Dict[str, Any]:
        """
        Sample size for two-sample t-test.

        Args:
            effect_size: Cohen's d (standardized mean difference)
            alpha: significance level
            power: desired power (1 - β)
            ratio: n2/n1 ratio

        Returns:
            Dict with required n1, n2, total_n
        """
        if effect_size == 0:
            return {"error": "Effect size cannot be zero"}

        z_alpha = sp_stats.norm.ppf(1 - alpha / 2)
        z_beta = sp_stats.norm.ppf(power)

        # n per group (equal allocation)
        n = ((z_alpha + z_beta) ** 2 * (1 + 1 / ratio)) / (effect_size ** 2)
        n = math.ceil(n)

        return {
            "test": "two_sample_t_test",
            "effect_size_cohens_d": effect_size,
            "alpha": alpha,
            "power": power,
            "n1": n,
            "n2": math.ceil(n * ratio),
            "total_n": n + math.ceil(n * ratio),
            "interpretation": PowerAnalysis._interpret_effect_size(effect_size),
        }

    @staticmethod
    def mann_whitney(
        effect_size: float,
        alpha: float = 0.05,
        power: float = 0.80,
    ) -> Dict[str, Any]:
        """
        Sample size for Mann-Whitney U test.

        Uses the asymptotic relative efficiency (ARE) correction:
        n_mw ≈ n_t / (3/π) ≈ n_t × 1.047

        Args:
            effect_size: Cohen's d equivalent
            alpha: significance level
            power: desired power

        Returns:
            Dict with required sample sizes
        """
        # Mann-Whitney has ARE of 3/π ≈ 0.955 relative to t-test
        # So need slightly more observations
        t_result = PowerAnalysis.two_sample_t_test(effect_size, alpha, power)
        if "error" in t_result:
            return t_result

        correction = math.pi / 3  # ≈ 1.047
        n_adjusted = math.ceil(t_result["n1"] * correction)

        return {
            "test": "mann_whitney",
            "effect_size_cohens_d": effect_size,
            "alpha": alpha,
            "power": power,
            "n_per_group": n_adjusted,
            "total_n": 2 * n_adjusted,
            "note": "Mann-Whitney needs ~5% more observations than t-test for same power",
        }

    @staticmethod
    def proportion_test(
        p1: float,
        p2: float,
        alpha: float = 0.05,
        power: float = 0.80,
    ) -> Dict[str, Any]:
        """
        Sample size for comparing two proportions.

        Args:
            p1: proportion in group 1
            p2: proportion in group 2
            alpha: significance level
            power: desired power

        Returns:
            Dict with required sample sizes
        """
        z_alpha = sp_stats.norm.ppf(1 - alpha / 2)
        z_beta = sp_stats.norm.ppf(power)

        p_bar = (p1 + p2) / 2
        n = ((z_alpha * math.sqrt(2 * p_bar * (1 - p_bar)) +
              z_beta * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))) ** 2) / ((p1 - p2) ** 2)
        n = math.ceil(n)

        return {
            "test": "proportion_test",
            "p1": p1,
            "p2": p2,
            "alpha": alpha,
            "power": power,
            "n_per_group": n,
            "total_n": 2 * n,
        }

    @staticmethod
    def minimum_detectable_effect(
        n_per_group: int,
        alpha: float = 0.05,
        power: float = 0.80,
    ) -> Dict[str, Any]:
        """
        Minimum detectable effect given sample size.

        Args:
            n_per_group: sample size per group
            alpha: significance level
            power: desired power

        Returns:
            Dict with minimum Cohen's d
        """
        z_alpha = sp_stats.norm.ppf(1 - alpha / 2)
        z_beta = sp_stats.norm.ppf(power)

        d = (z_alpha + z_beta) * math.sqrt(2 / n_per_group)

        return {
            "n_per_group": n_per_group,
            "alpha": alpha,
            "power": power,
            "min_detectable_effect_cohens_d": float(d),
            "interpretation": PowerAnalysis._interpret_effect_size(d),
        }

    @staticmethod
    def sample_size_for_confidence_interval(
        desired_width: float,
        estimated_std: float,
        confidence: float = 0.95,
    ) -> Dict[str, Any]:
        """
        Sample size for a confidence interval of desired width.

        n = (2 × z_{α/2} × σ / W)²

        Args:
            desired_width: desired CI width (upper - lower)
            estimated_std: estimated population standard deviation
            confidence: confidence level

        Returns:
            Required sample size
        """
        z = sp_stats.norm.ppf(1 - (1 - confidence) / 2)
        n = math.ceil((2 * z * estimated_std / desired_width) ** 2)

        return {
            "desired_width": desired_width,
            "estimated_std": estimated_std,
            "confidence": confidence,
            "required_n": n,
        }

    @staticmethod
    def _interpret_effect_size(d: float) -> str:
        d = abs(d)
        if d < 0.2:
            return "negligible"
        elif d < 0.5:
            return "small"
        elif d < 0.8:
            return "medium"
        else:
            return "large"


# ════════════════════════════════════════════════════════════════
# 7. Differential Privacy (Fixed: ε=1.0 minimum)
# ════════════════════════════════════════════════════════════════


class DifferentialPrivacy:
    """
    Differential privacy for aggregated statistics.

    IMPORTANT FIX: ε=0.1 was too restrictive — noise overwhelmed signal.
    Minimum ε=1.0 for useful inference. See:
    - Dwork & Roth (2014). The Algorithmic Foundations of DP.
    - For ε=1.0: P(output|D₁) ≤ e × P(output|D₂) — bounded privacy loss

    Mathematical basis:
        (ε, δ)-differential privacy:
        P(M(D) ∈ S) ≤ e^ε × P(M(D') ∈ S) + δ

        Gaussian mechanism: σ = Δf × √(2 ln(1.25/δ)) / ε
    """

    # FIXED: ε=0.1 was too strict. ε=1.0 provides useful inference
    # while still providing meaningful privacy guarantees.
    # For ε=1.0, the privacy loss is bounded by e ≈ 2.718
    DEFAULT_EPSILON = 1.0  # was 0.1 — too noisy for any useful inference
    DEFAULT_DELTA = 1e-5
    MIN_COHORT_SIZE = 10  # k-anonymity

    @staticmethod
    def noise_scale(
        epsilon: float = 1.0,
        delta: float = 1e-5,
        sensitivity: float = 1.0,
    ) -> float:
        """
        Compute Gaussian noise scale for (ε, δ)-DP.

        σ = Δf × √(2 ln(1.25/δ)) / ε

        Args:
            epsilon: privacy budget (≥1.0 recommended)
            delta: failure probability
            sensitivity: L2 sensitivity of the query

        Returns:
            Noise standard deviation
        """
        return sensitivity * math.sqrt(2 * math.log(1.25 / delta)) / epsilon

    @staticmethod
    def add_noise(
        value: float,
        epsilon: float = 1.0,
        delta: float = 1e-5,
        sensitivity: float = 1.0,
    ) -> float:
        """Add calibrated Gaussian noise for DP."""
        sigma = DifferentialPrivacy.noise_scale(epsilon, delta, sensitivity)
        noise = np.random.normal(0, sigma)
        return value + noise

    @staticmethod
    def private_mean(
        data: np.ndarray,
        epsilon: float = 1.0,
        clip_bounds: Tuple[float, float] = (0.0, 1.0),
    ) -> Dict[str, Any]:
        """
        Differentially private mean with clipping.

        Args:
            data: observations
            epsilon: privacy budget
            clip_bounds: (lower, upper) for clipping

        Returns:
            Dict with private_mean, noise_added, true_mean
        """
        data = np.asarray(data, dtype=float).ravel()
        low, high = clip_bounds

        # Clip data
        clipped = np.clip(data, low, high)
        true_mean = float(np.mean(clipped))

        # Sensitivity = (high - low) / n
        n = len(data)
        sensitivity = (high - low) / n

        # Add noise
        private = DifferentialPrivacy.add_noise(true_mean, epsilon, sensitivity=sensitivity)

        return {
            "private_mean": private,
            "true_mean": true_mean,
            "noise_added": private - true_mean,
            "epsilon": epsilon,
            "n": n,
            "clipped_count": int(np.sum((data < low) | (data > high))),
        }


# ════════════════════════════════════════════════════════════════
# 8. HHI (Herfindahl-Hirschman Index) — Fixed Application
# ════════════════════════════════════════════════════════════════


class MarketConcentration:
    """
    Market concentration metrics — correctly applied.

    IMPORTANT FIX: HHI was misapplied. HHI measures market concentration
    for ANTITRUST analysis (DOJ guidelines: HHI < 1500 = unconcentrated,
    1500-2500 = moderately concentrated, > 2500 = highly concentrated).

    For informal sector market analysis, we need:
    - HHI for market structure assessment
    - Gini coefficient for inequality
    - Entropy for diversity
    """

    @staticmethod
    def hhi(market_shares: np.ndarray) -> Dict[str, Any]:
        """
        Herfindahl-Hirschman Index.

        HHI = Σᵢ sᵢ² where sᵢ is market share as percentage (0-100).

        Args:
            market_shares: array of market shares (as percentages, e.g., 30 for 30%)

        Returns:
            Dict with HHI, concentration level, number of firms
        """
        shares = np.asarray(market_shares, dtype=float).ravel()

        # HHI = Σ sᵢ² (shares as percentages)
        hhi = float(np.sum(shares ** 2))

        # DOJ concentration thresholds
        if hhi < 1500:
            level = "unconcentrated"
        elif hhi < 2500:
            level = "moderately_concentrated"
        else:
            level = "highly_concentrated"

        # Equivalent number of firms: N_eq = 1/HHI_normalized
        shares_normalized = shares / shares.sum() if shares.sum() > 0 else shares
        hhi_normalized = float(np.sum(shares_normalized ** 2))
        n_equivalent = 1.0 / hhi_normalized if hhi_normalized > 0 else float('inf')

        return {
            "hhi": hhi,
            "concentration_level": level,
            "n_firms": len(shares),
            "n_equivalent_firms": float(n_equivalent),
            "thresholds": {"unconcentrated": 1500, "moderately": 2500, "highly": "above 2500"},
            "note": "HHI measures market concentration for antitrust. Use Gini for inequality.",
        }

    @staticmethod
    def gini(values: np.ndarray) -> Dict[str, Any]:
        """
        Gini coefficient — measures inequality.

        G = (2 Σᵢ i×yᵢ) / (n Σ yᵢ) - (n+1)/n

        where yᵢ are sorted values.

        Args:
            values: array of values (e.g., incomes, transaction volumes)

        Returns:
            Dict with Gini coefficient, interpretation, bootstrap CI
        """
        values = np.asarray(values, dtype=float).ravel()
        n = len(values)
        if n < 2:
            return {"error": "Need at least 2 observations"}

        sorted_vals = np.sort(values)
        index = np.arange(1, n + 1)

        gini = (2 * np.sum(index * sorted_vals)) / (n * np.sum(sorted_vals)) - (n + 1) / n

        # Interpretation
        if gini < 0.2:
            interpretation = "low_inequality"
        elif gini < 0.4:
            interpretation = "moderate_inequality"
        elif gini < 0.6:
            interpretation = "high_inequality"
        else:
            interpretation = "very_high_inequality"

        # Bootstrap CI
        def gini_stat(data):
            s = np.sort(data)
            idx = np.arange(1, len(s) + 1)
            return (2 * np.sum(idx * s)) / (len(s) * np.sum(s)) - (len(s) + 1) / len(s)

        ci = BootstrapInference.percentile_ci(values, gini_stat, n_bootstrap=2000)

        return {
            "gini": float(gini),
            "interpretation": interpretation,
            "n": n,
            "ci_lower_95": ci.get("ci_lower"),
            "ci_upper_95": ci.get("ci_upper"),
            "bootstrap_se": ci.get("bootstrap_se"),
        }

    @staticmethod
    def theil_index(values: np.ndarray) -> Dict[str, Any]:
        """
        Theil T index — decomposable inequality measure.

        T = (1/n) Σ (yᵢ/ȳ) × ln(yᵢ/ȳ)

        Theil T is decomposable: T = T_between + T_within

        Args:
            values: array of positive values

        Returns:
            Dict with Theil index, bootstrap CI
        """
        values = np.asarray(values, dtype=float).ravel()
        values = values[values > 0]  # Theil requires positive values
        n = len(values)
        if n < 2:
            return {"error": "Need at least 2 positive observations"}

        mean_val = np.mean(values)
        ratios = values / mean_val
        theil = float(np.mean(ratios * np.log(ratios)))

        # Bootstrap CI
        def theil_stat(data):
            d = data[data > 0]
            m = np.mean(d)
            r = d / m
            return np.mean(r * np.log(r))

        ci = BootstrapInference.percentile_ci(values, theil_stat, n_bootstrap=2000)

        return {
            "theil_t": theil,
            "n": n,
            "ci_lower_95": ci.get("ci_lower"),
            "ci_upper_95": ci.get("ci_upper"),
            "bootstrap_se": ci.get("bootstrap_se"),
            "note": "Theil T is 0 for perfect equality, increases with inequality",
        }
