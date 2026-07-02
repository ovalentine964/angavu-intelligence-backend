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


# Singleton instances for use across services
bayesian_updater = BayesianUpdater()
kde_estimator = KernelDensityEstimator()
bootstrap = BootstrapInference()
hypothesis_tester = HypothesisTester()
distribution_fitter = DistributionFitter()
mc_engine = MonteCarloEngine()
mcmc_sampler = MCMCSampler()
cluster_analyzer = ClusterAnalyzer()
