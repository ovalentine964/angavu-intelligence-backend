"""
Hypothesis Testing Framework — STA 342.

Implements:
- Significance tests for all intelligence products
- Multiple testing correction (Bonferroni, Benjamini-Hochberg FDR, Holm)
- Statistical significance reporting for buyers
- Power analysis for sample size calculations

From STA 342 (Test of Hypothesis):
- §7.1: Fundamentals (H₀, H₁, Type I/II errors, p-values)
- §7.2: Neyman-Pearson Lemma (most powerful tests)
- §7.3: Common tests (z, t, chi-square, F, proportion)
- §7.6: Non-parametric tests (Mann-Whitney, Wilcoxon, Kruskal-Wallis)
- §7.7: Power analysis and sample size
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import structlog
from scipy import stats as sp_stats

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestType(str, Enum):
    """Types of hypothesis tests."""
    ONE_SAMPLE_T = "one_sample_t"
    TWO_SAMPLE_T = "two_sample_t"
    PAIRED_T = "paired_t"
    WELCH_T = "welch_t"
    MANN_WHITNEY_U = "mann_whitney_u"
    WILCOXON = "wilcoxon"
    KRUSKAL_WALLIS = "kruskal_wallis"
    CHI_SQUARE = "chi_square"
    PROPORTION_Z = "proportion_z"
    ONE_WAY_ANOVA = "one_way_anova"


class CorrectionMethod(str, Enum):
    """Multiple testing correction methods (STA 342 §7.3)."""
    BONFERRONI = "bonferroni"
    HOLM = "holm"
    BENJAMINI_HOCHBERG = "benjamini_hochberg"  # FDR
    BENJAMINI_YEKUTIELI = "benjamini_yekutieli"


@dataclass
class HypothesisTestResult:
    """Result of a single hypothesis test."""
    test_type: TestType
    test_statistic: float
    p_value: float
    alpha: float
    reject_null: bool
    effect_size: Optional[float] = None
    confidence_interval: Optional[Tuple[float, float]] = None
    power: Optional[float] = None
    sample_size: int = 0
    null_hypothesis: str = ""
    alternative_hypothesis: str = ""
    interpretation: str = ""
    correction_applied: Optional[str] = None
    adjusted_p_value: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_type": self.test_type.value,
            "test_statistic": round(self.test_statistic, 6),
            "p_value": round(self.p_value, 8),
            "alpha": self.alpha,
            "reject_null": self.reject_null,
            "effect_size": round(self.effect_size, 4) if self.effect_size else None,
            "confidence_interval": (
                [round(self.confidence_interval[0], 4),
                 round(self.confidence_interval[1], 4)]
                if self.confidence_interval else None
            ),
            "power": round(self.power, 4) if self.power else None,
            "sample_size": self.sample_size,
            "null_hypothesis": self.null_hypothesis,
            "alternative_hypothesis": self.alternative_hypothesis,
            "interpretation": self.interpretation,
            "correction_applied": self.correction_applied,
            "adjusted_p_value": (
                round(self.adjusted_p_value, 8)
                if self.adjusted_p_value else None
            ),
        }


@dataclass
class SignificanceReport:
    """Aggregated significance report for an intelligence product."""
    product_name: str
    generated_at: datetime
    tests: List[HypothesisTestResult]
    overall_significant: bool
    summary: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "product": self.product_name,
            "generated_at": self.generated_at.isoformat(),
            "total_tests": len(self.tests),
            "significant_tests": sum(1 for t in self.tests if t.reject_null),
            "overall_significant": self.overall_significant,
            "summary": self.summary,
            "tests": [t.to_dict() for t in self.tests],
        }


# ---------------------------------------------------------------------------
# Multiple Testing Correction (STA 342 §7.3)
# ---------------------------------------------------------------------------

class MultipleTestingCorrection:
    """
    Multiple testing correction methods.

    When testing m hypotheses simultaneously, the family-wise error rate
    (FWER) increases. These methods control for that.

    From STA 342:
    - Bonferroni: α/m for each test → controls FWER but conservative
    - Holm: Step-down procedure, uniformly more powerful than Bonferroni
    - Benjamini-Hochberg: Controls FDR (expected proportion of false rejections)
    """

    @staticmethod
    def bonferroni(p_values: List[float]) -> List[float]:
        """
        Bonferroni correction: adjusted_p = min(p * m, 1.0).

        Controls FWER at α. Most conservative method.
        """
        m = len(p_values)
        return [min(p * m, 1.0) for p in p_values]

    @staticmethod
    def holm(p_values: List[float]) -> List[float]:
        """
        Holm's step-down procedure.

        Uniformly more powerful than Bonferroni while still controlling FWER.
        """
        m = len(p_values)
        indexed = sorted(enumerate(p_values), key=lambda x: x[1])
        adjusted = [0.0] * m

        for rank, (idx, p) in enumerate(indexed):
            adjusted[idx] = min(p * (m - rank), 1.0)

        # Ensure monotonicity (step-down)
        sorted_adjusted = sorted(
            [(idx, adjusted[idx]) for idx in range(m)],
            key=lambda x: p_values[x[0]],
        )
        for i in range(1, m):
            prev_idx = sorted_adjusted[i - 1][0]
            curr_idx = sorted_adjusted[i][0]
            adjusted[curr_idx] = max(adjusted[curr_idx], adjusted[prev_idx])

        return adjusted

    @staticmethod
    def benjamini_hochberg(p_values: List[float]) -> List[float]:
        """
        Benjamini-Hochberg FDR correction.

        Controls the False Discovery Rate (expected proportion of
        false rejections among all rejections). Less conservative
        than FWER methods.
        """
        m = len(p_values)
        indexed = sorted(enumerate(p_values), key=lambda x: x[1])
        adjusted = [0.0] * m

        for rank, (idx, p) in enumerate(indexed):
            adjusted[idx] = min(p * m / (rank + 1), 1.0)

        # Ensure monotonicity (step-up)
        sorted_adjusted = sorted(
            [(idx, adjusted[idx]) for idx in range(m)],
            key=lambda x: p_values[x[0]],
        )
        for i in range(m - 2, -1, -1):
            next_idx = sorted_adjusted[i + 1][0]
            curr_idx = sorted_adjusted[i][0]
            adjusted[curr_idx] = min(adjusted[curr_idx], adjusted[next_idx])

        return adjusted

    @staticmethod
    def benjamini_yekutieli(p_values: List[float]) -> List[float]:
        """
        Benjamini-Yekutieli correction.

        Controls FDR under arbitrary dependence.
        More conservative than BH but valid without independence assumption.
        """
        m = len(p_values)
        c_m = sum(1.0 / i for i in range(1, m + 1))  # Harmonic number
        indexed = sorted(enumerate(p_values), key=lambda x: x[1])
        adjusted = [0.0] * m

        for rank, (idx, p) in enumerate(indexed):
            adjusted[idx] = min(p * m * c_m / (rank + 1), 1.0)

        return adjusted

    @classmethod
    def apply(
        cls,
        p_values: List[float],
        method: CorrectionMethod = CorrectionMethod.BENJAMINI_HOCHBERG,
    ) -> List[float]:
        """Apply the specified correction method."""
        if method == CorrectionMethod.BONFERRONI:
            return cls.bonferroni(p_values)
        elif method == CorrectionMethod.HOLM:
            return cls.holm(p_values)
        elif method == CorrectionMethod.BENJAMINI_HOCHBERG:
            return cls.benjamini_hochberg(p_values)
        elif method == CorrectionMethod.BENJAMINI_YEKUTIELI:
            return cls.benjamini_yekutieli(p_values)
        else:
            raise ValueError(f"Unknown correction method: {method}")


# ---------------------------------------------------------------------------
# Hypothesis Tester
# ---------------------------------------------------------------------------

class HypothesisTester:
    """
    Comprehensive hypothesis testing for Biashara Intelligence.

    From STA 342 (Test of Hypothesis):
    - One-sample, two-sample, paired t-tests
    - Non-parametric alternatives (Mann-Whitney, Wilcoxon, Kruskal-Wallis)
    - Chi-square tests for independence
    - Proportion tests
    - Effect size computation (Cohen's d)
    - Power analysis

    Usage:
        tester = HypothesisTester(alpha=0.05)

        # Compare two groups
        result = tester.two_sample_t_test(group_a, group_b)

        # Non-parametric comparison
        result = tester.mann_whitney_u(group_a, group_b)

        # Multiple testing correction
        corrected = tester.correct_multiple(p_values, method="fdr")
    """

    def __init__(self, alpha: float = 0.05):
        self.alpha = alpha

    # -----------------------------------------------------------------------
    # Parametric Tests (STA 342 §7.3)
    # -----------------------------------------------------------------------

    def one_sample_t_test(
        self,
        sample: List[float],
        null_mean: float,
        alternative: str = "two-sided",
    ) -> HypothesisTestResult:
        """
        One-sample t-test.

        H₀: μ = null_mean
        H₁: μ ≠ null_mean (two-sided), μ > null_mean (greater), μ < null_mean (less)

        From STA 342: t = (X̄ - μ₀) / (S/√n)
        """
        arr = np.array(sample)
        n = len(arr)
        if n < 2:
            return self._insufficient_data(TestType.ONE_SAMPLE_T, n)

        t_stat, p_val = sp_stats.ttest_1samp(arr, null_mean, alternative=alternative)

        # Effect size: Cohen's d
        mean_diff = float(np.mean(arr)) - null_mean
        std = float(np.std(arr, ddof=1))
        cohens_d = mean_diff / std if std > 0 else 0.0

        # Confidence interval
        se = std / math.sqrt(n)
        t_crit = sp_stats.t.ppf(1 - self.alpha / 2, n - 1)
        ci = (mean_diff - t_crit * se, mean_diff + t_crit * se)

        # Power
        power = self._compute_power_one_sample(n, cohens_d, self.alpha)

        return HypothesisTestResult(
            test_type=TestType.ONE_SAMPLE_T,
            test_statistic=float(t_stat),
            p_value=float(p_val),
            alpha=self.alpha,
            reject_null=p_val < self.alpha,
            effect_size=cohens_d,
            confidence_interval=ci,
            power=power,
            sample_size=n,
            null_hypothesis=f"μ = {null_mean}",
            alternative_hypothesis=f"μ {'≠' if alternative == 'two-sided' else '>' if alternative == 'greater' else '<'} {null_mean}",
            interpretation=self._interpret_result(p_val, self.alpha, cohens_d),
        )

    def two_sample_t_test(
        self,
        sample_a: List[float],
        sample_b: List[float],
        equal_var: bool = False,
    ) -> HypothesisTestResult:
        """
        Independent two-sample t-test (Welch's by default).

        H₀: μ_A = μ_B
        H₁: μ_A ≠ μ_B

        From STA 342: Welch's t-test for unequal variances.
        """
        a = np.array(sample_a)
        b = np.array(sample_b)
        n_a, n_b = len(a), len(b)

        if n_a < 2 or n_b < 2:
            return self._insufficient_data(TestType.TWO_SAMPLE_T, n_a + n_b)

        t_stat, p_val = sp_stats.ttest_ind(a, b, equal_var=equal_var)

        # Effect size: Cohen's d
        pooled_std = math.sqrt(
            ((n_a - 1) * np.var(a, ddof=1) + (n_b - 1) * np.var(b, ddof=1))
            / (n_a + n_b - 2)
        )
        cohens_d = (float(np.mean(a)) - float(np.mean(b))) / pooled_std if pooled_std > 0 else 0.0

        # Confidence interval for difference
        diff = float(np.mean(a)) - float(np.mean(b))
        se = pooled_std * math.sqrt(1 / n_a + 1 / n_b)
        df = n_a + n_b - 2
        t_crit = sp_stats.t.ppf(1 - self.alpha / 2, df)
        ci = (diff - t_crit * se, diff + t_crit * se)

        # Power
        power = self._compute_power_two_sample(n_a, n_b, cohens_d, self.alpha)

        test_type = TestType.TWO_SAMPLE_T if equal_var else TestType.WELCH_T

        return HypothesisTestResult(
            test_type=test_type,
            test_statistic=float(t_stat),
            p_value=float(p_val),
            alpha=self.alpha,
            reject_null=p_val < self.alpha,
            effect_size=cohens_d,
            confidence_interval=ci,
            power=power,
            sample_size=n_a + n_b,
            null_hypothesis="μ_A = μ_B",
            alternative_hypothesis="μ_A ≠ μ_B",
            interpretation=self._interpret_result(p_val, self.alpha, cohens_d),
        )

    def paired_t_test(
        self,
        before: List[float],
        after: List[float],
    ) -> HypothesisTestResult:
        """
        Paired t-test (before/after comparison).

        H₀: μ_diff = 0
        H₁: μ_diff ≠ 0

        From STA 342: t = D̄ / (S_D/√n)
        """
        a = np.array(before)
        b = np.array(after)
        n = len(a)

        if n < 2 or len(b) < 2:
            return self._insufficient_data(TestType.PAIRED_T, n)

        t_stat, p_val = sp_stats.ttest_rel(a, b)

        diff = b - a
        mean_diff = float(np.mean(diff))
        std_diff = float(np.std(diff, ddof=1))
        cohens_d = mean_diff / std_diff if std_diff > 0 else 0.0

        se = std_diff / math.sqrt(n)
        t_crit = sp_stats.t.ppf(1 - self.alpha / 2, n - 1)
        ci = (mean_diff - t_crit * se, mean_diff + t_crit * se)

        power = self._compute_power_one_sample(n, cohens_d, self.alpha)

        return HypothesisTestResult(
            test_type=TestType.PAIRED_T,
            test_statistic=float(t_stat),
            p_value=float(p_val),
            alpha=self.alpha,
            reject_null=p_val < self.alpha,
            effect_size=cohens_d,
            confidence_interval=ci,
            power=power,
            sample_size=n,
            null_hypothesis="μ_diff = 0",
            alternative_hypothesis="μ_diff ≠ 0",
            interpretation=self._interpret_result(p_val, self.alpha, cohens_d),
        )

    # -----------------------------------------------------------------------
    # Non-Parametric Tests (STA 342 §7.6)
    # -----------------------------------------------------------------------

    def mann_whitney_u(
        self,
        sample_a: List[float],
        sample_b: List[float],
        alternative: str = "two-sided",
    ) -> HypothesisTestResult:
        """
        Mann-Whitney U test (non-parametric alternative to two-sample t-test).

        From STA 342: Tests whether two distributions are the same.
        No normality assumption required.
        ARE vs t-test: 3/π ≈ 0.955 for normal data, >1 for heavy-tailed.
        """
        a = np.array(sample_a)
        b = np.array(sample_b)
        n_a, n_b = len(a), len(b)

        if n_a < 2 or n_b < 2:
            return self._insufficient_data(TestType.MANN_WHITNEY_U, n_a + n_b)

        u_stat, p_val = sp_stats.mannwhitneyu(a, b, alternative=alternative)

        # Effect size: rank-biserial correlation
        n_total = n_a + n_b
        effect_size = 1 - (2 * u_stat) / (n_a * n_b)

        return HypothesisTestResult(
            test_type=TestType.MANN_WHITNEY_U,
            test_statistic=float(u_stat),
            p_value=float(p_val),
            alpha=self.alpha,
            reject_null=p_val < self.alpha,
            effect_size=float(effect_size),
            sample_size=n_total,
            null_hypothesis="Distributions of A and B are the same",
            alternative_hypothesis="Distributions of A and B differ",
            interpretation=self._interpret_result(p_val, self.alpha, effect_size),
        )

    def wilcoxon_signed_rank(
        self,
        before: List[float],
        after: List[float],
    ) -> HypothesisTestResult:
        """
        Wilcoxon signed-rank test (non-parametric paired test).

        From STA 342: Non-parametric alternative to paired t-test.
        Uses ranks of absolute differences.
        """
        a = np.array(before)
        b = np.array(after)
        n = len(a)

        if n < 2:
            return self._insufficient_data(TestType.WILCOXON, n)

        stat, p_val = sp_stats.wilcoxon(a, b)

        # Effect size: r = Z / √N
        z_score = sp_stats.norm.ppf(1 - p_val / 2) if p_val > 0 else 0
        effect_size = z_score / math.sqrt(n) if n > 0 else 0

        return HypothesisTestResult(
            test_type=TestType.WILCOXON,
            test_statistic=float(stat),
            p_value=float(p_val),
            alpha=self.alpha,
            reject_null=p_val < self.alpha,
            effect_size=float(effect_size),
            sample_size=n,
            null_hypothesis="Median difference = 0",
            alternative_hypothesis="Median difference ≠ 0",
            interpretation=self._interpret_result(p_val, self.alpha, effect_size),
        )

    def kruskal_wallis(
        self,
        groups: List[List[float]],
    ) -> HypothesisTestResult:
        """
        Kruskal-Wallis test (non-parametric ANOVA).

        From STA 342: Tests whether multiple groups come from
        the same distribution. No normality assumption.
        """
        arrays = [np.array(g) for g in groups]
        n_total = sum(len(a) for a in arrays)

        if any(len(a) < 2 for a in arrays):
            return self._insufficient_data(TestType.KRUSKAL_WALLIS, n_total)

        stat, p_val = sp_stats.kruskal(*arrays)

        # Effect size: epsilon-squared
        k = len(groups)
        epsilon_sq = (stat - k + 1) / (n_total - k) if n_total > k else 0

        return HypothesisTestResult(
            test_type=TestType.KRUSKAL_WALLIS,
            test_statistic=float(stat),
            p_value=float(p_val),
            alpha=self.alpha,
            reject_null=p_val < self.alpha,
            effect_size=float(epsilon_sq),
            sample_size=n_total,
            null_hypothesis="All groups have the same distribution",
            alternative_hypothesis="At least one group differs",
            interpretation=self._interpret_result(p_val, self.alpha, epsilon_sq),
        )

    # -----------------------------------------------------------------------
    # Chi-Square & Proportion Tests (STA 342 §7.5)
    # -----------------------------------------------------------------------

    def chi_square_test(
        self,
        observed: List[List[int]],
    ) -> HypothesisTestResult:
        """
        Chi-square test of independence.

        From STA 342: χ² = Σ (Oᵢ - Eᵢ)² / Eᵢ
        """
        obs = np.array(observed)
        n = obs.sum()

        if n < 5:
            return self._insufficient_data(TestType.CHI_SQUARE, int(n))

        chi2, p_val, dof, expected = sp_stats.chi2_contingency(obs)

        # Cramér's V effect size
        k = min(obs.shape) - 1
        cramers_v = math.sqrt(chi2 / (n * k)) if k > 0 and n > 0 else 0

        return HypothesisTestResult(
            test_type=TestType.CHI_SQUARE,
            test_statistic=float(chi2),
            p_value=float(p_val),
            alpha=self.alpha,
            reject_null=p_val < self.alpha,
            effect_size=float(cramers_v),
            sample_size=int(n),
            null_hypothesis="Variables are independent",
            alternative_hypothesis="Variables are associated",
            interpretation=self._interpret_result(p_val, self.alpha, cramers_v),
        )

    def proportion_test(
        self,
        successes_a: int,
        n_a: int,
        successes_b: int,
        n_b: int,
    ) -> HypothesisTestResult:
        """
        Two-proportion z-test.

        From STA 342: z = (p̂₁ - p̂₂) / √(p̂(1-p̂)(1/n₁ + 1/n₂))
        """
        if n_a < 5 or n_b < 5:
            return self._insufficient_data(TestType.PROPORTION_Z, n_a + n_b)

        p_a = successes_a / n_a
        p_b = successes_b / n_b
        p_pool = (successes_a + successes_b) / (n_a + n_b)

        se = math.sqrt(p_pool * (1 - p_pool) * (1 / n_a + 1 / n_b))
        z_stat = (p_a - p_b) / se if se > 0 else 0
        p_val = 2 * (1 - sp_stats.norm.cdf(abs(z_stat)))

        # Effect size: Cohen's h
        h = 2 * (math.asin(math.sqrt(p_a)) - math.asin(math.sqrt(p_b)))

        return HypothesisTestResult(
            test_type=TestType.PROPORTION_Z,
            test_statistic=float(z_stat),
            p_value=float(p_val),
            alpha=self.alpha,
            reject_null=p_val < self.alpha,
            effect_size=float(h),
            sample_size=n_a + n_b,
            null_hypothesis="p_A = p_B",
            alternative_hypothesis="p_A ≠ p_B",
            interpretation=self._interpret_result(p_val, self.alpha, h),
        )

    # -----------------------------------------------------------------------
    # Multiple Testing Correction
    # -----------------------------------------------------------------------

    def correct_multiple(
        self,
        results: List[HypothesisTestResult],
        method: CorrectionMethod = CorrectionMethod.BENJAMINI_HOCHBERG,
    ) -> List[HypothesisTestResult]:
        """
        Apply multiple testing correction to a list of results.

        From STA 342: When testing m hypotheses, FWER/FDR must be controlled.
        """
        p_values = [r.p_value for r in results]
        adjusted = MultipleTestingCorrection.apply(p_values, method)

        for i, result in enumerate(results):
            result.correction_applied = method.value
            result.adjusted_p_value = adjusted[i]
            result.reject_null = adjusted[i] < self.alpha

        return results

    # -----------------------------------------------------------------------
    # Power Analysis (STA 342 §7.7)
    # -----------------------------------------------------------------------

    @staticmethod
    def compute_power_one_sample(
        n: int,
        effect_size: float,
        alpha: float = 0.05,
    ) -> float:
        """
        Power for one-sample t-test.

        From STA 342: Power = P(reject H₀ | H₁ true) = 1 - β
        """
        if n < 2:
            return 0.0
        df = n - 1
        ncp = effect_size * math.sqrt(n)  # Non-centrality parameter
        t_crit = sp_stats.t.ppf(1 - alpha / 2, df)
        power = 1 - sp_stats.nct.cdf(t_crit, df, ncp) + sp_stats.nct.cdf(-t_crit, df, ncp)
        return min(1.0, max(0.0, float(power)))

    @staticmethod
    def compute_power_two_sample(
        n_a: int,
        n_b: int,
        effect_size: float,
        alpha: float = 0.05,
    ) -> float:
        """Power for two-sample t-test."""
        if n_a < 2 or n_b < 2:
            return 0.0
        df = n_a + n_b - 2
        ncp = effect_size * math.sqrt(n_a * n_b / (n_a + n_b))
        t_crit = sp_stats.t.ppf(1 - alpha / 2, df)
        power = 1 - sp_stats.nct.cdf(t_crit, df, ncp) + sp_stats.nct.cdf(-t_crit, df, ncp)
        return min(1.0, max(0.0, float(power)))

    @staticmethod
    def required_sample_size(
        effect_size: float,
        power: float = 0.80,
        alpha: float = 0.05,
        test_type: str = "two_sample",
    ) -> int:
        """
        Compute required sample size for given power.

        From STA 342: n = (z_α + z_β)² × σ² / δ²
        Simplified using Cohen's d: n per group ≈ 2(z_α + z_β)² / d²
        """
        z_alpha = sp_stats.norm.ppf(1 - alpha / 2)
        z_beta = sp_stats.norm.ppf(power)

        if effect_size == 0:
            return 0

        if test_type == "one_sample":
            n = ((z_alpha + z_beta) / effect_size) ** 2
        else:  # two_sample
            n = 2 * ((z_alpha + z_beta) / effect_size) ** 2

        return max(int(math.ceil(n)), 2)

    # -----------------------------------------------------------------------
    # Private Helpers
    # -----------------------------------------------------------------------

    def _compute_power_one_sample(self, n, d, alpha):
        return self.compute_power_one_sample(n, d, alpha)

    def _compute_power_two_sample(self, n_a, n_b, d, alpha):
        return self.compute_power_two_sample(n_a, n_b, d, alpha)

    def _insufficient_data(
        self, test_type: TestType, n: int
    ) -> HypothesisTestResult:
        return HypothesisTestResult(
            test_type=test_type,
            test_statistic=0.0,
            p_value=1.0,
            alpha=self.alpha,
            reject_null=False,
            sample_size=n,
            interpretation="Insufficient data for test",
        )

    @staticmethod
    def _interpret_result(
        p_value: float, alpha: float, effect_size: float
    ) -> str:
        """Generate plain-language interpretation."""
        if p_value < alpha:
            sig = "statistically significant"
        else:
            sig = "not statistically significant"

        abs_effect = abs(effect_size)
        if abs_effect < 0.2:
            magnitude = "negligible"
        elif abs_effect < 0.5:
            magnitude = "small"
        elif abs_effect < 0.8:
            magnitude = "medium"
        else:
            magnitude = "large"

        return (
            f"Result is {sig} (p={p_value:.4f}, α={alpha}). "
            f"Effect size is {magnitude} (d={effect_size:.3f})."
        )
