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


# ---------------------------------------------------------------------------
# Cluster Analysis (STA 442)
# ---------------------------------------------------------------------------


class ClusterAnalyzer:
    """
    Cluster Analysis (STA 442 — Multivariate Analysis).

    Implements K-means clustering with k-means++ initialization,
    silhouette score evaluation, and elbow method for optimal k.

    K-means partitions n observations into k clusters by minimizing
    the within-cluster sum of squares (WCSS):

        argmin Σᵢ Σₓ∈Cᵢ ‖x - μᵢ‖²

    where μᵢ is the centroid of cluster Cᵢ.

    Used by:
    - Soko Pulse: Market segmentation (group similar trader behaviors)
    - Alama Score: Risk grouping (cluster borrowers by risk profile)
    - Jamii Insights: Socioeconomic segmentation

    Algorithm: Lloyd's algorithm with k-means++ initialization.
    k-means++ selects initial centroids that are spread out,
    improving convergence and final clustering quality.
    """

    @staticmethod
    def _kmeans_plus_plus_init(
        data: np.ndarray, k: int, rng: np.random.RandomState,
    ) -> np.ndarray:
        """
        k-means++ initialization (Arthur & Vassilvitskii, 2007).

        Selects initial centroids that are well-separated:
        1. Choose first centroid uniformly at random.
        2. For each subsequent centroid, choose point x with probability
           proportional to D(x)², where D(x) is distance to nearest
           existing centroid.

        This gives O(log k)-competitive approximation vs optimal.

        Args:
            data: (n, d) data matrix
            k: Number of clusters
            rng: Random state for reproducibility

        Returns:
            (k, d) array of initial centroids
        """
        n, d = data.shape
        centroids = np.empty((k, d), dtype=data.dtype)

        # Step 1: first centroid chosen uniformly at random
        idx = rng.randint(n)
        centroids[0] = data[idx]

        # Step 2: choose remaining centroids proportional to D(x)²
        for i in range(1, k):
            # Compute min distance squared to any existing centroid
            dists = np.min(
                np.linalg.norm(data[:, np.newaxis] - centroids[:i], axis=2) ** 2,
                axis=1,
            )
            # Probability proportional to distance squared
            probs = dists / dists.sum()
            cumprobs = np.cumsum(probs)
            r = rng.random()
            idx = int(np.searchsorted(cumprobs, r))
            idx = min(idx, n - 1)
            centroids[i] = data[idx]

        return centroids

    @staticmethod
    def kmeans(
        data: np.ndarray,
        k: int,
        max_iter: int = 300,
        tol: float = 1e-6,
        n_init: int = 10,
        seed: int = 42,
    ) -> Dict[str, Any]:
        """
        K-means clustering (Lloyd's algorithm with k-means++ init).

        Lloyd's algorithm:
        1. Initialize k centroids (k-means++)
        2. Assign each point to nearest centroid
        3. Recompute centroids as cluster means
        4. Repeat 2-3 until convergence (centroid shift < tol)
        5. Repeat 1-4 for n_init runs, keep best

        Args:
            data: (n, d) data matrix
            k: Number of clusters
            max_iter: Maximum iterations per run
            tol: Convergence tolerance (centroid shift)
            n_init: Number of independent runs (best kept)
            seed: Random seed

        Returns:
            Dict with labels, centroids, inertia, iterations, converged
        """
        data = np.asarray(data, dtype=float)
        n, d = data.shape

        if k < 1:
            raise ValueError("k must be >= 1")
        if k > n:
            raise ValueError("k cannot exceed number of data points")

        best_result = None
        best_inertia = np.inf
        rng = np.random.RandomState(seed)

        for run in range(n_init):
            # Initialize centroids with k-means++
            centroids = ClusterAnalyzer._kmeans_plus_plus_init(data, k, rng)

            labels = np.zeros(n, dtype=int)
            converged = False

            for iteration in range(max_iter):
                # Assignment step: assign each point to nearest centroid
                dists = np.linalg.norm(
                    data[:, np.newaxis] - centroids[np.newaxis, :], axis=2
                )
                new_labels = np.argmin(dists, axis=1)

                # Update step: recompute centroids
                new_centroids = np.empty_like(centroids)
                for j in range(k):
                    members = data[new_labels == j]
                    if len(members) > 0:
                        new_centroids[j] = members.mean(axis=0)
                    else:
                        # Empty cluster: reinitialize randomly
                        new_centroids[j] = data[rng.randint(n)]

                # Check convergence
                shift = float(np.linalg.norm(new_centroids - centroids))
                centroids = new_centroids
                labels = new_labels

                if shift < tol:
                    converged = True
                    break

            # Compute inertia (WCSS)
            inertia = 0.0
            for j in range(k):
                members = data[labels == j]
                if len(members) > 0:
                    inertia += float(np.sum((members - centroids[j]) ** 2))

            if inertia < best_inertia:
                best_inertia = inertia
                best_result = {
                    "labels": labels.copy(),
                    "centroids": centroids.copy(),
                    "inertia": round(inertia, 4),
                    "iterations": iteration + 1,
                    "converged": converged,
                    "k": k,
                    "n": n,
                    "n_init": n_init,
                }

        # Compute cluster sizes
        labels = best_result["labels"]
        best_result["cluster_sizes"] = {
            int(j): int(np.sum(labels == j)) for j in range(k)
        }

        return best_result

    @staticmethod
    def silhouette_score(
        data: np.ndarray, labels: np.ndarray,
    ) -> Dict[str, Any]:
        """
        Silhouette score for cluster quality evaluation.

        For each point i:
            a(i) = mean distance to other points in same cluster
            b(i) = min mean distance to points in other clusters
            s(i) = (b(i) - a(i)) / max(a(i), b(i))

        Overall score = mean s(i) ∈ [-1, 1]
        - Near +1: well-clustered (point closer to own cluster)
        - Near 0: on boundary between clusters
        - Near -1: possibly mis-clustered

        Args:
            data: (n, d) data matrix
            labels: (n,) cluster assignments

        Returns:
            Dict with overall score, per-cluster scores, per-sample scores
        """
        data = np.asarray(data, dtype=float)
        labels = np.asarray(labels)
        n = len(data)
        k = len(set(labels))

        if k < 2:
            return {
                "overall_score": 0.0,
                "cluster_scores": {},
                "n_clusters": k,
                "message": "Silhouette requires at least 2 clusters",
            }

        # Compute pairwise distance matrix
        dist_matrix = np.linalg.norm(
            data[:, np.newaxis] - data[np.newaxis, :], axis=2
        )

        sample_scores = np.zeros(n)
        cluster_scores = {}

        for i in range(n):
            own_cluster = labels[i]
            mask_own = labels == own_cluster
            mask_own[i] = False  # Exclude self
            n_own = np.sum(mask_own)

            # a(i): mean intra-cluster distance
            if n_own > 0:
                a_i = float(np.mean(dist_matrix[i, mask_own]))
            else:
                a_i = 0.0

            # b(i): min mean distance to other clusters
            b_i = np.inf
            for j in range(k):
                if j == own_cluster:
                    continue
                mask_other = labels == j
                if np.sum(mask_other) > 0:
                    mean_dist = float(np.mean(dist_matrix[i, mask_other]))
                    b_i = min(b_i, mean_dist)

            if b_i == np.inf:
                b_i = 0.0

            denom = max(a_i, b_i)
            sample_scores[i] = (b_i - a_i) / denom if denom > 0 else 0.0

        # Per-cluster average
        for j in range(k):
            mask = labels == j
            if np.sum(mask) > 0:
                cluster_scores[int(j)] = round(float(np.mean(sample_scores[mask])), 4)

        return {
            "overall_score": round(float(np.mean(sample_scores)), 4),
            "cluster_scores": cluster_scores,
            "n_clusters": k,
            "n_samples": n,
            "per_sample_scores": sample_scores,
        }

    @staticmethod
    def elbow_method(
        data: np.ndarray,
        k_range: Optional[List[int]] = None,
        max_k: int = 10,
        n_init: int = 10,
        seed: int = 42,
    ) -> Dict[str, Any]:
        """
        Elbow method for selecting optimal number of clusters.

        Runs K-means for k = 1, 2, ..., max_k and plots WCSS (inertia)
        vs k. The "elbow" — the point where marginal WCSS reduction
        drops sharply — indicates the optimal k.

        Quantified by computing the rate of change ("delta") and finding
        the k where the second derivative ("acceleration") is maximized.

        Args:
            data: (n, d) data matrix
            k_range: Specific k values to try (default: 2 to max_k)
            max_k: Maximum k to try if k_range not given
            n_init: Number of K-means runs per k
            seed: Random seed

        Returns:
            Dict with WCSS per k, recommended k, and all scores
        """
        data = np.asarray(data, dtype=float)
        n = data.shape[0]

        if k_range is None:
            max_k_eff = min(max_k, n - 1)
            k_range = list(range(2, max_k_eff + 1))

        results = []
        for k in k_range:
            result = ClusterAnalyzer.kmeans(data, k=k, n_init=n_init, seed=seed)
            sil = ClusterAnalyzer.silhouette_score(data, result["labels"])
            results.append({
                "k": k,
                "inertia": result["inertia"],
                "silhouette": sil["overall_score"],
                "cluster_sizes": result["cluster_sizes"],
            })

        # Compute deltas (marginal WCSS reduction)
        for i in range(len(results)):
            if i == 0:
                results[i]["delta"] = None
                results[i]["acceleration"] = None
            else:
                delta = results[i - 1]["inertia"] - results[i]["inertia"]
                results[i]["delta"] = round(delta, 4)
                if i >= 2:
                    accel = results[i - 1]["delta"] - delta
                    results[i]["acceleration"] = round(accel, 4)
                else:
                    results[i]["acceleration"] = None

        # Recommended k: maximize acceleration (elbow point)
        # Fallback to best silhouette if no clear elbow
        accels = [
            (r["k"], r["acceleration"])
            for r in results
            if r["acceleration"] is not None
        ]
        if accels:
            recommended_k = max(accels, key=lambda x: x[1])[0]
        else:
            recommended_k = max(results, key=lambda x: x["silhouette"])["k"]

        return {
            "results": results,
            "recommended_k": recommended_k,
            "method": "elbow + silhouette fallback",
            "n_samples": n,
            "k_range_tested": [r["k"] for r in results],
        }

    @staticmethod
    def segment_market(
        data: np.ndarray,
        feature_names: Optional[List[str]] = None,
        max_k: int = 8,
        seed: int = 42,
    ) -> Dict[str, Any]:
        """
        Market segmentation using K-means clustering.

        High-level API for Soko Pulse market segmentation.
        Automatically selects optimal k, runs clustering,
        and produces interpretable segment profiles.

        Args:
            data: (n, d) feature matrix (e.g., trader metrics)
            feature_names: Names for each feature dimension
            max_k: Maximum clusters to try
            seed: Random seed

        Returns:
            Dict with segments, profiles, quality metrics
        """
        data = np.asarray(data, dtype=float)
        n, d = data.shape

        if feature_names is None:
            feature_names = [f"feature_{i}" for i in range(d)]

        # Find optimal k
        elbow = ClusterAnalyzer.elbow_method(data, max_k=max_k, seed=seed)
        optimal_k = elbow["recommended_k"]

        # Run clustering with optimal k
        result = ClusterAnalyzer.kmeans(data, k=optimal_k, seed=seed)
        sil = ClusterAnalyzer.silhouette_score(data, result["labels"])

        # Build segment profiles
        segments = []
        for j in range(optimal_k):
            mask = result["labels"] == j
            members = data[mask]
            profile = {}
            for fi, fname in enumerate(feature_names):
                col = members[:, fi]
                profile[fname] = {
                    "mean": round(float(np.mean(col)), 4),
                    "std": round(float(np.std(col)), 4),
                    "min": round(float(np.min(col)), 4),
                    "max": round(float(np.max(col)), 4),
                    "median": round(float(np.median(col)), 4),
                }
            segments.append({
                "segment_id": j,
                "size": int(np.sum(mask)),
                "proportion": round(float(np.mean(mask)), 4),
                "centroid": [round(float(c), 4) for c in result["centroids"][j]],
                "profile": profile,
            })

        return {
            "optimal_k": optimal_k,
            "silhouette_score": sil["overall_score"],
            "inertia": result["inertia"],
            "converged": result["converged"],
            "segments": segments,
            "elbow_analysis": elbow,
            "labels": result["labels"].tolist(),
        }


class MonteCarloEngine:
    """
    Monte Carlo simulation methods (STA 347 — Stochastic Processes).

    Provides simulation-based inference when analytical solutions are
    intractable or when full distributional characterisation is needed.

    Methods:
    - Crude Monte Carlo integration
    - Importance sampling for variance reduction
    - Bootstrap hypothesis testing (extends BootstrapInference)
    - Simulation-based confidence intervals

    Use Cases:
    - Alama Score: Revenue distribution simulation for credit risk assessment
    - Soko Pulse: Price volatility simulation under uncertainty
    - Jamii Insights: Population-level metric simulation

    References:
    - Robert, C.P. & Casella, G. (2004). Monte Carlo Statistical Methods.
      2nd ed. Springer.
    - Kroese, D.P., Taimre, T., & Botev, Z.I. (2011). Handbook of Monte Carlo
      Methods. Wiley.
    - Efron, B. & Tibshirani, R.J. (1993). An Introduction to the Bootstrap.
      Chapman & Hall.
    """

    @staticmethod
    def crude_integration(
        func: callable,
        lower: float,
        upper: float,
        n_samples: int = 100000,
        seed: int = 42,
    ) -> Dict[str, float]:
        """
        Crude Monte Carlo integration.

        Estimates ∫_a^b f(x) dx ≈ (b-a)/n Σᵢ f(Xᵢ)
        where Xᵢ ~ Uniform(a, b).

        Args:
            func: Integrand f(x)
            lower: Lower bound of integration
            upper: Upper bound of integration
            n_samples: Number of Monte Carlo samples
            seed: Random seed

        Returns:
            Dict with estimate, standard error, and 95% CI
        """
        rng = np.random.RandomState(seed)
        samples = rng.uniform(lower, upper, size=n_samples)
        func_values = np.array([func(x) for x in samples])

        interval_length = upper - lower
        estimate = interval_length * np.mean(func_values)
        se = interval_length * np.std(func_values) / np.sqrt(n_samples)

        return {
            "estimate": round(float(estimate), 6),
            "standard_error": round(float(se), 6),
            "ci_lower": round(float(estimate - 1.96 * se), 6),
            "ci_upper": round(float(estimate + 1.96 * se), 6),
            "n_samples": n_samples,
            "method": "crude_monte_carlo",
        }

    @staticmethod
    def importance_sampling(
        func: callable,
        proposal_sampler: callable,
        proposal_pdf: callable,
        target_pdf: Optional[callable] = None,
        n_samples: int = 100000,
        seed: int = 42,
    ) -> Dict[str, float]:
        """
        Importance sampling for variance reduction.

        Estimates E_p[f(X)] ≈ (1/n) Σᵢ f(Xᵢ)·w(Xᵢ)
        where w(x) = p(x)/q(x) and Xᵢ ~ q (proposal).

        When target_pdf is None, estimates ∫ f(x) dx using
        the proposal distribution.

        Args:
            func: Function f(x) to integrate/average
            proposal_sampler: Function that returns n samples from proposal q
            proposal_pdf: Proposal density q(x)
            target_pdf: Target density p(x). If None, estimates ∫f(x)dx.
            n_samples: Number of samples
            seed: Random seed

        Returns:
            Dict with estimate, effective sample size, and diagnostics
        """
        rng = np.random.RandomState(seed)
        samples = proposal_sampler(n_samples, rng)

        func_values = np.array([func(x) for x in samples])
        proposal_vals = np.array([proposal_pdf(x) for x in samples])

        # Avoid division by zero
        proposal_vals = np.maximum(proposal_vals, 1e-300)

        if target_pdf is not None:
            target_vals = np.array([target_pdf(x) for x in samples])
            weights = target_vals / proposal_vals
        else:
            # Estimating integral: weight = 1/q(x)
            weights = 1.0 / proposal_vals

        # Normalised importance weights
        weights_normalized = weights / weights.sum()

        estimate = np.sum(weights_normalized * func_values)

        # Effective sample size: ESS = 1/Σw̃ᵢ²
        ess = 1.0 / np.sum(weights_normalized ** 2)

        # Weighted variance for SE
        weighted_var = np.sum(weights_normalized * (func_values - estimate) ** 2)
        se = np.sqrt(weighted_var / ess)

        return {
            "estimate": round(float(estimate), 6),
            "standard_error": round(float(se), 6),
            "ci_lower": round(float(estimate - 1.96 * se), 6),
            "ci_upper": round(float(estimate + 1.96 * se), 6),
            "effective_sample_size": round(float(ess), 1),
            "efficiency": round(float(ess / n_samples), 4),
            "n_samples": n_samples,
            "method": "importance_sampling",
        }

    @staticmethod
    def bootstrap_hypothesis_test(
        sample1: np.ndarray,
        sample2: np.ndarray,
        statistic_func: callable,
        n_bootstrap: int = 10000,
        alternative: str = "two-sided",
        seed: int = 42,
    ) -> Dict[str, Any]:
        """
        Bootstrap hypothesis test.

        Tests H₀: θ₁ = θ₂ against H₁: θ₁ ≠ θ₂ (or one-sided).
        Uses the permutation/bootstrap distribution of the test statistic
        to compute p-values without distributional assumptions.

        Procedure:
        1. Compute observed test statistic T_obs = stat(sample1) - stat(sample2)
        2. Pool samples and resample under H₀ (permutation)
        3. Compute bootstrap distribution of T
        4. p-value = P(|T| ≥ |T_obs|) under H₀

        Args:
            sample1: First sample
            sample2: Second sample
            statistic_func: Function computing the statistic of interest
            n_bootstrap: Number of bootstrap/permutation resamples
            alternative: 'two-sided', 'greater', 'less'
            seed: Random seed

        Returns:
            Dict with test statistic, p-value, and bootstrap distribution info
        """
        sample1 = np.asarray(sample1, dtype=float)
        sample2 = np.asarray(sample2, dtype=float)
        rng = np.random.RandomState(seed)

        n1 = len(sample1)
        n2 = len(sample2)
        observed_diff = statistic_func(sample1) - statistic_func(sample2)

        # Permutation test: pool and resample
        pooled = np.concatenate([sample1, sample2])
        n_total = n1 + n2

        perm_stats = np.zeros(n_bootstrap)
        for i in range(n_bootstrap):
            perm = rng.permutation(n_total)
            s1_perm = pooled[perm[:n1]]
            s2_perm = pooled[perm[n1:]]
            perm_stats[i] = statistic_func(s1_perm) - statistic_func(s2_perm)

        # Compute p-value
        if alternative == "two-sided":
            p_value = np.mean(np.abs(perm_stats) >= np.abs(observed_diff))
        elif alternative == "greater":
            p_value = np.mean(perm_stats >= observed_diff)
        elif alternative == "less":
            p_value = np.mean(perm_stats <= observed_diff)
        else:
            raise ValueError(f"Unknown alternative: {alternative}")

        return {
            "observed_statistic": round(float(observed_diff), 4),
            "p_value": round(float(p_value), 6),
            "significant_at_05": p_value < 0.05,
            "significant_at_01": p_value < 0.01,
            "n_bootstrap": n_bootstrap,
            "alternative": alternative,
            "permutation_mean": round(float(np.mean(perm_stats)), 4),
            "permutation_std": round(float(np.std(perm_stats)), 4),
            "test_name": "Permutation/bootstrap hypothesis test",
            "interpretation": (
                f"{'Reject' if p_value < 0.05 else 'Fail to reject'} null hypothesis "
                f"at 5% significance (p={p_value:.4f})"
            ),
        }

    @staticmethod
    def simulation_confidence_interval(
        data: np.ndarray,
        statistic_func: callable,
        n_simulations: int = 10000,
        confidence: float = 0.95,
        method: str = "percentile",
        seed: int = 42,
    ) -> Dict[str, float]:
        """
        Simulation-based confidence intervals.

        Supports multiple methods:
        - 'percentile': Direct percentile of bootstrap distribution
        - 'bc': Bias-corrected (BC) percentile interval
        - 'bca': Bias-corrected and accelerated (BCa) interval

        Args:
            data: Observed data
            statistic_func: Function computing the statistic
            n_simulations: Number of bootstrap simulations
            confidence: Confidence level
            method: CI method ('percentile', 'bc', 'bca')
            seed: Random seed

        Returns:
            Dict with estimate, CI bounds, method, and diagnostics
        """
        data = np.asarray(data, dtype=float)
        rng = np.random.RandomState(seed)
        n = len(data)
        alpha = 1 - confidence

        original_stat = statistic_func(data)
        boot_stats = np.zeros(n_simulations)

        for i in range(n_simulations):
            sample = rng.choice(data, size=n, replace=True)
            boot_stats[i] = statistic_func(sample)

        if method == "percentile":
            ci_lower = np.percentile(boot_stats, 100 * alpha / 2)
            ci_upper = np.percentile(boot_stats, 100 * (1 - alpha / 2))

        elif method == "bc":
            # Bias-corrected
            z0 = stats.norm.ppf(np.mean(boot_stats < original_stat))
            z_alpha = stats.norm.ppf([alpha / 2, 1 - alpha / 2])
            p_vals = stats.norm.cdf(2 * z0 + z_alpha)
            ci_lower = np.percentile(boot_stats, 100 * p_vals[0])
            ci_upper = np.percentile(boot_stats, 100 * p_vals[1])

        elif method == "bca":
            # Bias-corrected and accelerated
            z0 = stats.norm.ppf(np.mean(boot_stats < original_stat))

            # Acceleration factor via jackknife
            jackknife_stats = np.zeros(n)
            for i in range(n):
                jack_sample = np.delete(data, i)
                jackknife_stats[i] = statistic_func(jack_sample)
            jack_mean = np.mean(jackknife_stats)
            numer = np.sum((jack_mean - jackknife_stats) ** 3)
            denom = 6 * (np.sum((jack_mean - jackknife_stats) ** 2) ** 1.5)
            a_hat = numer / denom if abs(denom) > 1e-12 else 0.0

            z_alpha = stats.norm.ppf([alpha / 2, 1 - alpha / 2])
            p_vals = stats.norm.cdf(z0 + (z0 + z_alpha) / (1 - a_hat * (z0 + z_alpha)))
            ci_lower = np.percentile(boot_stats, 100 * p_vals[0])
            ci_upper = np.percentile(boot_stats, 100 * p_vals[1])

        else:
            raise ValueError(f"Unknown CI method: {method}")

        return {
            "estimate": round(float(original_stat), 4),
            "ci_lower": round(float(ci_lower), 4),
            "ci_upper": round(float(ci_upper), 4),
            "bootstrap_se": round(float(np.std(boot_stats)), 4),
            "confidence": confidence,
            "method": method,
            "n_simulations": n_simulations,
        }

    @staticmethod
    def revenue_distribution_simulation(
        base_revenue: float,
        growth_mean: float,
        growth_std: float,
        n_periods: int = 12,
        n_simulations: int = 10000,
        seed: int = 42,
    ) -> Dict[str, Any]:
        """
        Simulate revenue distribution over multiple periods.

        Models revenue as a geometric Brownian motion:
            R(t+1) = R(t) · exp((μ - σ²/2)·dt + σ·√dt·Z)
        where Z ~ N(0,1).

        Use case: Alama Score — revenue distribution simulation for credit
        risk assessment of small businesses.

        Args:
            base_revenue: Starting revenue
            growth_mean: Expected log revenue growth rate (annualised)
            growth_std: Volatility of log revenue growth
            n_periods: Number of periods to simulate
            n_simulations: Number of simulation paths
            seed: Random seed

        Returns:
            Dict with terminal distribution statistics and percentiles
        """
        rng = np.random.RandomState(seed)

        # Simulate paths
        dt = 1.0 / 12  # Monthly steps if n_periods is months
        paths = np.zeros((n_simulations, n_periods + 1))
        paths[:, 0] = base_revenue

        for t in range(n_periods):
            z = rng.randn(n_simulations)
            paths[:, t + 1] = paths[:, t] * np.exp(
                (growth_mean - 0.5 * growth_std ** 2) * dt + growth_std * np.sqrt(dt) * z
            )

        terminal = paths[:, -1]

        return {
            "base_revenue": base_revenue,
            "terminal_mean": round(float(np.mean(terminal)), 2),
            "terminal_median": round(float(np.median(terminal)), 2),
            "terminal_std": round(float(np.std(terminal)), 2),
            "percentile_5": round(float(np.percentile(terminal, 5)), 2),
            "percentile_25": round(float(np.percentile(terminal, 25)), 2),
            "percentile_75": round(float(np.percentile(terminal, 75)), 2),
            "percentile_95": round(float(np.percentile(terminal, 95)), 2),
            "prob_decline": round(float(np.mean(terminal < base_revenue)), 4),
            "prob_growth_10pct": round(float(np.mean(terminal > base_revenue * 1.1)), 4),
            "n_periods": n_periods,
            "n_simulations": n_simulations,
            "growth_mean": growth_mean,
            "growth_std": growth_std,
        }


class MCMCSampler:
    """
    Markov Chain Monte Carlo sampling (STA 347 — Stochastic Processes).

    Implements Metropolis-Hastings algorithm for drawing samples from
    arbitrary (unnormalised) posterior distributions. Enables full
    Bayesian inference beyond conjugate prior models.

    The Metropolis-Hastings algorithm:
    1. Start at θ₀
    2. Propose θ* ~ q(θ*|θₜ)
    3. Accept with probability α = min(1, [π(θ*)q(θₜ|θ*)] / [π(θₜ)q(θ*|θₜ)])
    4. θₜ₊₁ = θ* if accepted, else θₜ

    Use Cases:
    - Alama Score: Full posterior inference for credit scoring models with
      non-conjugate likelihoods (e.g., logistic regression with informative priors)
    - Soko Pulse: Bayesian demand estimation with complex priors
    - Jamii Insights: Hierarchical models for financial inclusion

    References:
    - Metropolis, N. et al. (1953). "Equation of State Calculations by Fast
      Computing Machines." J. Chem. Phys., 21(6), 1087-1092.
    - Hastings, W.K. (1970). "Monte Carlo Sampling Methods Using Markov
      Chains and Their Applications." Biometrika, 57(1), 97-109.
    - Gelman, A. & Rubin, D.B. (1992). "Inference from Iterative Simulation
      Using Multiple Sequences." Statistical Science, 7(4), 457-472.
    - Brooks, S. et al. (2011). Handbook of Markov Chain Monte Carlo. CRC Press.
    """

    def __init__(self, seed: int = 42):
        self.rng = np.random.RandomState(seed)

    def metropolis_hastings(
        self,
        log_target: callable,
        initial_state: np.ndarray,
        n_samples: int = 10000,
        proposal_std: Optional[np.ndarray] = None,
        burn_in: int = 1000,
        thin: int = 1,
    ) -> Dict[str, Any]:
        """
        Metropolis-Hastings sampler with random walk proposal.

        Proposal: θ* = θₜ + ε, where ε ~ N(0, Σ)
        This is a symmetric random walk, so the Hastings ratio reduces to
        α = min(1, π(θ*) / π(θₜ)).

        Args:
            log_target: Log of the (unnormalised) target density π(θ)
            initial_state: Starting parameter vector θ₀
            n_samples: Total number of MCMC iterations (before burn-in/thinning)
            proposal_std: Std dev of Gaussian proposal for each dimension.
                          If None, uses 0.1 * |initial_state| (min 0.1)
            burn_in: Number of initial samples to discard
            thin: Keep every thin-th sample (to reduce autocorrelation)

        Returns:
            Dict with samples, acceptance rate, diagnostics, and summary
        """
        initial_state = np.asarray(initial_state, dtype=float)
        dim = len(initial_state)

        if proposal_std is None:
            proposal_std = np.maximum(0.1 * np.abs(initial_state), 0.1)
        else:
            proposal_std = np.asarray(proposal_std, dtype=float)

        # Storage
        all_samples = np.zeros((n_samples, dim))
        current = initial_state.copy()
        current_log_prob = log_target(current)
        n_accepted = 0

        for i in range(n_samples):
            # Propose
            proposal = current + self.rng.randn(dim) * proposal_std
            proposal_log_prob = log_target(proposal)

            # Acceptance ratio (log scale)
            log_alpha = proposal_log_prob - current_log_prob

            # Accept/reject
            if np.log(self.rng.rand()) < log_alpha:
                current = proposal
                current_log_prob = proposal_log_prob
                n_accepted += 1

            all_samples[i] = current

        # Apply burn-in and thinning
        post_burnin = all_samples[burn_in:]
        thinned = post_burnin[::thin]

        acceptance_rate = n_accepted / n_samples

        # Summary statistics per dimension
        summary = []
        for d in range(dim):
            chain = thinned[:, d]
            summary.append({
                "mean": round(float(np.mean(chain)), 4),
                "std": round(float(np.std(chain)), 4),
                "median": round(float(np.median(chain)), 4),
                "ci_95": (
                    round(float(np.percentile(chain, 2.5)), 4),
                    round(float(np.percentile(chain, 97.5)), 4),
                ),
            })

        return {
            "samples": thinned,
            "n_samples_effective": len(thinned),
            "acceptance_rate": round(float(acceptance_rate), 4),
            "burn_in": burn_in,
            "thin": thin,
            "n_total_iterations": n_samples,
            "summary": summary,
            "convergence": self._check_convergence_single(thinned),
        }

    @staticmethod
    def gelman_rubin_rhat(chains: List[np.ndarray]) -> Dict[str, Any]:
        """
        Gelman-Rubin R-hat convergence diagnostic.

        Compares within-chain and between-chain variance.
        R-hat < 1.1 generally indicates convergence.

        Formula:
            W = mean of within-chain variances
            B = n × variance of chain means
            R-hat = sqrt((W·(n-1)/n + B/n) / W)

        Args:
            chains: List of arrays, each a separate MCMC chain
                    Shape: (n_chains,) each with (n_samples, dim)
                    All chains must have the same shape.

        Returns:
            Dict with R-hat per dimension and overall diagnostic
        """
        if len(chains) < 2:
            raise ValueError("Need at least 2 chains for R-hat diagnostic")

        chains = [np.asarray(c) for c in chains]
        n_chains = len(chains)
        n_samples = chains[0].shape[0]
        dim = chains[0].shape[1] if chains[0].ndim > 1 else 1

        rhat_values = []

        for d in range(dim):
            if dim > 1:
                chain_data = [c[:, d] for c in chains]
            else:
                chain_data = [c.ravel() for c in chains]

            chain_means = [np.mean(c) for c in chain_data]
            chain_vars = [np.var(c, ddof=1) for c in chain_data]

            W = np.mean(chain_vars)  # Within-chain variance
            B = n_samples * np.var(chain_means, ddof=1)  # Between-chain variance

            # Pooled variance estimate
            var_hat = ((n_samples - 1) / n_samples) * W + B / n_samples

            rhat = np.sqrt(var_hat / W) if W > 0 else float("inf")
            rhat_values.append(round(float(rhat), 4))

        max_rhat = max(rhat_values)
        converged = max_rhat < 1.1

        return {
            "rhat_per_dimension": rhat_values,
            "rhat_max": round(max_rhat, 4),
            "converged": converged,
            "threshold": 1.1,
            "n_chains": n_chains,
            "n_samples_per_chain": n_samples,
            "diagnostic": "Gelman-Rubin (1992)",
            "interpretation": (
                f"{'Converged' if converged else 'NOT converged'}: "
                f"max R-hat = {max_rhat:.4f} ({'< 1.1 ✓' if converged else '≥ 1.1 ✗'})"
            ),
        }

    @staticmethod
    def _check_convergence_single(samples: np.ndarray) -> Dict[str, Any]:
        """
        Basic convergence diagnostics for a single chain.

        Checks:
        - Effective sample size (ESS) via initial positive autocorrelation sequence
        - Geweke diagnostic: compares first 10% vs last 50% of chain
        """
        n, dim = samples.shape if samples.ndim > 1 else (len(samples), 1)
        if samples.ndim == 1:
            samples = samples.reshape(-1, 1)

        diagnostics = []
        for d in range(dim):
            chain = samples[:, d]
            n = len(chain)

            # ESS approximation via initial monotone sequence estimator
            # (simple autocorrelation truncation)
            max_lag = min(n // 2, 200)
            acf_vals = []
            mean = np.mean(chain)
            var = np.var(chain, ddof=1)
            if var > 0:
                for lag in range(max_lag):
                    acf = np.mean((chain[:n - lag] - mean) * (chain[lag:] - mean)) / var
                    acf_vals.append(acf)
                    if acf < 0:
                        break
                # ESS = n / (1 + 2·Σ τₖ)
                tau = 1 + 2 * sum(acf_vals[1:]) if len(acf_vals) > 1 else 1.0
                ess = n / max(tau, 1.0)
            else:
                ess = float(n)

            # Geweke diagnostic
            n1 = max(int(0.1 * n), 10)
            n2 = max(int(0.5 * n), 10)
            first_part = chain[:n1]
            last_part = chain[-n2:]
            mean_diff = np.mean(first_part) - np.mean(last_part)
            se_diff = np.sqrt(
                np.var(first_part, ddof=1) / n1 + np.var(last_part, ddof=1) / n2
            )
            geweke_z = mean_diff / se_diff if se_diff > 0 else 0.0
            geweke_p = 2 * (1 - stats.norm.cdf(abs(geweke_z)))

            diagnostics.append({
                "dimension": d,
                "effective_sample_size": round(float(ess), 1),
                "ess_ratio": round(float(ess / n), 4),
                "geweke_z": round(float(geweke_z), 4),
                "geweke_p_value": round(float(geweke_p), 4),
                "geweke_converged": geweke_p > 0.05,
            })

        return {
            "per_dimension": diagnostics,
            "all_converged": all(d["geweke_converged"] for d in diagnostics),
        }


# ---------------------------------------------------------------------------
# Principal Component Analysis (STA 442)
# ---------------------------------------------------------------------------


class PCAAnalyzer:
    """
    Principal Component Analysis (STA 442 — Applied Multivariate Analysis).

    Reduces dimensionality by projecting data onto directions of maximum
    variance via eigendecomposition of the covariance matrix.

    Model:
        Σ = PΛP'  (eigendecomposition)
        Z = XP    (projection onto principal components)

    where Σ = covariance matrix, Λ = diagonal eigenvalue matrix,
    P = eigenvector matrix, Z = scores (reduced data).

    Proportion of variance explained by PCₖ = λₖ / Σλⱼ.

    Used by:
    - Alama Score: Dimensionality reduction of borrower feature vectors
      (activity, stability, growth, consistency, diversity) into
      uncorrelated principal components for credit scoring
    - Biashara Pulse: Composite index construction from correlated
      economic indicators
    - Jamii Insights: Socioeconomic dimension reduction for community
      profiling

    References:
    - Jolliffe, I.T. (2002). Principal Component Analysis. 2nd ed. Springer.
    - Hotelling, H. (1933). Analysis of a complex of statistical variables
      into principal components. Journal of Educational Psychology, 24(6), 417-441.
    """

    @staticmethod
    def fit_transform(
        X: np.ndarray,
        n_components: int = 3,
        standardize: bool = False,
    ) -> Dict[str, Any]:
        """
        Fit PCA and transform data.

        Steps:
        1. Center data (subtract mean)
        2. Compute covariance matrix Σ = (1/(n-1)) X'X
        3. Eigendecomposition: Σ = PΛP'
        4. Sort eigenvalues descending
        5. Project: Z = X_centered @ P[:, :k]

        Args:
            X: data matrix (n × p)
            n_components: number of components to retain
            standardize: if True, standardize to unit variance before PCA

        Returns:
            Dict with reduced_data, eigenvalues, loadings, variance_explained,
            cumulative_variance, and reconstruction
        """
        X = np.asarray(X, dtype=float)
        n, p = X.shape

        # Center
        mean = np.mean(X, axis=0)
        X_centered = X - mean

        # Optional standardization (correlation PCA vs covariance PCA)
        scale = None
        if standardize:
            scale = np.std(X, axis=0, ddof=1)
            scale = np.maximum(scale, 1e-10)
            X_centered = X_centered / scale

        # Covariance matrix
        cov = np.cov(X_centered, rowvar=False)
        if cov.ndim == 1:
            cov = cov.reshape(1, 1)

        # Eigendecomposition
        eigenvalues, eigenvectors = np.linalg.eigh(cov)

        # Sort descending
        idx = np.argsort(eigenvalues)[::-1]
        eigenvalues = eigenvalues[idx]
        eigenvectors = eigenvectors[:, idx]

        # Ensure non-negative eigenvalues (numerical noise)
        eigenvalues = np.maximum(eigenvalues, 0)

        # Take first k components
        k = min(n_components, p)
        loadings = eigenvectors[:, :k]  # p × k
        reduced = X_centered @ loadings  # n × k

        # Variance explained
        total_var = np.sum(eigenvalues)
        var_explained = eigenvalues[:k] / max(total_var, 1e-10)
        cum_var = np.cumsum(var_explained)

        # Reconstruction (inverse transform)
        reconstructed = reduced @ loadings.T + mean
        if scale is not None:
            reconstructed = reconstructed * scale + mean

        return {
            "reduced_data": reduced,
            "eigenvalues": eigenvalues,
            "loadings": loadings,
            "variance_explained": var_explained,
            "cumulative_variance": cum_var,
            "mean": mean,
            "scale": scale,
            "n_components": k,
            "n_features": p,
            "total_variance": total_var,
            "reconstructed": reconstructed,
        }

    @staticmethod
    def select_n_components(
        X: np.ndarray,
        variance_threshold: float = 0.90,
        standardize: bool = False,
    ) -> Dict[str, Any]:
        """
        Select number of components to retain a given variance proportion.

        Uses the cumulative variance threshold method:
        Choose smallest k such that Σⱼ₌₁ᵏ λⱼ / Σλⱼ ≥ threshold.

        Args:
            X: data matrix (n × p)
            variance_threshold: minimum cumulative variance to retain (default 0.90)
            standardize: whether to standardize first

        Returns:
            Dict with recommended k, cumulative variance curve, and elbow info
        """
        result = PCAAnalyzer.fit_transform(X, n_components=X.shape[1], standardize=standardize)
        cum_var = result["cumulative_variance"]
        eigenvalues = result["eigenvalues"]

        # Find k for threshold
        k_threshold = int(np.searchsorted(cum_var, variance_threshold) + 1)
        k_threshold = min(k_threshold, len(cum_var))

        # Elbow: maximize second difference of eigenvalues
        if len(eigenvalues) >= 3:
            diffs = np.diff(eigenvalues)
            diffs2 = np.diff(diffs)
            k_elbow = int(np.argmax(diffs2) + 2)  # +2 because two diffs
        else:
            k_elbow = 1

        return {
            "recommended_k": k_threshold,
            "variance_threshold": variance_threshold,
            "cumulative_variance": [round(float(v), 4) for v in cum_var],
            "eigenvalues": [round(float(v), 4) for v in eigenvalues],
            "k_elbow": k_elbow,
            "method": "cumulative_variance_threshold + elbow",
        }

    @staticmethod
    def interpret_loadings(
        loadings: np.ndarray,
        feature_names: List[str],
        n_components: int = 3,
        threshold: float = 0.3,
    ) -> List[Dict[str, Any]]:
        """
        Interpret PCA loadings to label components.

        For each component, identifies features with highest absolute
        loadings (above threshold) to provide economic interpretation.

        Args:
            loadings: p × k loading matrix
            feature_names: names for each feature
            n_components: number of components to interpret
            threshold: minimum |loading| to include in interpretation

        Returns:
            List of component interpretations
        """
        interpretations = []
        k = min(n_components, loadings.shape[1])

        for j in range(k):
            col = loadings[:, j]
            # Sort by absolute loading
            sorted_idx = np.argsort(np.abs(col))[::-1]
            top_features = []
            for idx in sorted_idx:
                if abs(col[idx]) >= threshold and idx < len(feature_names):
                    top_features.append({
                        "feature": feature_names[idx],
                        "loading": round(float(col[idx]), 4),
                        "direction": "positive" if col[idx] > 0 else "negative",
                    })
            interpretations.append({
                "component": j,
                "top_features": top_features,
                "variance_explained_pct": round(float(np.sum(col ** 2) / len(col) * 100), 1),
            })

        return interpretations


# ---------------------------------------------------------------------------
# Factor Analysis (STA 442)
# ---------------------------------------------------------------------------


class FactorAnalyzer:
    """
    Factor Analysis (STA 442 — Applied Multivariate Analysis).

    Models observed variables as linear combinations of latent factors
    plus unique (error) terms:

        X = μ + Λf + ε

    where Λ = factor loadings (p × m), f = common factors (Var(f) = I),
    ε = unique factors (Var(ε) = Ψ, diagonal).

    Cov(X) = ΛΛ' + Ψ

    Extraction: Iterative principal axis factoring
    Rotation: Varimax (orthogonal) maximizes variance of squared loadings

    Used by:
    - Alama Score: Extract latent creditworthiness factors (Transaction
      Intensity, Financial Discipline, Market Position) from correlated
      borrower features
    - Biashara Pulse: Identify latent economic factors driving
      observed indicators
    - Jamii Insights: Extract latent development factors from
      correlated socioeconomic indicators

    References:
    - Spearman, C. (1904). "General Intelligence," objectively determined
      and measured. American Journal of Psychology, 15(2), 201-292.
    - Kaiser, H.F. (1958). The varimax criterion for analytic rotation in
      factor analysis. Psychometrika, 23(3), 187-200.
    """

    @staticmethod
    def fit(
        X: np.ndarray,
        n_factors: int = 3,
        max_iter: int = 50,
        rotation: str = "varimax",
    ) -> Dict[str, Any]:
        """
        Fit factor analysis model.

        Extraction via iterative principal axis factoring:
        1. Initial communalities from PCA
        2. Replace diagonal of correlation matrix with communalities
        3. Eigendecompose adjusted matrix
        4. Extract loadings for top k factors
        5. Update communalities
        6. Repeat until convergence

        Then apply rotation (varimax by default).

        Args:
            X: data matrix (n × p)
            n_factors: number of latent factors to extract
            max_iter: maximum iterations for communality estimation
            rotation: 'varimax' (orthogonal) or 'none'

        Returns:
            Dict with loadings, communalities, variance explained,
            uniquenesses, and factor correlations
        """
        X = np.asarray(X, dtype=float)
        n, p = X.shape
        X_c = X - np.mean(X, axis=0)

        # Correlation matrix
        R = np.corrcoef(X_c, rowvar=False)
        if R.ndim == 1:
            R = R.reshape(1, 1)

        # Handle NaN in correlation matrix
        R = np.nan_to_num(R, nan=0.0)
        np.fill_diagonal(R, 1.0)

        # Initial communalities from PCA
        eigvals, eigvecs = np.linalg.eigh(R)
        idx = np.argsort(eigvals)[::-1]
        eigvals = eigvals[idx]
        eigvecs = eigvecs[:, idx]

        k = min(n_factors, p)
        loadings = eigvecs[:, :k] * np.sqrt(np.maximum(eigvals[:k], 0))

        # Iterative principal axis factoring
        communalities = np.sum(loadings ** 2, axis=1)
        converged = False
        for iteration in range(max_iter):
            R_adj = R.copy()
            np.fill_diagonal(R_adj, communalities)
            eigvals_i, eigvecs_i = np.linalg.eigh(R_adj)
            idx_i = np.argsort(eigvals_i)[::-1]
            eigvals_i = eigvals_i[idx_i]
            eigvecs_i = eigvecs_i[:, idx_i]
            loadings = eigvecs_i[:, :k] * np.sqrt(np.maximum(eigvals_i[:k], 0))
            new_comm = np.sum(loadings ** 2, axis=1)
            if np.max(np.abs(new_comm - communalities)) < 1e-6:
                communalities = new_comm
                converged = True
                break
            communalities = new_comm

        # Rotation
        if rotation == "varimax" and k > 1:
            rotated_loadings = FactorAnalyzer._varimax(loadings)
        else:
            rotated_loadings = loadings

        # Variance explained
        var_explained = np.sum(rotated_loadings ** 2, axis=0)
        total_var = p
        var_pct = var_explained / max(total_var, 1) * 100

        # Uniquenesses (1 - communality)
        rotated_communalities = np.sum(rotated_loadings ** 2, axis=1)
        uniquenesses = 1 - rotated_communalities

        return {
            "loadings": rotated_loadings,
            "communalities": rotated_communalities,
            "uniquenesses": uniquenesses,
            "variance_explained_pct": var_pct,
            "total_variance_explained_pct": float(np.sum(var_pct)),
            "n_factors": k,
            "n_features": p,
            "converged": converged,
            "rotation": rotation,
        }

    @staticmethod
    def _varimax(loadings: np.ndarray, max_iter: int = 100, tol: float = 1e-6) -> np.ndarray:
        """
        Varimax rotation (Kaiser, 1958).

        Orthogonal rotation that maximizes the variance of squared
        loadings in each column, producing simpler, more interpretable
        factor structure.

        Args:
            loadings: p × k unrotated loading matrix
            max_iter: maximum iterations
            tol: convergence tolerance

        Returns:
            Rotated loading matrix
        """
        p, k = loadings.shape
        R = np.eye(k)

        for _ in range(max_iter):
            rotated = loadings @ R
            B = rotated ** 2
            # Gradient for varimax
            u = np.sum(rotated ** 2, axis=0) * rotated - rotated * np.sum(B, axis=0) / p
            M = loadings.T @ u
            svd_U, _, svd_Vt = np.linalg.svd(M)
            R_new = svd_U @ svd_Vt
            if np.max(np.abs(R_new - R)) < tol:
                R = R_new
                break
            R = R_new

        return loadings @ R

    @staticmethod
    def interpret_factors(
        loadings: np.ndarray,
        feature_names: List[str],
        factor_names: Optional[List[str]] = None,
        threshold: float = 0.3,
    ) -> List[Dict[str, Any]]:
        """
        Interpret factor loadings for economic meaning.

        For each factor, identifies features with highest loadings
        and provides economic interpretation.

        Args:
            loadings: p × k rotated loading matrix
            feature_names: names for each observed variable
            factor_names: optional labels for each factor
            threshold: minimum |loading| to include

        Returns:
            List of factor interpretations
        """
        k = loadings.shape[1]
        if factor_names is None:
            factor_names = [f"Factor_{j+1}" for j in range(k)]

        interpretations = []
        for j in range(k):
            col = loadings[:, j]
            sorted_idx = np.argsort(np.abs(col))[::-1]
            markers = []
            for idx in sorted_idx:
                if abs(col[idx]) >= threshold and idx < len(feature_names):
                    markers.append({
                        "feature": feature_names[idx],
                        "loading": round(float(col[idx]), 4),
                        "direction": "positive" if col[idx] > 0 else "negative",
                    })
            interpretations.append({
                "factor": factor_names[j] if j < len(factor_names) else f"Factor_{j+1}",
                "marker_variables": markers,
                "variance_explained_pct": round(float(np.sum(col ** 2) / len(col) * 100), 1),
            })

        return interpretations


# ---------------------------------------------------------------------------
# Linear Discriminant Analysis (STA 442)
# ---------------------------------------------------------------------------


class DiscriminantAnalyzer:
    """
    Linear Discriminant Analysis (STA 442 — Applied Multivariate Analysis).

    Fisher's LDA finds the projection that maximizes the ratio of
    between-group variance to within-group variance:

        J(w) = (w'S_Bw) / (w'S_Ww)

    where S_B = between-group scatter, S_W = within-group scatter.

    Solution: w = S_W⁻¹(μ₁ - μ₂) for two-group case.

    Used by:
    - Alama Score: Classify borrowers into default/non-default groups
      based on multivariate transaction features
    - Worker Classifier: Discriminate between worker types
      (boda_boda, mama_mboga, vendor, etc.)

    References:
    - Fisher, R.A. (1936). "The use of multiple measurements in taxonomic
      problems." Annals of Eugenics, 7(2), 179-188.
    """

    @staticmethod
    def fit_predict(
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_test: np.ndarray,
    ) -> Dict[str, Any]:
        """
        Fit Fisher's LDA and predict test labels.

        For binary classification (groups 0 and 1):
        1. Compute group means μ₀, μ₁
        2. Compute pooled within-group covariance S_W
        3. Discriminant coefficients: a = S_W⁻¹(μ₁ - μ₀)
        4. Project: d(x) = a'x
        5. Classify: group 1 if d(x) > threshold (midpoint of projected means)

        Args:
            X_train: training features (n × p)
            y_train: training labels (0/1 for binary, or multi-class)
            X_test: test features (m × p)

        Returns:
            Dict with predicted_labels, discriminant_scores, coefficients,
            accuracy, and group statistics
        """
        X_train = np.asarray(X_train, dtype=float)
        y_train = np.asarray(y_train)
        X_test = np.asarray(X_test, dtype=float)

        classes = np.unique(y_train)
        n_classes = len(classes)

        if n_classes < 2:
            return {
                "predicted_labels": np.zeros(len(X_test), dtype=int),
                "discriminant_scores": np.zeros(len(X_test)),
                "error": "Need at least 2 classes",
            }

        # Overall mean
        mu_total = np.mean(X_train, axis=0)
        p = X_train.shape[1]

        # Within-class scatter S_W and between-class scatter S_B
        S_W = np.zeros((p, p))
        S_B = np.zeros((p, p))
        group_stats = {}

        for c in classes:
            mask = y_train == c
            X_c = X_train[mask]
            n_c = len(X_c)
            mu_c = np.mean(X_c, axis=0)
            S_W += (X_c - mu_c).T @ (X_c - mu_c)
            diff = (mu_c - mu_total).reshape(-1, 1)
            S_B += n_c * (diff @ diff.T)
            group_stats[int(c)] = {
                "n": int(n_c),
                "mean": [round(float(v), 4) for v in mu_c],
            }

        # Regularize S_W for invertibility
        S_W += np.eye(p) * 1e-6

        if n_classes == 2:
            # Binary case: single discriminant function
            mu0 = np.mean(X_train[y_train == classes[0]], axis=0)
            mu1 = np.mean(X_train[y_train == classes[1]], axis=0)
            try:
                S_W_inv = np.linalg.inv(S_W)
                a = S_W_inv @ (mu1 - mu0)
            except np.linalg.LinAlgError:
                a = mu1 - mu0

            scores_train = X_train @ a
            scores_test = X_test @ a
            threshold = 0.5 * (mu0 @ a + mu1 @ a)
            predicted = (scores_test > threshold).astype(int)

            # Training accuracy
            train_pred = (scores_train > threshold).astype(int)
            y_binary = (y_train == classes[1]).astype(int)
            accuracy = float(np.mean(train_pred == y_binary))

            return {
                "predicted_labels": predicted,
                "discriminant_scores": scores_test,
                "coefficients": a,
                "threshold": float(threshold),
                "training_accuracy": round(accuracy, 4),
                "group_stats": group_stats,
                "method": "fisher_linear_discriminant",
            }
        else:
            # Multi-class: use eigendecomposition of S_W⁻¹ S_B
            try:
                eigvals, eigvecs = np.linalg.eigh(np.linalg.inv(S_W) @ S_B)
                idx = np.argsort(eigvals)[::-1]
                eigvals = eigvals[idx]
                eigvecs = eigvecs[:, idx]
                # Take top (n_classes - 1) discriminant functions
                n_disc = min(n_classes - 1, p)
                W = eigvecs[:, :n_disc]
            except np.linalg.LinAlgError:
                W = np.eye(p)[:, :min(n_classes - 1, p)]

            # Project training and test data
            proj_train = X_train @ W
            proj_test = X_test @ W

            # Classify by nearest projected class mean
            proj_means = {}
            for c in classes:
                proj_means[int(c)] = np.mean(proj_train[y_train == c], axis=0)

            predicted = np.zeros(len(X_test), dtype=int)
            for i in range(len(X_test)):
                best_c = classes[0]
                best_dist = np.inf
                for c in classes:
                    d = np.linalg.norm(proj_test[i] - proj_means[int(c)])
                    if d < best_dist:
                        best_dist = d
                        best_c = c
                predicted[i] = int(best_c)

            # Training accuracy
            train_pred = np.zeros(len(X_train), dtype=int)
            for i in range(len(X_train)):
                best_c = classes[0]
                best_dist = np.inf
                for c in classes:
                    d = np.linalg.norm(proj_train[i] - proj_means[int(c)])
                    if d < best_dist:
                        best_dist = d
                        best_c = c
                train_pred[i] = int(best_c)
            accuracy = float(np.mean(train_pred == y_train))

            return {
                "predicted_labels": predicted,
                "discriminant_scores": proj_test,
                "discriminant_functions": W,
                "eigenvalues": [round(float(v), 4) for v in eigvals[:n_disc]],
                "training_accuracy": round(accuracy, 4),
                "group_stats": group_stats,
                "method": "fisher_multiclass_lda",
            }


# ---------------------------------------------------------------------------
# MANOVA — Multivariate Analysis of Variance (STA 442)
# ---------------------------------------------------------------------------


class MANOVA:
    """
    Multivariate Analysis of Variance (STA 442 — Applied Multivariate Analysis).

    Tests whether group means differ significantly across multiple
    dependent variables simultaneously.

    H₀: μ₁ = μ₂ = ... = μₖ (all group mean vectors are equal)
    H₁: at least one μᵢ differs

    Test statistics:
    - Wilks' Λ = |W| / |T| (ratio of within to total sum of squares)
    - Pillai's trace = Σ vᵢ/(1+vᵢ)
    - Hotelling-Lawley trace = Σ vᵢ

    where vᵢ are eigenvalues of W⁻¹B.

    Used by:
    - Alama Score: Test whether borrower groups differ significantly
      across multiple financial features
    - Soko Pulse: Test whether market segments differ in price-volume
      profiles
    """

    @staticmethod
    def fit(
        X: np.ndarray,
        groups: np.ndarray,
    ) -> Dict[str, Any]:
        """
        Fit one-way MANOVA.

        Args:
            X: data matrix (n × p) — p dependent variables
            groups: group labels (n,) — k groups

        Returns:
            Dict with Wilks' Lambda, Pillai trace, F-approximation,
            and significance
        """
        X = np.asarray(X, dtype=float)
        groups = np.asarray(groups)
        n, p = X.shape
        classes = np.unique(groups)
        k = len(classes)

        if k < 2:
            return {"error": "Need at least 2 groups"}

        # Grand mean
        mu = np.mean(X, axis=0)

        # Within-groups SSCP matrix W
        W = np.zeros((p, p))
        B = np.zeros((p, p))
        for c in classes:
            mask = groups == c
            X_c = X[mask]
            n_c = len(X_c)
            mu_c = np.mean(X_c, axis=0)
            W += (X_c - mu_c).T @ (X_c - mu_c)
            diff = (mu_c - mu).reshape(-1, 1)
            B += n_c * (diff @ diff.T)

        # Total SSCP
        T_mat = W + B

        # Wilks' Lambda
        try:
            wilks = np.linalg.det(W) / max(np.linalg.det(T_mat), 1e-30)
        except np.linalg.LinAlgError:
            wilks = 1.0

        # Eigenvalues of W⁻¹B
        W_reg = W + np.eye(p) * 1e-10
        try:
            eigvals = np.abs(np.linalg.eigvalsh(np.linalg.inv(W_reg) @ B))
            eigvals = np.sort(eigvals)[::-1]
        except np.linalg.LinAlgError:
            eigvals = np.zeros(p)

        # Pillai's trace
        pillai = float(np.sum(eigvals / (1 + eigvals)))

        # Hotelling-Lawley trace
        hotelling = float(np.sum(eigvals))

        # Roy's largest root
        roy = float(eigvals[0]) if len(eigvals) > 0 else 0.0

        # F-approximation for Wilks' Lambda (Rao's approximation)
        df_hypo = p * (k - 1)
        df_error = n - k
        s_val = min(p, k - 1)
        if wilks > 0 and df_error > 0:
            wilks_f = ((1 - wilks ** (1 / s_val)) / max(wilks ** (1 / s_val), 1e-10)) * (df_error / df_hypo) if df_hypo > 0 else 0
        else:
            wilks_f = 0

        from scipy import stats as sp_stats
        f_pvalue = 1 - sp_stats.f.cdf(max(wilks_f, 0), df_hypo, max(df_error, 1))

        return {
            "wilks_lambda": round(float(wilks), 6),
            "pillai_trace": round(pillai, 6),
            "hotelling_lawley_trace": round(hotelling, 6),
            "roys_largest_root": round(roy, 6),
            "f_approximation": round(float(wilks_f), 4),
            "df_hypothesis": int(df_hypo),
            "df_error": int(df_error),
            "p_value": round(float(f_pvalue), 6),
            "significant_at_05": f_pvalue < 0.05,
            "n_groups": k,
            "n_samples": n,
            "n_variables": p,
            "group_sizes": {int(c): int(np.sum(groups == c)) for c in classes},
            "interpretation": (
                f"{'Reject' if f_pvalue < 0.05 else 'Fail to reject'} null hypothesis "
                f"that all group means are equal (Wilks' Λ={wilks:.4f}, F={wilks_f:.2f}, p={f_pvalue:.4f})"
            ),
        }


# Singleton instances for use across services
bayesian_updater = BayesianUpdater()
kde_estimator = KernelDensityEstimator()
bootstrap = BootstrapInference()
hypothesis_tester = HypothesisTester()
distribution_fitter = DistributionFitter()
mc_engine = MonteCarloEngine()
mcmc_sampler = MCMCSampler()
cluster_analyzer = ClusterAnalyzer()
pca_analyzer = PCAAnalyzer()
factor_analyzer = FactorAnalyzer()
discriminant_analyzer = DiscriminantAnalyzer()
