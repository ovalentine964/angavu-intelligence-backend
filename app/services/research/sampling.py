"""
Sampling Methodology — ECO 315 / STA 245.

Implements:
- Proper sampling methods for market research
- Sample size calculations
- Design effect computation
- Stratified and cluster sampling

From ECO 315 (Research Methods):
- §3.3: Sampling methods (probability and non-probability)
- Sample size formula: n = (Z² × p × (1-p)) / e²
- Stratified, cluster, systematic sampling

From STA 245 (Social & Economic Statistics for National Planning):
- Official statistics standards
- Design effects for complex surveys
- Finite population correction
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class SampleSizeResult:
    """Result of sample size calculation."""
    required_n: int
    adjusted_n: int                # After finite population correction
    confidence_level: float
    margin_of_error: float
    expected_proportion: float
    population_size: int | None
    design_effect: float
    method: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "required_n": self.required_n,
            "adjusted_n": self.adjusted_n,
            "confidence_level": self.confidence_level,
            "margin_of_error": self.margin_of_error,
            "expected_proportion": self.expected_proportion,
            "population_size": self.population_size,
            "design_effect": self.design_effect,
            "method": self.method,
        }


@dataclass
class SamplingPlan:
    """A complete sampling plan."""
    method: str
    strata: dict[str, list[str]] | None
    sample_size: int
    allocation: dict[str, int]     # Per-stratum sample sizes
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "strata": self.strata,
            "sample_size": self.sample_size,
            "allocation": self.allocation,
            "description": self.description,
        }


class SampleSizeCalculator:
    """
    Sample size calculations for research designs.

    From ECO 315 §3.3:
    n = (Z² × p × (1-p)) / e²

    With finite population correction (STA 245):
    n_adjusted = n / (1 + (n-1)/N)

    With design effect (complex surveys):
    n_design = n × DEFF
    """

    @staticmethod
    def for_proportion(
        confidence: float = 0.95,
        margin_of_error: float = 0.05,
        expected_proportion: float = 0.5,
        population_size: int | None = None,
        design_effect: float = 1.0,
    ) -> SampleSizeResult:
        """
        Sample size for estimating a proportion.

        n = (Z² × p × (1-p)) / e²

        Args:
            confidence: Confidence level (default 0.95)
            margin_of_error: Desired margin of error (default 0.05)
            expected_proportion: Expected proportion (default 0.5 for max variance)
            population_size: Finite population size (optional)
            design_effect: Design effect for complex sampling (default 1.0)
        """
        from scipy import stats as sp_stats

        z = float(sp_stats.norm.ppf((1 + confidence) / 2))
        p = expected_proportion
        e = margin_of_error

        # Basic formula (ECO 315)
        n = (z ** 2 * p * (1 - p)) / (e ** 2)

        # Apply design effect (STA 245)
        n = n * design_effect

        # Finite population correction
        n_adjusted = n
        if population_size:
            n_adjusted = n / (1 + (n - 1) / population_size)

        return SampleSizeResult(
            required_n=int(math.ceil(n)),
            adjusted_n=int(math.ceil(n_adjusted)),
            confidence_level=confidence,
            margin_of_error=margin_of_error,
            expected_proportion=expected_proportion,
            population_size=population_size,
            design_effect=design_effect,
            method="proportion",
        )

    @staticmethod
    def for_mean(
        confidence: float = 0.95,
        margin_of_error: float = 0.05,
        std_dev: float = 1.0,
        population_size: int | None = None,
        design_effect: float = 1.0,
    ) -> SampleSizeResult:
        """
        Sample size for estimating a mean.

        n = (Z × σ / e)²
        """
        from scipy import stats as sp_stats

        z = float(sp_stats.norm.ppf((1 + confidence) / 2))
        n = (z * std_dev / margin_of_error) ** 2
        n = n * design_effect

        n_adjusted = n
        if population_size:
            n_adjusted = n / (1 + (n - 1) / population_size)

        return SampleSizeResult(
            required_n=int(math.ceil(n)),
            adjusted_n=int(math.ceil(n_adjusted)),
            confidence_level=confidence,
            margin_of_error=margin_of_error,
            expected_proportion=0.5,
            population_size=population_size,
            design_effect=design_effect,
            method="mean",
        )

    @staticmethod
    def for_comparison(
        confidence: float = 0.95,
        power: float = 0.80,
        effect_size: float = 0.5,
    ) -> SampleSizeResult:
        """
        Sample size for comparing two groups.

        n per group = 2(z_α + z_β)² / d²
        """
        from scipy import stats as sp_stats

        z_alpha = float(sp_stats.norm.ppf((1 + confidence) / 2))
        z_beta = float(sp_stats.norm.ppf(power))

        if effect_size == 0:
            return SampleSizeResult(
                required_n=0, adjusted_n=0,
                confidence_level=confidence, margin_of_error=0,
                expected_proportion=0.5, population_size=None,
                design_effect=1.0, method="comparison",
            )

        n = 2 * ((z_alpha + z_beta) / effect_size) ** 2

        return SampleSizeResult(
            required_n=int(math.ceil(n)),
            adjusted_n=int(math.ceil(n)) * 2,
            confidence_level=confidence,
            margin_of_error=effect_size,
            expected_proportion=0.5,
            population_size=None,
            design_effect=1.0,
            method="comparison",
        )


class SamplingEngine:
    """
    Sampling methodology for market research.

    From ECO 315 §3.3:
    - Simple random sampling
    - Stratified sampling: Divide by product category
    - Cluster sampling: Sample specific market sections
    - Systematic sampling: Every kth element

    From STA 245:
    - Design effect computation
    - Optimal allocation for stratified sampling
    """

    @staticmethod
    def simple_random(
        population_size: int,
        sample_size: int,
        seed: int | None = None,
    ) -> list[int]:
        """Simple random sampling without replacement."""
        rng = np.random.default_rng(seed)
        return sorted(rng.choice(population_size, size=sample_size, replace=False).tolist())

    @staticmethod
    def stratified(
        strata: dict[str, int],
        total_sample_size: int,
        allocation: str = "proportional",
        seed: int | None = None,
    ) -> dict[str, list[int]]:
        """
        Stratified sampling.

        Args:
            strata: Dict mapping stratum name to population size
                    e.g., {"food": 1000, "household": 500, "health": 200}
            total_sample_size: Total number to sample
            allocation: "proportional" or "optimal" (Neyman)
            seed: Random seed

        Returns:
            Dict mapping stratum name to list of selected indices
        """
        rng = np.random.default_rng(seed)
        total_pop = sum(strata.values())

        # Compute per-stratum sample sizes
        stratum_ns = {}
        for name, pop_size in strata.items():
            if allocation == "proportional":
                stratum_ns[name] = max(1, round(total_sample_size * pop_size / total_pop))
            else:  # Neyman allocation (optimal)
                # Use √(p(1-p)) as proxy for stratum std
                stratum_ns[name] = max(1, round(total_sample_size * math.sqrt(pop_size) / sum(math.sqrt(v) for v in strata.values())))

        # Sample within each stratum
        result = {}
        for name, pop_size in strata.items():
            n = min(stratum_ns[name], pop_size)
            result[name] = sorted(rng.choice(pop_size, size=n, replace=False).tolist())

        return result

    @staticmethod
    def cluster(
        clusters: dict[str, int],
        n_clusters_to_sample: int,
        sample_per_cluster: int,
        seed: int | None = None,
    ) -> dict[str, list[int]]:
        """
        Cluster sampling.

        First randomly selects clusters, then samples within selected clusters.
        """
        rng = np.random.default_rng(seed)
        cluster_names = list(clusters.keys())
        n_select = min(n_clusters_to_sample, len(cluster_names))

        selected_clusters = rng.choice(cluster_names, size=n_select, replace=False)

        result = {}
        for cluster in selected_clusters:
            pop_size = clusters[cluster]
            n = min(sample_per_cluster, pop_size)
            result[cluster] = sorted(rng.choice(pop_size, size=n, replace=False).tolist())

        return result

    @staticmethod
    def compute_design_effect(
        cluster_sizes: list[float],
        intra_class_correlation: float = 0.05,
    ) -> float:
        """
        Compute design effect (DEFF) for clustered sampling.

        DEFF = 1 + (m̄ - 1) × ρ

        Where m̄ = average cluster size, ρ = intra-class correlation

        From STA 245: Complex survey design considerations.
        """
        if not cluster_sizes:
            return 1.0

        m_bar = np.mean(cluster_sizes)
        deff = 1 + (m_bar - 1) * intra_class_correlation

        return float(deff)

    @staticmethod
    def create_sampling_plan(
        market_segments: dict[str, int],
        total_budget: int,
        confidence: float = 0.95,
        margin_of_error: float = 0.05,
    ) -> SamplingPlan:
        """
        Create a complete sampling plan for market research.

        Combines stratified sampling with sample size calculations.
        """
        calculator = SampleSizeCalculator()

        # Calculate required sample per segment
        total_pop = sum(market_segments.values())
        allocation = {}

        for segment, pop_size in market_segments.items():
            result = calculator.for_proportion(
                confidence=confidence,
                margin_of_error=margin_of_error,
                population_size=pop_size,
            )
            allocation[segment] = min(result.adjusted_n, pop_size)

        # Adjust to budget
        total_needed = sum(allocation.values())
        if total_needed > total_budget:
            scale = total_budget / total_needed
            allocation = {
                k: max(1, int(v * scale))
                for k, v in allocation.items()
            }

        return SamplingPlan(
            method="stratified_proportional",
            strata={seg: list(range(pop)) for seg, pop in market_segments.items()},
            sample_size=sum(allocation.values()),
            allocation=allocation,
            description=(
                f"Stratified sampling across {len(market_segments)} segments. "
                f"Total sample: {sum(allocation.values())} from population of {total_pop}. "
                f"Confidence: {confidence*100:.0f}%, Margin: ±{margin_of_error*100:.1f}%."
            ),
        )
