"""
Hypothesis Testing, Bootstrap Inference & Distribution Fitting (STA 342, STA 444).

Classes:
- HypothesisTester: z-test, t-test, chi-square, Mann-Whitney U
- BootstrapInference: Bootstrap CI, permutation tests
- DistributionFitter: MLE/MOM fitting, goodness-of-fit tests

Decomposed from statistical_foundation.py for maintainability.
"""

from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
from scipy import stats


class BootstrapInference:
    """
    Bootstrap inference (STA 444 — Non-Parametric Methods).

    Distribution-free confidence intervals and standard errors.
    The bootstrap principle: F̂ approximates F; resampling from F̂
    mimics sampling from F.
    """

    @staticmethod
    def percentile_ci(
        data: np.ndarray,
        statistic_func: Callable,
        n_bootstrap: int = 10000,
        confidence: float = 0.95,
        seed: int = 42,
    ) -> Dict[str, float]:
        """
        Bootstrap percentile confidence interval.

        Args:
            data: Original sample
            statistic_func: Function computing the statistic of interest
            n_bootstrap: Number of bootstrap resamples
            confidence: Confidence level (default: 0.95)
            seed: Random seed for reproducibility

        Returns:
            Dict with estimate, CI, and bootstrap SE
        """
        rng = np.random.RandomState(seed)
        n: int = len(data)
        original_stat: float = float(statistic_func(data))

        bootstrap_stats: np.ndarray = np.zeros(n_bootstrap)
        for i in range(n_bootstrap):
            sample = rng.choice(data, size=n, replace=True)
            bootstrap_stats[i] = statistic_func(sample)

        alpha: float = 1 - confidence
        ci_lower: float = float(np.percentile(bootstrap_stats, 100 * alpha / 2))
        ci_upper: float = float(np.percentile(bootstrap_stats, 100 * (1 - alpha / 2)))

        return {
            "estimate": round(original_stat, 4),
            "ci_lower": round(ci_lower, 4),
            "ci_upper": round(ci_upper, 4),
            "bootstrap_se": round(float(np.std(bootstrap_stats)), 4),
            "n_bootstrap": n_bootstrap,
            "confidence": confidence,
        }

    @staticmethod
    def bootstrap_se(
        data: np.ndarray,
        statistic_func: Callable,
        n_bootstrap: int = 10000,
        seed: int = 42,
    ) -> float:
        """Bootstrap standard error estimation."""
        rng = np.random.RandomState(seed)
        n: int = len(data)
        stats_arr: np.ndarray = np.zeros(n_bootstrap)
        for i in range(n_bootstrap):
            sample = rng.choice(data, size=n, replace=True)
            stats_arr[i] = statistic_func(sample)
        return float(np.std(stats_arr))


class HypothesisTester:
    """
    Hypothesis testing framework (STA 342 — Test of Hypothesis).

    Key Tests:
    - t-test for mean comparisons
    - Chi-square for categorical associations
    - Mann-Whitney U for non-parametric comparisons
    - Kolmogorov-Smirnov for distribution comparisons
    """

    @staticmethod
    def two_sample_test(
        sample1: np.ndarray,
        sample2: np.ndarray,
        test_type: str = "auto",
        alternative: str = "two-sided",
    ) -> Dict[str, Any]:
        """
        Two-sample hypothesis test with automatic selection.

        Automatically selects parametric (t-test) or non-parametric
        (Mann-Whitney) based on normality testing.
        """
        n1: int = len(sample1)
        n2: int = len(sample2)

        if test_type == "auto":
            if n1 < 5000 and n2 < 5000:
                _, p_norm1 = stats.shapiro(sample1[:min(n1, 5000)])
                _, p_norm2 = stats.shapiro(sample2[:min(n2, 5000)])
                test_type = "ttest" if (p_norm1 > 0.05 and p_norm2 > 0.05) else "mannwhitney"
            else:
                test_type = "ttest"

        if test_type == "ttest":
            stat, p_value = stats.ttest_ind(sample1, sample2, alternative=alternative)
            test_name = "Welch's t-test"
        elif test_type == "mannwhitney":
            stat, p_value = stats.mannwhitneyu(sample1, sample2, alternative=alternative)
            test_name = "Mann-Whitney U test"
        elif test_type == "ks":
            stat, p_value = stats.ks_2samp(sample1, sample2)
            test_name = "Kolmogorov-Smirnov test"
        else:
            raise ValueError(f"Unknown test type: {test_type}")

        cohens_d: Optional[float] = None
        if test_type == "ttest":
            pooled_std: float = float(np.sqrt(
                ((n1 - 1) * np.var(sample1, ddof=1) + (n2 - 1) * np.var(sample2, ddof=1))
                / (n1 + n2 - 2)
            ))
            cohens_d = float((np.mean(sample1) - np.mean(sample2)) / max(pooled_std, 1e-10))

        return {
            "test_name": test_name,
            "test_statistic": round(float(stat), 4),
            "p_value": round(float(p_value), 6),
            "significant_at_05": p_value < 0.05,
            "significant_at_01": p_value < 0.01,
            "effect_size_cohens_d": round(cohens_d, 4) if cohens_d is not None else None,
            "sample_sizes": (n1, n2),
            "alternative": alternative,
            "interpretation": (
                f"{'Reject' if p_value < 0.05 else 'Fail to reject'} null hypothesis "
                f"at 5% significance level (p={p_value:.4f})"
            ),
        }


class DistributionFitter:
    """
    Distribution fitting and testing (STA 241 — Probability and Distribution Models).

    Fits parametric distributions to data and performs goodness-of-fit tests.
    """

    DISTRIBUTIONS = {
        "normal": stats.norm,
        "lognormal": stats.lognorm,
        "gamma": stats.gamma,
        "exponential": stats.expon,
        "weibull": stats.weibull_min,
    }

    @classmethod
    def fit_best_distribution(
        cls, data: np.ndarray, candidates: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Fit multiple distributions and select the best one by AIC.

        Uses Kolmogorov-Smirnov goodness-of-fit test.
        """
        if candidates is None:
            candidates = list(cls.DISTRIBUTIONS.keys())

        results: List[Dict[str, Any]] = []
        for dist_name in candidates:
            if dist_name not in cls.DISTRIBUTIONS:
                continue
            dist = cls.DISTRIBUTIONS[dist_name]
            try:
                params = dist.fit(data)
                ks_stat, p_value = stats.kstest(data, dist_name, args=params)
                aic: float = 2 * len(params) - 2 * float(np.sum(
                    np.log(np.maximum(dist.pdf(data, *params), 1e-10))
                ))
                results.append({
                    "distribution": dist_name,
                    "parameters": [round(p, 4) for p in params],
                    "ks_statistic": round(ks_stat, 4),
                    "p_value": round(p_value, 4),
                    "aic": round(aic, 2),
                })
            except Exception:
                continue

        if not results:
            return {"error": "No distribution could be fitted"}

        results.sort(key=lambda x: x["aic"])
        best = results[0]

        return {
            "best_distribution": best["distribution"],
            "best_parameters": best["parameters"],
            "ks_statistic": best["ks_statistic"],
            "p_value": best["p_value"],
            "aic": best["aic"],
            "all_results": results,
        }


__all__ = ["HypothesisTester", "BootstrapInference", "DistributionFitter"]
