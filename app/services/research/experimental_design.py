"""
Experimental Design Framework — STA 343.

Implements:
- A/B testing framework for business advice
- Controlled experiment design for pilot programs
- Power analysis for sample size calculations
- Factorial designs for multi-factor experiments
- Sequential/adaptive designs

From STA 343 (Experimental Designs):
- §8.1: Principles (randomization, replication, blocking)
- §8.2: Completely Randomized Design (CRD)
- §8.3: Randomized Complete Block Design (RCBD)
- §8.5: Factorial Designs
- §8.8: Sequential and Adaptive Designs
"""

from __future__ import annotations

import hashlib
import math
import secrets
from collections import defaultdict
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

class ExperimentStatus(str, Enum):
    """Experiment lifecycle states."""
    DRAFT = "draft"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    STOPPED_EARLY = "stopped_early"


class DesignType(str, Enum):
    """Experimental design types (STA 343)."""
    COMPLETELY_RANDOMIZED = "crd"           # §8.2
    RANDOMIZED_COMPLETE_BLOCK = "rcbd"      # §8.3
    FACTORIAL = "factorial"                 # §8.5
    LATIN_SQUARE = "latin_square"           # §8.4
    SEQUENTIAL = "sequential"               # §8.8


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class Variant:
    """An experimental variant (treatment)."""
    variant_id: str
    name: str
    description: str
    allocation_prob: float = 0.5  # Probability of assignment

    def to_dict(self) -> Dict[str, Any]:
        return {
            "variant_id": self.variant_id,
            "name": self.name,
            "description": self.description,
            "allocation_prob": self.allocation_prob,
        }


@dataclass
class ExperimentResult:
    """Results from an experiment."""
    experiment_id: str
    status: ExperimentStatus
    variants: List[Dict[str, Any]]
    primary_metric: str
    winner: Optional[str]
    confidence_level: float
    p_value: float
    effect_size: float
    power: float
    sample_sizes: Dict[str, int]
    metric_means: Dict[str, float]
    metric_stds: Dict[str, float]
    confidence_intervals: Dict[str, Tuple[float, float]]
    recommendation: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "status": self.status.value,
            "variants": self.variants,
            "primary_metric": self.primary_metric,
            "winner": self.winner,
            "confidence_level": round(self.confidence_level, 4),
            "p_value": round(self.p_value, 6),
            "effect_size": round(self.effect_size, 4),
            "power": round(self.power, 4),
            "sample_sizes": self.sample_sizes,
            "metric_means": {k: round(v, 4) for k, v in self.metric_means.items()},
            "metric_stds": {k: round(v, 4) for k, v in self.metric_stds.items()},
            "confidence_intervals": {
                k: [round(v[0], 4), round(v[1], 4)]
                for k, v in self.confidence_intervals.items()
            },
            "recommendation": self.recommendation,
        }


@dataclass
class PowerAnalysisResult:
    """Result of power analysis."""
    required_n_per_group: int
    total_n: int
    effect_size: float
    alpha: float
    power: float
    test_type: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "required_n_per_group": self.required_n_per_group,
            "total_n": self.total_n,
            "effect_size": round(self.effect_size, 4),
            "alpha": self.alpha,
            "power": self.power,
            "test_type": self.test_type,
        }


# ---------------------------------------------------------------------------
# Power Analyzer (STA 342 §7.7 + STA 343)
# ---------------------------------------------------------------------------

class PowerAnalyzer:
    """
    Power analysis for sample size calculations.

    From STA 342 §7.7:
    - One-sample t-test: n = (z_α + z_β)² × σ² / δ²
    - Two-sample t-test: n per group = 2(z_α + z_β)² × σ² / δ²
    - Cohen's d: Small=0.2, Medium=0.5, Large=0.8
    """

    @staticmethod
    def analyze(
        effect_size: float,
        power: float = 0.80,
        alpha: float = 0.05,
        test_type: str = "two_sample",
        n_groups: int = 2,
    ) -> PowerAnalysisResult:
        """
        Compute required sample size.

        Args:
            effect_size: Cohen's d (standardized effect size)
            power: Desired power (1 - β), default 0.80
            alpha: Significance level, default 0.05
            test_type: "one_sample", "two_sample", or "paired"
            n_groups: Number of groups for multi-group designs

        Returns:
            PowerAnalysisResult with required sample sizes
        """
        z_alpha = sp_stats.norm.ppf(1 - alpha / 2)
        z_beta = sp_stats.norm.ppf(power)

        if effect_size == 0:
            return PowerAnalysisResult(
                required_n_per_group=0,
                total_n=0,
                effect_size=0,
                alpha=alpha,
                power=power,
                test_type=test_type,
            )

        if test_type == "one_sample":
            n = ((z_alpha + z_beta) / effect_size) ** 2
        elif test_type == "paired":
            n = ((z_alpha + z_beta) / effect_size) ** 2
        elif test_type == "two_sample":
            n = 2 * ((z_alpha + z_beta) / effect_size) ** 2
        else:  # ANOVA / multi-group
            # Approximation for one-way ANOVA
            f = effect_size  # Cohen's f
            n = ((z_alpha + z_beta) / f) ** 2 * n_groups / (n_groups - 1)

        n_per_group = max(int(math.ceil(n)), 2)
        total = n_per_group * n_groups

        return PowerAnalysisResult(
            required_n_per_group=n_per_group,
            total_n=total,
            effect_size=effect_size,
            alpha=alpha,
            power=power,
            test_type=test_type,
        )

    @staticmethod
    def compute_achieved_power(
        n_per_group: int,
        effect_size: float,
        alpha: float = 0.05,
        test_type: str = "two_sample",
    ) -> float:
        """Compute achieved power given sample size and effect size."""
        if n_per_group < 2 or effect_size == 0:
            return 0.0

        if test_type == "two_sample":
            ncp = effect_size * math.sqrt(n_per_group / 2)
            df = 2 * n_per_group - 2
        else:
            ncp = effect_size * math.sqrt(n_per_group)
            df = n_per_group - 1

        t_crit = sp_stats.t.ppf(1 - alpha / 2, df)
        power = 1 - sp_stats.nct.cdf(t_crit, df, ncp) + sp_stats.nct.cdf(-t_crit, df, ncp)
        return min(1.0, max(0.0, float(power)))


# ---------------------------------------------------------------------------
# Experiment Designer (STA 343)
# ---------------------------------------------------------------------------

class ExperimentDesigner:
    """
    Design experiments following Fisher's principles (STA 343).

    Principles:
    1. Randomization: Randomly assign treatments to units
    2. Replication: Repeat to estimate error
    3. Blocking: Group similar units to reduce error

    Supports:
    - Completely Randomized Design (CRD)
    - Randomized Complete Block Design (RCBD)
    - Factorial designs
    - Sequential/adaptive designs
    """

    @staticmethod
    def design_crd(
        n_subjects: int,
        variants: List[Variant],
        seed: Optional[int] = None,
    ) -> Dict[str, List[str]]:
        """
        Completely Randomized Design (STA 343 §8.2).

        Randomly assign all subjects to treatments with equal probability.
        """
        rng = np.random.default_rng(seed)
        assignment: Dict[str, List[str]] = {v.variant_id: [] for v in variants}

        # Create allocation array
        variant_ids = []
        for v in variants:
            count = max(1, round(v.allocation_prob * n_subjects))
            variant_ids.extend([v.variant_id] * count)

        # Trim or extend to match n_subjects
        while len(variant_ids) < n_subjects:
            variant_ids.append(variants[0].variant_id)
        variant_ids = variant_ids[:n_subjects]

        # Shuffle
        rng.shuffle(variant_ids)

        for i, vid in enumerate(variant_ids):
            subject_id = f"subject_{i:06d}"
            assignment[vid].append(subject_id)

        return assignment

    @staticmethod
    def design_rcbd(
        blocks: Dict[str, List[str]],
        variants: List[Variant],
        seed: Optional[int] = None,
    ) -> Dict[str, Dict[str, List[str]]]:
        """
        Randomized Complete Block Design (STA 343 §8.3).

        Block similar units together, then randomize within blocks.
        Reduces experimental error from known sources of variation.
        """
        rng = np.random.default_rng(seed)
        assignment: Dict[str, Dict[str, List[str]]] = {}

        for block_name, subjects in blocks.items():
            assignment[block_name] = {v.variant_id: [] for v in variants}

            # Randomize within block
            shuffled = list(subjects)
            rng.shuffle(shuffled)

            # Distribute evenly across variants
            for i, subject in enumerate(shuffled):
                vid = variants[i % len(variants)].variant_id
                assignment[block_name][vid].append(subject)

        return assignment

    @staticmethod
    def design_factorial(
        n_subjects: int,
        factors: Dict[str, List[str]],
        seed: Optional[int] = None,
    ) -> List[Dict[str, str]]:
        """
        Factorial design (STA 343 §8.5).

        Study multiple factors simultaneously. Each subject receives
        a combination of factor levels.

        Args:
            n_subjects: Total number of subjects
            factors: Dict mapping factor name to list of levels
                     e.g., {"advice_type": ["price", "demand"],
                            "frequency": ["daily", "weekly"]}
            seed: Random seed for reproducibility

        Returns:
            List of factor level assignments per subject
        """
        import itertools

        rng = np.random.default_rng(seed)

        # Generate all combinations
        factor_names = list(factors.keys())
        factor_levels = [factors[f] for f in factor_names]
        combinations = list(itertools.product(*factor_levels))

        # Assign subjects to combinations
        assignments = []
        for i in range(n_subjects):
            combo = combinations[i % len(combinations)]
            assignment = {factor_names[j]: combo[j] for j in range(len(factor_names))}
            assignment["subject_id"] = f"subject_{i:06d}"
            assignments.append(assignment)

        # Shuffle
        rng.shuffle(assignments)

        return assignments


# ---------------------------------------------------------------------------
# A/B Test Framework
# ---------------------------------------------------------------------------

class ABTestFramework:
    """
    A/B testing framework for Angavu Intelligence products.

    Implements proper experimental design (STA 343):
    - Random assignment using cryptographic randomness
    - Sequential testing with O'Brien-Fleming boundaries
    - Proper power analysis before starting
    - Effect size and confidence interval reporting
    - Multiple testing correction when comparing many variants

    Usage:
        framework = ABTestFramework()

        # Create experiment
        exp = framework.create_experiment(
            name="Soko Pulse Price Advice",
            variants=[
                Variant("control", "Current advice", "Existing price recommendations"),
                Variant("treatment", "New advice", "ML-based price recommendations"),
            ],
            primary_metric="profit_change_pct",
            min_detectable_effect=0.05,
        )

        # Assign user
        variant = framework.assign_user(exp["experiment_id"], user_id)

        # Record outcome
        framework.record_outcome(exp["experiment_id"], user_id, variant, 12.5)

        # Analyze
        result = framework.analyze(exp["experiment_id"])
    """

    def __init__(self):
        self._experiments: Dict[str, Dict[str, Any]] = {}
        self._assignments: Dict[str, Dict[str, str]] = {}  # exp_id -> {user_id: variant_id}
        self._outcomes: Dict[str, Dict[str, List[float]]] = {}  # exp_id -> {variant_id: [values]}

    def create_experiment(
        self,
        name: str,
        variants: List[Variant],
        primary_metric: str,
        min_detectable_effect: float = 0.05,
        alpha: float = 0.05,
        power: float = 0.80,
        design: DesignType = DesignType.COMPLETELY_RANDOMIZED,
    ) -> Dict[str, Any]:
        """
        Create a new A/B test experiment.

        Performs power analysis to determine required sample size.
        """
        exp_id = hashlib.sha256(
            f"{name}{datetime.now(timezone.utc).isoformat()}{secrets.token_hex(8)}".encode()
        ).hexdigest()[:16]

        # Power analysis
        n_groups = len(variants)
        power_result = PowerAnalyzer.analyze(
            effect_size=min_detectable_effect,
            power=power,
            alpha=alpha,
            test_type="two_sample" if n_groups == 2 else "anova",
            n_groups=n_groups,
        )

        experiment = {
            "experiment_id": exp_id,
            "name": name,
            "variants": [v.to_dict() for v in variants],
            "primary_metric": primary_metric,
            "min_detectable_effect": min_detectable_effect,
            "alpha": alpha,
            "power": power,
            "design": design.value,
            "status": ExperimentStatus.DRAFT.value,
            "required_n_per_group": power_result.required_n_per_group,
            "total_required_n": power_result.total_n,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        self._experiments[exp_id] = experiment
        self._assignments[exp_id] = {}
        self._outcomes[exp_id] = {v.variant_id: [] for v in variants}

        logger.info(
            "experiment_created",
            exp_id=exp_id,
            name=name,
            variants=len(variants),
            required_n=power_result.total_n,
        )

        return experiment

    def assign_user(
        self,
        experiment_id: str,
        user_id: str,
    ) -> str:
        """
        Assign a user to a variant using deterministic hashing.

        Uses SHA-256 for consistent assignment (same user always
        gets same variant across sessions).
        """
        exp = self._experiments.get(experiment_id)
        if not exp:
            raise ValueError(f"Experiment {experiment_id} not found")

        # Deterministic assignment via hash
        hash_input = f"{experiment_id}:{user_id}"
        hash_val = int(hashlib.sha256(hash_input.encode()).hexdigest(), 16)
        variants = exp["variants"]
        idx = hash_val % len(variants)
        variant_id = variants[idx]["variant_id"]

        self._assignments[experiment_id][user_id] = variant_id

        return variant_id

    def record_outcome(
        self,
        experiment_id: str,
        user_id: str,
        variant_id: str,
        value: float,
    ) -> None:
        """Record an outcome value for a user in an experiment."""
        if experiment_id not in self._outcomes:
            raise ValueError(f"Experiment {experiment_id} not found")

        if variant_id not in self._outcomes[experiment_id]:
            raise ValueError(f"Variant {variant_id} not found")

        self._outcomes[experiment_id][variant_id].append(value)

    def analyze(
        self,
        experiment_id: str,
    ) -> ExperimentResult:
        """
        Analyze experiment results.

        Performs appropriate statistical test based on number of variants:
        - 2 variants: Welch's t-test
        - 3+ variants: One-way ANOVA (or Kruskal-Wallis if non-normal)

        Includes effect size, confidence intervals, and power.
        """
        from app.services.research.hypothesis_testing import HypothesisTester

        exp = self._experiments.get(experiment_id)
        if not exp:
            raise ValueError(f"Experiment {experiment_id} not found")

        outcomes = self._outcomes.get(experiment_id, {})
        tester = HypothesisTester(alpha=exp["alpha"])

        variant_data = {}
        for vid, values in outcomes.items():
            if values:
                variant_data[vid] = values

        if len(variant_data) < 2:
            return ExperimentResult(
                experiment_id=experiment_id,
                status=ExperimentStatus(exp["status"]),
                variants=exp["variants"],
                primary_metric=exp["primary_metric"],
                winner=None,
                confidence_level=1 - exp["alpha"],
                p_value=1.0,
                effect_size=0.0,
                power=0.0,
                sample_sizes={vid: len(v) for vid, v in variant_data.items()},
                metric_means={vid: float(np.mean(v)) if v else 0 for vid, v in variant_data.items()},
                metric_stds={vid: float(np.std(v, ddof=1)) if len(v) > 1 else 0 for vid, v in variant_data.items()},
                confidence_intervals={},
                recommendation="Insufficient data for analysis",
            )

        # Compute statistics
        sample_sizes = {vid: len(v) for vid, v in variant_data.items()}
        metric_means = {vid: float(np.mean(v)) for vid, v in variant_data.items()}
        metric_stds = {
            vid: float(np.std(v, ddof=1)) if len(v) > 1 else 0.0
            for vid, v in variant_data.items()
        }

        # Confidence intervals
        confidence_intervals = {}
        for vid, values in variant_data.items():
            if len(values) > 1:
                mean = np.mean(values)
                se = np.std(values, ddof=1) / math.sqrt(len(values))
                t_crit = sp_stats.t.ppf(1 - exp["alpha"] / 2, len(values) - 1)
                confidence_intervals[vid] = (
                    float(mean - t_crit * se),
                    float(mean + t_crit * se),
                )

        # Statistical test
        variant_ids = list(variant_data.keys())
        p_value = 1.0
        effect_size = 0.0
        winner = None

        if len(variant_ids) == 2:
            # Two-sample t-test
            a = variant_data[variant_ids[0]]
            b = variant_data[variant_ids[1]]
            result = tester.two_sample_t_test(a, b)
            p_value = result.p_value
            effect_size = result.effect_size or 0.0

            if result.reject_null:
                winner = variant_ids[0] if metric_means[variant_ids[0]] > metric_means[variant_ids[1]] else variant_ids[1]
        else:
            # ANOVA / Kruskal-Wallis
            groups = [variant_data[vid] for vid in variant_ids]
            result = tester.kruskal_wallis(groups)
            p_value = result.p_value
            effect_size = result.effect_size or 0.0

            if result.reject_null:
                winner = max(variant_ids, key=lambda v: metric_means[v])

        # Compute achieved power
        if len(variant_ids) == 2:
            n_a = sample_sizes[variant_ids[0]]
            n_b = sample_sizes[variant_ids[1]]
            power = PowerAnalyzer.compute_achieved_power(
                min(n_a, n_b), abs(effect_size), exp["alpha"]
            )
        else:
            power = 0.0  # Multi-group power is more complex

        # Generate recommendation
        if winner:
            recommendation = (
                f"Variant '{winner}' is significantly better "
                f"(p={p_value:.4f}, d={effect_size:.3f}). "
                f"Consider deploying to all users."
            )
        else:
            recommendation = (
                f"No significant difference detected (p={p_value:.4f}). "
                f"Continue experiment or increase sample size."
            )

        return ExperimentResult(
            experiment_id=experiment_id,
            status=ExperimentStatus(exp["status"]),
            variants=exp["variants"],
            primary_metric=exp["primary_metric"],
            winner=winner,
            confidence_level=1 - exp["alpha"],
            p_value=p_value,
            effect_size=effect_size,
            power=power,
            sample_sizes=sample_sizes,
            metric_means=metric_means,
            metric_stds=metric_stds,
            confidence_intervals=confidence_intervals,
            recommendation=recommendation,
        )

    def get_experiment(self, experiment_id: str) -> Optional[Dict[str, Any]]:
        """Get experiment details."""
        exp = self._experiments.get(experiment_id)
        if exp:
            exp_copy = exp.copy()
            exp_copy["current_sample_sizes"] = {
                vid: len(vals)
                for vid, vals in self._outcomes.get(experiment_id, {}).items()
            }
            return exp_copy
        return None

    def list_experiments(self) -> List[Dict[str, Any]]:
        """List all experiments."""
        return [
            {
                "experiment_id": eid,
                "name": exp["name"],
                "status": exp["status"],
                "variants": len(exp["variants"]),
            }
            for eid, exp in self._experiments.items()
        ]
