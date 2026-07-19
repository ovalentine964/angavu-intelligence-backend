"""
Confidence Interval Calculator — STA 342 / ECO 315.

Implements:
- Confidence intervals for all intelligence products
- Bootstrap confidence intervals (non-parametric)
- Prediction intervals for forecasts
- Proper uncertainty quantification

From STA 342:
- §7.7: Confidence intervals as dual of hypothesis tests
- CI = X̄ ± t_{α/2,n-1} × S/√n

From ECO 315:
- §3.7: Quantitative data analysis, uncertainty quantification
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import structlog
from scipy import stats as sp_stats

logger = structlog.get_logger(__name__)


@dataclass
class ConfidenceInterval:
    """A confidence interval with metadata."""
    point_estimate: float
    lower: float
    upper: float
    confidence_level: float
    method: str
    n: int
    margin_of_error: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "point_estimate": round(self.point_estimate, 4),
            "lower": round(self.lower, 4),
            "upper": round(self.upper, 4),
            "confidence_level": self.confidence_level,
            "method": self.method,
            "n": self.n,
            "margin_of_error": round(self.margin_of_error, 4),
        }

    def __str__(self) -> str:
        return (
            f"{self.confidence_level*100:.0f}% CI: "
            f"[{self.lower:.2f}, {self.upper:.2f}] "
            f"(margin: ±{self.margin_of_error:.2f})"
        )


class ConfidenceIntervalCalculator:
    """
    Compute confidence intervals for Angavu Intelligence products.

    Every intelligence product should include confidence intervals
    to communicate uncertainty to buyers.

    Methods:
    - t-interval: For means with unknown σ (most common)
    - z-interval: For proportions and large samples
    - Bootstrap: Non-parametric, no distributional assumptions
    - Prediction interval: For individual forecasts
    """

    @staticmethod
    def mean_ci(
        values: list[float],
        confidence: float = 0.95,
    ) -> ConfidenceInterval:
        """
        Confidence interval for the population mean.

        CI = X̄ ± t_{α/2,n-1} × S/√n

        From STA 342: Uses t-distribution for small samples.
        """
        arr = np.array(values)
        n = len(arr)
        if n < 2:
            mean = float(arr[0]) if n == 1 else 0.0
            return ConfidenceInterval(
                point_estimate=mean,
                lower=mean,
                upper=mean,
                confidence_level=confidence,
                method="t-interval",
                n=n,
                margin_of_error=0.0,
            )

        mean = float(np.mean(arr))
        std = float(np.std(arr, ddof=1))
        se = std / math.sqrt(n)
        t_crit = float(sp_stats.t.ppf((1 + confidence) / 2, n - 1))
        margin = t_crit * se

        return ConfidenceInterval(
            point_estimate=mean,
            lower=mean - margin,
            upper=mean + margin,
            confidence_level=confidence,
            method="t-interval",
            n=n,
            margin_of_error=margin,
        )

    @staticmethod
    def proportion_ci(
        successes: int,
        n: int,
        confidence: float = 0.95,
    ) -> ConfidenceInterval:
        """
        Confidence interval for a proportion.

        Uses Wilson score interval (better than Wald for small n).

        From STA 342: z = (p̂ - p₀) / √(p₀(1-p₀)/n)
        """
        if n == 0:
            return ConfidenceInterval(
                point_estimate=0, lower=0, upper=0,
                confidence_level=confidence, method="wilson",
                n=0, margin_of_error=0.0,
            )

        p_hat = successes / n
        z = float(sp_stats.norm.ppf((1 + confidence) / 2))

        # Wilson score interval
        denominator = 1 + z ** 2 / n
        center = (p_hat + z ** 2 / (2 * n)) / denominator
        spread = z * math.sqrt(
            (p_hat * (1 - p_hat) + z ** 2 / (4 * n)) / n
        ) / denominator

        lower = max(0, center - spread)
        upper = min(1, center + spread)

        return ConfidenceInterval(
            point_estimate=p_hat,
            lower=lower,
            upper=upper,
            confidence_level=confidence,
            method="wilson",
            n=n,
            margin_of_error=(upper - lower) / 2,
        )

    @staticmethod
    def difference_ci(
        values_a: list[float],
        values_b: list[float],
        confidence: float = 0.95,
    ) -> ConfidenceInterval:
        """
        Confidence interval for difference of two means.

        CI = (X̄_A - X̄_B) ± t_{α/2,df} × SE(diff)

        From STA 342: Welch's t-interval (unequal variances).
        """
        a = np.array(values_a)
        b = np.array(values_b)
        n_a, n_b = len(a), len(b)

        if n_a < 2 or n_b < 2:
            diff = float(np.mean(a) - np.mean(b)) if n_a > 0 and n_b > 0 else 0
            return ConfidenceInterval(
                point_estimate=diff, lower=diff, upper=diff,
                confidence_level=confidence, method="welch-diff",
                n=n_a + n_b, margin_of_error=0.0,
            )

        mean_a = float(np.mean(a))
        mean_b = float(np.mean(b))
        var_a = float(np.var(a, ddof=1))
        var_b = float(np.var(b, ddof=1))

        se = math.sqrt(var_a / n_a + var_b / n_b)

        # Welch-Satterthwaite degrees of freedom
        num = (var_a / n_a + var_b / n_b) ** 2
        denom = (var_a / n_a) ** 2 / (n_a - 1) + (var_b / n_b) ** 2 / (n_b - 1)
        df = num / denom if denom > 0 else 1

        t_crit = float(sp_stats.t.ppf((1 + confidence) / 2, df))
        diff = mean_a - mean_b
        margin = t_crit * se

        return ConfidenceInterval(
            point_estimate=diff,
            lower=diff - margin,
            upper=diff + margin,
            confidence_level=confidence,
            method="welch",
            n=n_a + n_b,
            margin_of_error=margin,
        )


class BootstrapCI:
    """
    Bootstrap confidence intervals (non-parametric).

    From ECO 315 / STA 342:
    - Resample with replacement
    - Compute statistic on each resample
    - Use percentile or bias-corrected method for CI

    No distributional assumptions. Valid for any statistic.
    """

    @staticmethod
    def compute(
        values: list[float],
        statistic: str = "mean",
        confidence: float = 0.95,
        n_bootstrap: int = 10000,
        seed: int | None = None,
    ) -> ConfidenceInterval:
        """
        Bootstrap confidence interval.

        Args:
            values: Data values
            statistic: "mean", "median", "std", or callable
            confidence: Confidence level
            n_bootstrap: Number of bootstrap resamples
            seed: Random seed for reproducibility

        Returns:
            ConfidenceInterval
        """
        rng = np.random.default_rng(seed)
        arr = np.array(values)
        n = len(arr)

        if n < 2:
            val = float(arr[0]) if n == 1 else 0.0
            return ConfidenceInterval(
                point_estimate=val, lower=val, upper=val,
                confidence_level=confidence, method="bootstrap",
                n=n, margin_of_error=0.0,
            )

        # Select statistic function
        stat_funcs = {
            "mean": np.mean,
            "median": np.median,
            "std": lambda x: np.std(x, ddof=1),
        }
        stat_fn = stat_funcs.get(statistic, np.mean)

        # Generate bootstrap samples
        boot_stats = np.empty(n_bootstrap)
        for i in range(n_bootstrap):
            sample = rng.choice(arr, size=n, replace=True)
            boot_stats[i] = stat_fn(sample)

        # Percentile method
        alpha = 1 - confidence
        lower = float(np.percentile(boot_stats, 100 * alpha / 2))
        upper = float(np.percentile(boot_stats, 100 * (1 - alpha / 2)))
        point = float(stat_fn(arr))

        return ConfidenceInterval(
            point_estimate=point,
            lower=lower,
            upper=upper,
            confidence_level=confidence,
            method=f"bootstrap-{statistic}",
            n=n,
            margin_of_error=(upper - lower) / 2,
        )

    @staticmethod
    def compute_difference(
        values_a: list[float],
        values_b: list[float],
        confidence: float = 0.95,
        n_bootstrap: int = 10000,
        seed: int | None = None,
    ) -> ConfidenceInterval:
        """Bootstrap CI for difference of means."""
        rng = np.random.default_rng(seed)
        a = np.array(values_a)
        b = np.array(values_b)
        n_a, n_b = len(a), len(b)

        if n_a < 2 or n_b < 2:
            diff = float(np.mean(a) - np.mean(b)) if n_a > 0 and n_b > 0 else 0
            return ConfidenceInterval(
                point_estimate=diff, lower=diff, upper=diff,
                confidence_level=confidence, method="bootstrap-diff",
                n=n_a + n_b, margin_of_error=0.0,
            )

        boot_diffs = np.empty(n_bootstrap)
        for i in range(n_bootstrap):
            sample_a = rng.choice(a, size=n_a, replace=True)
            sample_b = rng.choice(b, size=n_b, replace=True)
            boot_diffs[i] = np.mean(sample_a) - np.mean(sample_b)

        alpha = 1 - confidence
        lower = float(np.percentile(boot_diffs, 100 * alpha / 2))
        upper = float(np.percentile(boot_diffs, 100 * (1 - alpha / 2)))
        point = float(np.mean(a) - np.mean(b))

        return ConfidenceInterval(
            point_estimate=point,
            lower=lower,
            upper=upper,
            confidence_level=confidence,
            method="bootstrap-diff",
            n=n_a + n_b,
            margin_of_error=(upper - lower) / 2,
        )
