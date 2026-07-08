"""
Descriptive Statistics Module — STA 444 Non-Parametric Methods.

Extracted from statistical_foundation.py for modularity.

Provides non-parametric statistical methods that work without
distributional assumptions — essential for informal economy data
which is non-normal, small-sample, and outlier-heavy.

Classes:
- KernelDensityEstimator: Non-parametric density estimation
- BootstrapInference: Distribution-free confidence intervals
- ClusterAnalyzer: K-means clustering for market segmentation
- DistributionFitter: Parametric distribution fitting with GoF tests
- HypothesisTester: Statistical hypothesis testing framework

Academic Foundation:
- STA 444: Non-Parametric Methods → KDE, bootstrap, rank tests
- STA 342: Test of Hypothesis → t-test, chi-square, Mann-Whitney
- STA 241: Probability → Distribution models, goodness-of-fit
- STA 442: Multivariate Analysis → K-means clustering
"""

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import structlog
from scipy import stats
from scipy.stats import norm

logger = structlog.get_logger(__name__)


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
        """Gaussian kernel density estimation."""
        n = len(data)
        if n < 2:
            raise ValueError("Need at least 2 data points for KDE")

        if bandwidth is None:
            sigma = np.std(data, ddof=1)
            iqr = np.percentile(data, 75) - np.percentile(data, 25)
            sigma_robust = min(sigma, iqr / 1.34)
            bandwidth = 0.9 * sigma_robust * n ** (-1 / 5)
            bandwidth = max(bandwidth, 1e-6)

        if points is None:
            data_min, data_max = data.min(), data.max()
            margin = 3 * bandwidth
            points = np.linspace(data_min - margin, data_max + margin, 100)

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
        """Test for multimodality in data distribution."""
        points, density = KernelDensityEstimator.gaussian_kde(data)

        peaks = []
        for i in range(1, len(density) - 1):
            if density[i] > density[i - 1] and density[i] > density[i + 1]:
                peaks.append((points[i], density[i]))

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
    The bootstrap principle: F̂ approximates F. Resampling from F̂
    mimics sampling from F.
    """

    @staticmethod
    def percentile_ci(
        data: np.ndarray,
        statistic_func: callable,
        n_bootstrap: int = 10000,
        confidence: float = 0.95,
        seed: int = 42,
    ) -> Dict[str, float]:
        """Bootstrap percentile confidence interval."""
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
        """Bootstrap standard error estimation."""
        rng = np.random.RandomState(seed)
        n = len(data)
        stats_arr = np.zeros(n_bootstrap)
        for i in range(n_bootstrap):
            sample = rng.choice(data, size=n, replace=True)
            stats_arr[i] = statistic_func(sample)
        return float(np.std(stats_arr))


class HypothesisTester:
    """
    Hypothesis testing framework (STA 342 — Test of Hypothesis).

    Implements statistical tests for validating all platform claims.
    """

    @staticmethod
    def two_sample_test(
        sample1: np.ndarray,
        sample2: np.ndarray,
        test_type: str = "auto",
        alternative: str = "two-sided",
    ) -> Dict[str, Any]:
        """Two-sample hypothesis test with auto-selection."""
        n1, n2 = len(sample1), len(sample2)

        if test_type == "auto":
            if n1 < 5000 and n2 < 5000:
                _, p_norm1 = stats.shapiro(sample1[:min(n1, 5000)])
                _, p_norm2 = stats.shapiro(sample2[:min(n2, 5000)])
                if p_norm1 > 0.05 and p_norm2 > 0.05:
                    test_type = "ttest"
                else:
                    test_type = "mannwhitney"
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
        """Fit multiple distributions and select the best by AIC."""
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


class ClusterAnalyzer:
    """
    Cluster Analysis (STA 442 — Multivariate Analysis).

    K-means clustering with k-means++ initialization, silhouette
    evaluation, and elbow method for optimal k.
    """

    @staticmethod
    def _kmeans_plus_plus_init(
        data: np.ndarray, k: int, rng: np.random.RandomState,
    ) -> np.ndarray:
        """k-means++ initialization (Arthur & Vassilvitskii, 2007)."""
        n, d = data.shape
        centroids = np.empty((k, d), dtype=data.dtype)
        idx = rng.randint(n)
        centroids[0] = data[idx]

        for i in range(1, k):
            dists = np.min(
                np.linalg.norm(data[:, np.newaxis] - centroids[:i], axis=2) ** 2,
                axis=1,
            )
            probs = dists / dists.sum()
            cumprobs = np.cumsum(probs)
            r = rng.random()
            idx = int(np.searchsorted(cumprobs, r))
            idx = min(idx, n - 1)
            centroids[i] = data[idx]

        return centroids

    @staticmethod
    def kmeans(
        data: np.ndarray, k: int, max_iter: int = 300, tol: float = 1e-6,
        n_init: int = 10, seed: int = 42,
    ) -> Dict[str, Any]:
        """K-means clustering (Lloyd's algorithm with k-means++ init)."""
        data = np.asarray(data, dtype=float)
        n, d = data.shape
        best_result = None
        best_inertia = np.inf
        rng = np.random.RandomState(seed)

        for run in range(n_init):
            centroids = ClusterAnalyzer._kmeans_plus_plus_init(data, k, rng)
            labels = np.zeros(n, dtype=int)
            converged = False

            for iteration in range(max_iter):
                dists = np.linalg.norm(
                    data[:, np.newaxis] - centroids[np.newaxis, :], axis=2
                )
                new_labels = np.argmin(dists, axis=1)
                new_centroids = np.empty_like(centroids)
                for j in range(k):
                    members = data[new_labels == j]
                    if len(members) > 0:
                        new_centroids[j] = members.mean(axis=0)
                    else:
                        new_centroids[j] = data[rng.randint(n)]

                shift = float(np.linalg.norm(new_centroids - centroids))
                centroids = new_centroids
                labels = new_labels
                if shift < tol:
                    converged = True
                    break

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
                    "k": k, "n": n, "n_init": n_init,
                }

        labels = best_result["labels"]
        best_result["cluster_sizes"] = {
            int(j): int(np.sum(labels == j)) for j in range(k)
        }
        return best_result

    @staticmethod
    def silhouette_score(data: np.ndarray, labels: np.ndarray) -> Dict[str, Any]:
        """Silhouette score for cluster quality evaluation."""
        data = np.asarray(data, dtype=float)
        labels = np.asarray(labels)
        n = len(data)
        k = len(set(labels))

        if k < 2:
            return {"overall_score": 0.0, "cluster_scores": {}, "n_clusters": k,
                    "message": "Silhouette requires at least 2 clusters"}

        dist_matrix = np.linalg.norm(
            data[:, np.newaxis] - data[np.newaxis, :], axis=2
        )
        sample_scores = np.zeros(n)
        cluster_scores = {}

        for i in range(n):
            own_cluster = labels[i]
            mask_own = labels == own_cluster
            mask_own[i] = False
            n_own = np.sum(mask_own)
            a_i = float(np.mean(dist_matrix[i, mask_own])) if n_own > 0 else 0.0
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

        for j in range(k):
            mask = labels == j
            if np.sum(mask) > 0:
                cluster_scores[int(j)] = round(float(np.mean(sample_scores[mask])), 4)

        return {
            "overall_score": round(float(np.mean(sample_scores)), 4),
            "cluster_scores": cluster_scores,
            "n_clusters": k, "n_samples": n,
            "per_sample_scores": sample_scores,
        }

    @staticmethod
    def elbow_method(
        data: np.ndarray, k_range: Optional[List[int]] = None,
        max_k: int = 10, n_init: int = 10, seed: int = 42,
    ) -> Dict[str, Any]:
        """Elbow method for selecting optimal number of clusters."""
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
                "k": k, "inertia": result["inertia"],
                "silhouette": sil["overall_score"],
                "cluster_sizes": result["cluster_sizes"],
            })

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

        accels = [(r["k"], r["acceleration"]) for r in results if r["acceleration"] is not None]
        if accels:
            recommended_k = max(accels, key=lambda x: x[1])[0]
        else:
            recommended_k = max(results, key=lambda x: x["silhouette"])["k"]

        return {
            "results": results, "recommended_k": recommended_k,
            "method": "elbow + silhouette fallback", "n_samples": n,
            "k_range_tested": [r["k"] for r in results],
        }

    @staticmethod
    def segment_market(
        data: np.ndarray, feature_names: Optional[List[str]] = None,
        max_k: int = 8, seed: int = 42,
    ) -> Dict[str, Any]:
        """Market segmentation using K-means clustering."""
        data = np.asarray(data, dtype=float)
        n, d = data.shape
        if feature_names is None:
            feature_names = [f"feature_{i}" for i in range(d)]

        elbow = ClusterAnalyzer.elbow_method(data, max_k=max_k, seed=seed)
        optimal_k = elbow["recommended_k"]
        result = ClusterAnalyzer.kmeans(data, k=optimal_k, seed=seed)
        sil = ClusterAnalyzer.silhouette_score(data, result["labels"])

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
                "segment_id": j, "size": int(np.sum(mask)),
                "proportion": round(float(np.mean(mask)), 4),
                "centroid": [round(float(c), 4) for c in result["centroids"][j]],
                "profile": profile,
            })

        return {
            "optimal_k": optimal_k, "silhouette_score": sil["overall_score"],
            "inertia": result["inertia"], "converged": result["converged"],
            "segments": segments, "elbow_analysis": elbow,
            "labels": result["labels"].tolist(),
        }
