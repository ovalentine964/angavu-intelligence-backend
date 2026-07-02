"""
Nonparametric Analyzer — STA 444: Non-Parametric Methods

Maps STA 444 (Non-Parametric Methods) course unit into executable
distribution-free statistical testing capabilities.

Capabilities:
- Mann-Whitney U test (two-sample comparison)
- Kruskal-Wallis test (multi-sample comparison)
- Kolmogorov-Smirnov test (distribution comparison)
- Wilcoxon signed-rank test (paired comparison)
- Bootstrap inference
- Kernel density estimation

Theoretical Foundations:
- Rank-based statistics (no distributional assumptions)
- Asymptotic relative efficiency
- Permutation tests
- Bootstrap methods (Efron, 1979)

Wired into: AnalysisAgent
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import structlog
from scipy import stats

from app.skills.base import BaseSkill, SkillResult

logger = structlog.get_logger(__name__)


class NonparametricAnalyzer(BaseSkill):
    """
    STA 444 — Non-Parametric Methods

    Provides distribution-free statistical tests for comparing groups,
    testing distributions, and making inferences without normality assumptions.
    """

    def __init__(self):
        super().__init__(
            name="nonparametric_analyzer",
            course_unit="STA 444 — Non-Parametric Methods",
            description=(
                "Mann-Whitney U, Kruskal-Wallis, Kolmogorov-Smirnov tests "
                "and bootstrap inference for distribution-free analysis."
            ),
            version="1.0.0",
            agent_bindings=["IntelligenceGenerator"],
        )

    async def execute(self, action: str, **kwargs) -> SkillResult:
        actions = {
            "mann_whitney": self._mann_whitney,
            "kruskal_wallis": self._kruskal_wallis,
            "kolmogorov_smirnov": self._kolmogorov_smirnov,
            "wilcoxon": self._wilcoxon,
            "bootstrap_ci": self._bootstrap_ci,
            "kde": self._kde,
            "auto_test": self._auto_test,
        }

        if action not in actions:
            return SkillResult(
                success=False,
                skill_name=self.name,
                error=f"Unknown action: {action}. Available: {list(actions.keys())}",
            )

        try:
            data = await actions[action](**kwargs)
            return SkillResult(
                success=True,
                skill_name=self.name,
                data=data,
                confidence=data.get("_confidence", 0.85),
            )
        except Exception as exc:
            return SkillResult(
                success=False,
                skill_name=self.name,
                error=str(exc),
            )

    async def _mann_whitney(
        self,
        sample1: List[float],
        sample2: List[float],
        alternative: str = "two-sided",
    ) -> Dict[str, Any]:
        """
        Mann-Whitney U test (Wilcoxon rank-sum test).

        Non-parametric alternative to the two-sample t-test.
        Tests whether two independent samples come from the same
        distribution (or whether one tends to have larger values).

        H₀: The distributions of both groups are equal
        H₁: The distributions differ (or one is stochastically larger)

        Args:
            sample1: First sample
            sample2: Second sample
            alternative: 'two-sided', 'greater', 'less'

        Returns:
            Dict with U statistic, p-value, effect size, interpretation
        """
        s1 = np.array(sample1, dtype=float)
        s2 = np.array(sample2, dtype=float)
        n1, n2 = len(s1), len(s2)

        if n1 < 2 or n2 < 2:
            return {"error": "Need at least 2 observations per sample"}

        stat, p_value = stats.mannwhitneyu(s1, s2, alternative=alternative)

        # Effect size (rank-biserial correlation)
        U = float(stat)
        r = 1 - (2 * U) / (n1 * n2)

        # Median difference
        median_diff = float(np.median(s1) - np.median(s2))

        # Common language effect size
        cles = U / (n1 * n2)

        return {
            "test": "Mann-Whitney U",
            "U_statistic": round(U, 4),
            "p_value": round(float(p_value), 6),
            "significant_at_05": p_value < 0.05,
            "significant_at_01": p_value < 0.01,
            "effect_size_r": round(r, 4),
            "effect_size_interpretation": (
                "negligible" if abs(r) < 0.1
                else "small" if abs(r) < 0.3
                else "medium" if abs(r) < 0.5
                else "large"
            ),
            "common_language_effect_size": round(cles, 4),
            "median_difference": round(median_diff, 4),
            "sample_sizes": (n1, n2),
            "alternative": alternative,
            "_confidence": 0.9,
        }

    async def _kruskal_wallis(
        self,
        samples: List[List[float]],
        group_names: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Kruskal-Wallis H test.

        Non-parametric alternative to one-way ANOVA.
        Tests whether multiple independent samples come from
        the same distribution.

        H₀: All groups have the same distribution
        H₁: At least one group differs

        Args:
            samples: List of samples (one per group)
            group_names: Optional group labels

        Returns:
            Dict with H statistic, p-value, pairwise comparisons
        """
        arrays = [np.array(s, dtype=float) for s in samples]
        k = len(arrays)

        if k < 2:
            return {"error": "Need at least 2 groups"}
        if any(len(a) < 2 for a in arrays):
            return {"error": "Need at least 2 observations per group"}

        stat, p_value = stats.kruskal(*arrays)

        # Effect size (epsilon-squared)
        N = sum(len(a) for a in arrays)
        epsilon_sq = (stat - k + 1) / (N - k) if N > k else 0

        # Pairwise Mann-Whitney (post-hoc)
        if group_names is None:
            group_names = [f"Group_{i+1}" for i in range(k)]

        pairwise = []
        for i in range(k):
            for j in range(i + 1, k):
                u_stat, u_p = stats.mannwhitneyu(arrays[i], arrays[j], alternative="two-sided")
                # Bonferroni correction
                n_comparisons = k * (k - 1) / 2
                corrected_p = min(float(u_p) * n_comparisons, 1.0)
                pairwise.append({
                    "group_1": group_names[i],
                    "group_2": group_names[j],
                    "U_statistic": round(float(u_stat), 4),
                    "p_value": round(float(u_p), 6),
                    "p_value_bonferroni": round(corrected_p, 6),
                    "significant": corrected_p < 0.05,
                })

        group_stats = []
        for i, (arr, name) in enumerate(zip(arrays, group_names)):
            group_stats.append({
                "group": name,
                "n": len(arr),
                "median": round(float(np.median(arr)), 4),
                "mean_rank": None,  # Computed by scipy internally
            })

        return {
            "test": "Kruskal-Wallis H",
            "H_statistic": round(float(stat), 4),
            "p_value": round(float(p_value), 6),
            "significant_at_05": p_value < 0.05,
            "effect_size_epsilon_sq": round(float(epsilon_sq), 4),
            "n_groups": k,
            "total_n": N,
            "group_stats": group_stats,
            "pairwise_comparisons": pairwise,
            "_confidence": 0.9,
        }

    async def _kolmogorov_smirnov(
        self,
        sample1: List[float],
        sample2: List[float],
    ) -> Dict[str, Any]:
        """
        Kolmogorov-Smirnov two-sample test.

        Tests whether two samples come from the same distribution.
        Based on the maximum difference between empirical CDFs.

        D = sup_x |F₁(x) - F₂(x)|

        More general than t-test or Mann-Whitney: detects any
        distributional difference (location, scale, shape).

        Args:
            sample1: First sample
            sample2: Second sample

        Returns:
            Dict with D statistic, p-value, interpretation
        """
        s1 = np.array(sample1, dtype=float)
        s2 = np.array(sample2, dtype=float)

        stat, p_value = stats.ks_2samp(s1, s2)

        # Compute ECDF difference at each point for visualization
        all_values = np.sort(np.concatenate([s1, s2]))
        ecdf1 = np.searchsorted(np.sort(s1), all_values, side='right') / len(s1)
        ecdf2 = np.searchsorted(np.sort(s2), all_values, side='right') / len(s2)
        diffs = np.abs(ecdf1 - ecdf2)
        max_diff_idx = int(np.argmax(diffs))

        return {
            "test": "Kolmogorov-Smirnov",
            "D_statistic": round(float(stat), 4),
            "p_value": round(float(p_value), 6),
            "significant_at_05": p_value < 0.05,
            "significant_at_01": p_value < 0.01,
            "max_difference_at": round(float(all_values[max_diff_idx]), 4),
            "sample_sizes": (len(s1), len(s2)),
            "interpretation": (
                "Samples come from different distributions" if p_value < 0.05
                else "No significant difference detected"
            ),
            "_confidence": 0.9,
        }

    async def _wilcoxon(
        self,
        sample1: List[float],
        sample2: List[float],
        alternative: str = "two-sided",
    ) -> Dict[str, Any]:
        """
        Wilcoxon signed-rank test for paired samples.

        Non-parametric alternative to the paired t-test.
        Tests whether the median difference is zero.

        Args:
            sample1: First sample (before)
            sample2: Second sample (after)
            alternative: 'two-sided', 'greater', 'less'

        Returns:
            Dict with test statistic, p-value, effect size
        """
        s1 = np.array(sample1, dtype=float)
        s2 = np.array(sample2, dtype=float)

        if len(s1) != len(s2):
            return {"error": "Samples must have equal length for paired test"}

        diff = s2 - s1
        diff = diff[diff != 0]  # Remove zeros

        if len(diff) < 2:
            return {"error": "Need at least 2 non-zero differences"}

        stat, p_value = stats.wilcoxon(s1, s2, alternative=alternative)

        # Effect size (matched-pairs rank-biserial correlation)
        n = len(diff)
        r = float(stat) / (n * (n + 1) / 2) if n > 0 else 0

        return {
            "test": "Wilcoxon signed-rank",
            "W_statistic": round(float(stat), 4),
            "p_value": round(float(p_value), 6),
            "significant_at_05": p_value < 0.05,
            "median_difference": round(float(np.median(diff)), 4),
            "mean_difference": round(float(np.mean(diff)), 4),
            "n_pairs": len(s1),
            "n_nonzero": len(diff),
            "alternative": alternative,
            "_confidence": 0.9,
        }

    async def _bootstrap_ci(
        self,
        data: List[float],
        statistic: str = "mean",
        n_bootstrap: int = 10000,
        confidence: float = 0.95,
    ) -> Dict[str, Any]:
        """
        Bootstrap confidence interval.

        Distribution-free confidence interval using resampling.

        Args:
            data: Observed data
            statistic: 'mean', 'median', 'std', 'proportion'
            n_bootstrap: Number of bootstrap samples
            confidence: Confidence level

        Returns:
            Dict with estimate, CI, bootstrap SE
        """
        from app.services.statistical_foundation import BootstrapInference

        arr = np.array(data, dtype=float)

        stat_funcs = {
            "mean": np.mean,
            "median": np.median,
            "std": np.std,
            "proportion": lambda x: np.mean(x > 0),
        }

        stat_func = stat_funcs.get(statistic, np.mean)

        result = BootstrapInference.percentile_ci(
            arr, stat_func,
            n_bootstrap=n_bootstrap,
            confidence=confidence,
        )

        result["_confidence"] = confidence
        return result

    async def _kde(
        self,
        data: List[float],
        n_points: int = 100,
    ) -> Dict[str, Any]:
        """
        Kernel Density Estimation.

        Non-parametric estimation of the probability density function.

        Args:
            data: Observed data
            n_points: Number of evaluation points

        Returns:
            Dict with grid points, density estimates, multimodality test
        """
        from app.services.statistical_foundation import KernelDensityEstimator

        arr = np.array(data, dtype=float)
        points, density = KernelDensityEstimator.gaussian_kde(arr)

        multimodality = KernelDensityEstimator.detect_multimodality(arr)

        return {
            "grid_points": [round(float(v), 4) for v in points[::max(1, len(points) // n_points)]],
            "density": [round(float(v), 6) for v in density[::max(1, len(density) // n_points)]],
            "multimodality": multimodality,
            "n_data_points": len(arr),
            "_confidence": 0.85,
        }

    async def _auto_test(
        self,
        sample1: List[float],
        sample2: Optional[List[float]] = None,
        paired: bool = False,
    ) -> Dict[str, Any]:
        """
        Automatically select and run the appropriate non-parametric test.

        Selection logic:
        - Paired samples → Wilcoxon signed-rank
        - Two independent samples → Mann-Whitney U
        - KS test always included as a robustness check

        Args:
            sample1: First sample
            sample2: Second sample (optional, for two-sample tests)
            paired: Whether samples are paired

        Returns:
            Dict with test results and recommendation
        """
        s1 = np.array(sample1, dtype=float)

        if sample2 is None:
            # One-sample: just descriptive + bootstrap CI
            ci_result = await self._bootstrap_ci(sample1)
            return {
                "test_type": "one_sample",
                "descriptives": {
                    "n": len(s1),
                    "median": round(float(np.median(s1)), 4),
                    "mean": round(float(np.mean(s1)), 4),
                    "iqr": round(float(np.percentile(s1, 75) - np.percentile(s1, 25)), 4),
                },
                "bootstrap_ci": ci_result,
                "_confidence": 0.85,
            }

        s2 = np.array(sample2, dtype=float)

        results = {}

        if paired:
            if len(s1) != len(s2):
                return {"error": "Paired test requires equal-length samples"}
            wilcoxon_result = await self._wilcoxon(sample1, sample2)
            results["wilcoxon"] = wilcoxon_result
            results["recommended_test"] = "Wilcoxon signed-rank"
        else:
            mw_result = await self._mann_whitney(sample1, sample2)
            results["mann_whitney"] = mw_result
            results["recommended_test"] = "Mann-Whitney U"

        # Always include KS as robustness check
        ks_result = await self._kolmogorov_smirnov(sample1, sample2)
        results["kolmogorov_smirnov"] = ks_result

        # Agreement check
        if paired:
            primary_p = results.get("wilcoxon", {}).get("p_value", 1.0)
        else:
            primary_p = results.get("mann_whitney", {}).get("p_value", 1.0)
        ks_p = ks_result.get("p_value", 1.0)

        results["tests_agree"] = (primary_p < 0.05) == (ks_p < 0.05)

        results["_confidence"] = 0.85
        return results
