"""
Bayesian Inference & Non-Parametric Density Estimation (STA 341, STA 444).

Classes:
- BayesianUpdater: Beta-Binomial and Normal-Normal conjugate updates
- KernelDensityEstimator: Gaussian KDE with Silverman bandwidth and multimodality detection

Decomposed from statistical_foundation.py for maintainability.
"""

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy import stats
from scipy.stats import norm


class BayesianUpdater:
    """
    Bayesian estimation framework (STA 341 — Theory of Estimation).

    Implements Bayes' theorem: p(θ|x) = [f(x|θ) × p(θ)] / m(x)

    Used by:
    - Alama Score: Credit scoring with limited data (Beta-Binomial model)
    - Soko Pulse: Price estimation with prior market knowledge
    - Jamii Insights: Financial inclusion estimation with demographic priors
    """

    @staticmethod
    def beta_binomial_update(
        prior_alpha: float,
        prior_beta: float,
        successes: int,
        failures: int,
    ) -> Tuple[float, float, Dict[str, float]]:
        """
        Beta-Binomial conjugate update.

        Prior: θ ~ Beta(α, β)
        Likelihood: X ~ Binomial(n, θ)
        Posterior: θ|X ~ Beta(α + successes, β + failures)

        Args:
            prior_alpha: Prior Beta alpha parameter
            prior_beta: Prior Beta beta parameter
            successes: Number of observed successes
            failures: Number of observed failures

        Returns:
            Tuple of (posterior_alpha, posterior_beta, summary_dict)
        """
        post_alpha: float = prior_alpha + successes
        post_beta: float = prior_beta + failures

        post_mean: float = post_alpha / (post_alpha + post_beta)
        post_var: float = (post_alpha * post_beta) / (
            (post_alpha + post_beta) ** 2 * (post_alpha + post_beta + 1)
        )
        post_std: float = float(np.sqrt(post_var))

        ci_lower: float = float(stats.beta.ppf(0.025, post_alpha, post_beta))
        ci_upper: float = float(stats.beta.ppf(0.975, post_alpha, post_beta))

        summary: Dict[str, float] = {
            "posterior_mean": round(post_mean, 4),
            "posterior_std": round(post_std, 4),
            "credible_interval_95": (round(ci_lower, 4), round(ci_upper, 4)),
            "prior_mean": round(prior_alpha / (prior_alpha + prior_beta), 4),
            "prior_sample_size": prior_alpha + prior_beta,
            "data_points": successes + failures,
            "effective_sample_size": post_alpha + post_beta,
        }

        return post_alpha, post_beta, summary

    @staticmethod
    def normal_normal_update(
        prior_mean: float,
        prior_var: float,
        data_mean: float,
        data_var: float,
        n: int,
    ) -> Tuple[float, float, Dict[str, float]]:
        """
        Normal-Normal conjugate update.

        Prior: θ ~ N(μ₀, σ₀²)
        Likelihood: X̄|θ ~ N(θ, σ²/n)
        Posterior: θ|X̄ ~ N(μₙ, σₙ²)
        """
        prior_precision: float = 1 / prior_var
        data_precision: float = n / data_var

        post_precision: float = prior_precision + data_precision
        post_var_val: float = 1 / post_precision
        post_mean_val: float = (
            prior_precision * prior_mean + data_precision * data_mean
        ) / post_precision
        post_std_val: float = float(np.sqrt(post_var_val))

        ci_lower: float = post_mean_val - 1.96 * post_std_val
        ci_upper: float = post_mean_val + 1.96 * post_std_val

        summary: Dict[str, Any] = {
            "posterior_mean": round(post_mean_val, 4),
            "posterior_std": round(post_std_val, 4),
            "credible_interval_95": (round(ci_lower, 4), round(ci_upper, 4)),
            "prior_mean": prior_mean,
            "prior_std": float(np.sqrt(prior_var)),
            "data_mean": data_mean,
            "data_points": n,
            "shrinkage_factor": round(data_precision / post_precision, 4),
        }

        return post_mean_val, post_var_val, summary


class KernelDensityEstimator:
    """
    Kernel Density Estimation (STA 444 — Non-Parametric Methods).

    Estimates probability density function without distributional assumptions.
    Formula: f̂(x) = (1/nh) Σᵢ K((x - Xᵢ)/h)

    Bandwidth selection (Silverman's rule): h = 1.06 × σ̂ × n^(-1/5)
    """

    @staticmethod
    def gaussian_kde(
        data: np.ndarray,
        points: Optional[np.ndarray] = None,
        bandwidth: Optional[float] = None,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Gaussian kernel density estimation.

        Args:
            data: 1D array of observations
            points: Points at which to evaluate density
            bandwidth: Smoothing parameter (default: Silverman's rule)

        Returns:
            Tuple of (grid_points, density_estimates)
        """
        n: int = len(data)
        if n < 2:
            raise ValueError("Need at least 2 data points for KDE")

        if bandwidth is None:
            sigma: float = float(np.std(data, ddof=1))
            iqr: float = float(np.percentile(data, 75) - np.percentile(data, 25))
            sigma_robust: float = min(sigma, iqr / 1.34)
            bandwidth = max(0.9 * sigma_robust * n ** (-1 / 5), 1e-6)

        if points is None:
            data_min: float = float(data.min())
            data_max: float = float(data.max())
            margin: float = 3 * bandwidth
            points = np.linspace(data_min - margin, data_max + margin, 100)

        density: np.ndarray = np.zeros_like(points, dtype=float)
        for xi in data:
            density += norm.pdf((points - xi) / bandwidth)
        density /= n * bandwidth

        return points, density

    @staticmethod
    def detect_multimodality(
        data: np.ndarray,
        n_modes_max: int = 5,
    ) -> Dict[str, Any]:
        """
        Test for multimodality in data distribution.

        Uses kernel density estimation to identify peaks.

        Args:
            data: 1D array of observations
            n_modes_max: Maximum number of modes to detect

        Returns:
            Dict with mode count, locations, and heights
        """
        points, density = KernelDensityEstimator.gaussian_kde(data)

        peaks: List[Tuple[float, float]] = []
        for i in range(1, len(density) - 1):
            if density[i] > density[i - 1] and density[i] > density[i + 1]:
                peaks.append((float(points[i]), float(density[i])))

        peaks.sort(key=lambda x: x[1], reverse=True)
        peaks = peaks[:n_modes_max]

        return {
            "n_modes": len(peaks),
            "mode_locations": [round(p[0], 2) for p in peaks],
            "mode_heights": [round(p[1], 6) for p in peaks],
            "is_multimodal": len(peaks) > 1,
        }


__all__ = ["BayesianUpdater", "KernelDensityEstimator"]
