"""
Statistical Foundation Layer — Shared by all intelligence products.

Theoretical Foundations:
- STA 241: Probability and Distribution Models
- STA 443: Measure and Probability Theory
- STA 341: Theory of Estimation
- STA 444: Non-Parametric Methods
- STA 342: Test of Hypothesis

This module provides the shared statistical infrastructure that all
intelligence products build upon. Every estimation, prediction, and
inference in Biashara Intelligence traces back to these foundations.

Key Concepts Embedded:
- Bayesian estimation (STA 341): Prior → Data → Posterior for all services
- Kernel density estimation (STA 444): Non-parametric density estimation
- Bootstrap inference (STA 444): Distribution-free confidence intervals
- Sufficient statistics (STA 341): Efficient data summarization
- Hypothesis testing (STA 342): Statistical validation of all claims
- Conditional expectation (STA 443): E[X|G] as the optimal predictor
"""

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import structlog
from scipy import stats
from scipy.stats import norm

logger = structlog.get_logger(__name__)


class BayesianUpdater:
    """
    Bayesian estimation framework (STA 341 — Theory of Estimation).

    Implements Bayes' theorem: p(θ|x) = [f(x|θ) × p(θ)] / m(x)

    Used by:
    - Alama Score: Credit scoring with limited data (Beta-Binomial model)
    - Soko Pulse: Price estimation with prior market knowledge
    - Jamii Insights: Financial inclusion estimation with demographic priors

    The posterior mean is a weighted average of prior mean and MLE:
    θ̂_Bayes = [n/(n+n₀)] × θ̂_MLE + [n₀/(n+n₀)] × θ_prior
    where n₀ is the "prior sample size."
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

        Used by Alama Score for default probability estimation:
        - Prior: Industry-wide default rate (e.g., Beta(2, 8) = 20% default)
        - Data: Individual trader's repayment history
        - Posterior: Personalized default probability with uncertainty

        Args:
            prior_alpha: Prior Beta alpha parameter
            prior_beta: Prior Beta beta parameter
            successes: Number of observed successes (e.g., repayments)
            failures: Number of observed failures (e.g., defaults)

        Returns:
            Tuple of (posterior_alpha, posterior_beta, summary_dict)
        """
        post_alpha = prior_alpha + successes
        post_beta = prior_beta + failures

        post_mean = post_alpha / (post_alpha + post_beta)
        post_var = (post_alpha * post_beta) / (
            (post_alpha + post_beta) ** 2 * (post_alpha + post_beta + 1)
        )
        post_std = np.sqrt(post_var)

        # 95% credible interval
        ci_lower = stats.beta.ppf(0.025, post_alpha, post_beta)
        ci_upper = stats.beta.ppf(0.975, post_alpha, post_beta)

        summary = {
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

        Used by Soko Pulse for price estimation:
        - Prior: Historical average price
        - Data: Recent market observations
        - Posterior: Updated price estimate with uncertainty
        """
        prior_precision = 1 / prior_var
        data_precision = n / data_var

        post_precision = prior_precision + data_precision
        post_var = 1 / post_precision
        post_mean = (
            prior_precision * prior_mean + data_precision * data_mean
        ) / post_precision
        post_std = np.sqrt(post_var)

        ci_lower = post_mean - 1.96 * post_std
        ci_upper = post_mean + 1.96 * post_std

        summary = {
            "posterior_mean": round(post_mean, 4),
            "posterior_std": round(post_std, 4),
            "credible_interval_95": (round(ci_lower, 4), round(ci_upper, 4)),
            "prior_mean": prior_mean,
            "prior_std": np.sqrt(prior_var),
            "data_mean": data_mean,
            "data_points": n,
            "shrinkage_factor": round(data_precision / post_precision, 4),
        }

        return post_mean, post_var, summary


class KernelDensityEstimator:
    """
    Kernel Density Estimation (STA 444 — Non-Parametric Methods).

    Estimates probability density function without distributional assumptions.

    Formula: f̂(x) = (1/nh) Σᵢ K((x - Xᵢ)/h)

    Where K = kernel function, h = bandwidth, Xᵢ = data points.

    Bandwidth selection (Silverman's rule of thumb):
    h = 1.06 × σ̂ × n^(-1/5)

    Used by:
    - Alama Score: Non-parametric default risk distribution
    - Soko Pulse: Price distribution estimation
    - Jamii Insights: Income distribution analysis
    """

    @staticmethod
    def gaussian_kde(
        data: np.ndarray,
        points: Optional[np.ndarray] = None,
        bandwidth: Optional[float] = None,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Gaussian kernel density estimation.

        Kernel: K(u) = (2π)^(-1/2) exp(-u²/2)

        Args:
            data: 1D array of observations
            points: Points at which to evaluate density (default: 100 grid points)
            bandwidth: Smoothing parameter (default: Silverman's rule)

        Returns:
            Tuple of (grid_points, density_estimates)
        """
        n = len(data)
        if n < 2:
            raise ValueError("Need at least 2 data points for KDE")

        # Silverman's rule of thumb
        if bandwidth is None:
            sigma = np.std(data, ddof=1)
            iqr = np.percentile(data, 75) - np.percentile(data, 25)
            sigma_robust = min(sigma, iqr / 1.34)
            bandwidth = 0.9 * sigma_robust * n ** (-1 / 5)
            bandwidth = max(bandwidth, 1e-6)  # Avoid zero bandwidth

        if points is None:
            data_min, data_max = data.min(), data.max()
            margin = 3 * bandwidth
            points = np.linspace(data_min - margin, data_max + margin, 100)

        # Compute KDE
        density = np.zeros_like(points, dtype=float)
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

        # Find peaks (local maxima)
        peaks = []
        for i in range(1, len(density) - 1):
            if density[i] > density[i - 1] and density[i] > density[i + 1]:
                peaks.append((points[i], density[i]))

        # Sort by height (descending)
        peaks.sort(key=lambda x: x[1], reverse=True)
        peaks = peaks[:n_modes_max]

        return {
            "n_modes": len(peaks),
            "mode_locations": [round(p[0], 2) for p in peaks],
            "mode_heights": [round(p[1], 6) for p in peaks],
            "is_multimodal": len(peaks) > 1,
        }


class BootstrapInference:
    """
    Bootstrap inference (STA 444 — Non-Parametric Methods).

    Distribution-free confidence intervals and standard errors.

    Used by all services for uncertainty quantification without
    distributional assumptions.

    The bootstrap principle: The empirical distribution F̂ is a
    good approximation to the population distribution F. Resampling
    from F̂ mimics sampling from F.
    """

    @staticmethod
    def percentile_ci(
        data: np.ndarray,
        statistic_func: callable,
        n_bootstrap: int = 10000,
        confidence: float = 0.95,
        seed: int = 42,
    ) -> Dict[str, float]:
        """
        Bootstrap percentile confidence interval.

        Procedure:
        1. Resample n_bootstrap samples with replacement
        2. Compute statistic for each bootstrap sample
        3. Take percentiles of bootstrap distribution

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
        n = len(data)
        original_stat = statistic_func(data)

        bootstrap_stats = np.zeros(n_bootstrap)
        for i in range(n_bootstrap):
            sample = rng.choice(data, size=n, replace=True)
            bootstrap_stats[i] = statistic_func(sample)

        alpha = 1 - confidence
        ci_lower = np.percentile(bootstrap_stats, 100 * alpha / 2)
        ci_upper = np.percentile(bootstrap_stats, 100 * (1 - alpha / 2))

        return {
            "estimate": round(float(original_stat), 4),
            "ci_lower": round(float(ci_lower), 4),
            "ci_upper": round(float(ci_upper), 4),
            "bootstrap_se": round(float(np.std(bootstrap_stats)), 4),
            "n_bootstrap": n_bootstrap,
            "confidence": confidence,
        }

    @staticmethod
    def bootstrap_se(
        data: np.ndarray,
        statistic_func: callable,
        n_bootstrap: int = 10000,
        seed: int = 42,
    ) -> float:
        """
        Bootstrap standard error estimation.

        Args:
            data: Original sample
            statistic_func: Function computing the statistic
            n_bootstrap: Number of bootstrap resamples
            seed: Random seed

        Returns:
            Bootstrap standard error
        """
        rng = np.random.RandomState(seed)
        n = len(data)
        stats = np.zeros(n_bootstrap)
        for i in range(n_bootstrap):
            sample = rng.choice(data, size=n, replace=True)
            stats[i] = statistic_func(sample)
        return float(np.std(stats))


class HypothesisTester:
    """
    Hypothesis testing framework (STA 342 — Test of Hypothesis).

    Implements statistical tests for validating all platform claims.
    Every "X% improvement" or "significant difference" claim must
    pass through this framework.

    Key Tests:
    - t-test for mean comparisons (income before/after intervention)
    - Chi-square for categorical associations (product type vs default)
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
        Two-sample hypothesis test.

        Automatically selects parametric (t-test) or non-parametric
        (Mann-Whitney) based on normality testing.

        Args:
            sample1: First sample
            sample2: Second sample
            test_type: 'auto', 'ttest', 'mannwhitney', 'ks'
            alternative: 'two-sided', 'greater', 'less'

        Returns:
            Dict with test statistic, p-value, and interpretation
        """
        n1, n2 = len(sample1), len(sample2)

        if test_type == "auto":
            # Check normality (Shapiro-Wilk for n < 5000)
            if n1 < 5000 and n2 < 5000:
                _, p_norm1 = stats.shapiro(sample1[:min(n1, 5000)])
                _, p_norm2 = stats.shapiro(sample2[:min(n2, 5000)])
                if p_norm1 > 0.05 and p_norm2 > 0.05:
                    test_type = "ttest"
                else:
                    test_type = "mannwhitney"
            else:
                test_type = "ttest"  # CLT applies for large samples

        if test_type == "ttest":
            stat, p_value = stats.ttest_ind(
                sample1, sample2, alternative=alternative
            )
            test_name = "Welch's t-test"
        elif test_type == "mannwhitney":
            stat, p_value = stats.mannwhitneyu(
                sample1, sample2, alternative=alternative
            )
            test_name = "Mann-Whitney U test"
        elif test_type == "ks":
            stat, p_value = stats.ks_2samp(sample1, sample2)
            test_name = "Kolmogorov-Smirnov test"
        else:
            raise ValueError(f"Unknown test type: {test_type}")

        # Effect size (Cohen's d for t-test)
        if test_type == "ttest":
            pooled_std = np.sqrt(
                ((n1 - 1) * np.var(sample1, ddof=1) + (n2 - 1) * np.var(sample2, ddof=1))
                / (n1 + n2 - 2)
            )
            cohens_d = (np.mean(sample1) - np.mean(sample2)) / max(pooled_std, 1e-10)
        else:
            cohens_d = None

        return {
            "test_name": test_name,
            "test_statistic": round(float(stat), 4),
            "p_value": round(float(p_value), 6),
            "significant_at_05": p_value < 0.05,
            "significant_at_01": p_value < 0.01,
            "effect_size_cohens_d": round(float(cohens_d), 4) if cohens_d else None,
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

    Supported distributions:
    - Normal: N(μ, σ²) — symmetric, bell-shaped
    - Log-normal: ln(X) ~ N(μ, σ²) — income distributions
    - Gamma: Γ(α, β) — positive, right-skewed
    - Exponential: Exp(λ) — inter-arrival times
    - Weibull: Weibull(k, λ) — survival analysis
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
        Fit multiple distributions and select the best one.

        Uses Kolmogorov-Smirnov goodness-of-fit test.

        Args:
            data: 1D array of observations
            candidates: List of distribution names to try

        Returns:
            Dict with best distribution, parameters, and goodness-of-fit
        """
        if candidates is None:
            candidates = list(cls.DISTRIBUTIONS.keys())

        results = []
        for dist_name in candidates:
            if dist_name not in cls.DISTRIBUTIONS:
                continue
            dist = cls.DISTRIBUTIONS[dist_name]
            try:
                params = dist.fit(data)
                ks_stat, p_value = stats.kstest(data, dist_name, args=params)
                aic = 2 * len(params) - 2 * np.sum(
                    np.log(np.maximum(dist.pdf(data, *params), 1e-10))
                )
                results.append({
                    "distribution": dist_name,
                    "parameters": [round(p, 4) for p in params],
                    "ks_statistic": round(ks_stat, 4),
                    "p_value": round(p_value, 4),
                    "aic": round(aic, 2),
                })
            except Exception as e:
                logger.debug("distribution_fit_failed", dist=dist_name, error=str(e))
                continue

        if not results:
            return {"error": "No distribution could be fitted"}

        # Select best by AIC
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


# Singleton instances for use across services
bayesian_updater = BayesianUpdater()
kde_estimator = KernelDensityEstimator()
bootstrap = BootstrapInference()
hypothesis_tester = HypothesisTester()
distribution_fitter = DistributionFitter()
