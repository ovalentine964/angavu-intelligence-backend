"""
Clustering Methods — K-means with k-means++ initialization (STA 442).

Classes:
- ClusterAnalyzer: K-means, silhouette score, elbow method, market segmentation

Decomposed from statistical_foundation.py for maintainability.
"""

from typing import Any, Dict, List, Optional

import numpy as np


class ClusterAnalyzer:
    """
    Cluster Analysis (STA 442 — Applied Multivariate Analysis).

    K-means clustering with k-means++ initialization,
    silhouette score evaluation, and elbow method for optimal k.
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
        data: np.ndarray,
        k: int,
        max_iter: int = 300,
        tol: float = 1e-6,
        n_init: int = 10,
        seed: int = 42,
    ) -> Dict[str, Any]:
        """
        K-means clustering (Lloyd's algorithm with k-means++ init).

        Args:
            data: (n, d) data matrix
            k: Number of clusters
            max_iter: Maximum iterations per run
            tol: Convergence tolerance
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

        best_result: Optional[Dict[str, Any]] = None
        best_inertia: float = np.inf
        rng = np.random.RandomState(seed)

        for _ in range(n_init):
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

                shift: float = float(np.linalg.norm(new_centroids - centroids))
                centroids = new_centroids
                labels = new_labels

                if shift < tol:
                    converged = True
                    break

            inertia: float = 0.0
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

        s(i) = (b(i) - a(i)) / max(a(i), b(i)) ∈ [-1, 1]
        """
        data = np.asarray(data, dtype=float)
        labels = np.asarray(labels)
        n: int = len(data)
        k: int = len(set(labels))

        if k < 2:
            return {
                "overall_score": 0.0,
                "cluster_scores": {},
                "n_clusters": k,
                "message": "Silhouette requires at least 2 clusters",
            }

        dist_matrix = np.linalg.norm(
            data[:, np.newaxis] - data[np.newaxis, :], axis=2
        )

        sample_scores = np.zeros(n)
        cluster_scores: Dict[int, float] = {}

        for i in range(n):
            own_cluster = labels[i]
            mask_own = labels == own_cluster
            mask_own[i] = False
            n_own: int = int(np.sum(mask_own))

            a_i: float = float(np.mean(dist_matrix[i, mask_own])) if n_own > 0 else 0.0

            b_i: float = np.inf
            for j in range(k):
                if j == own_cluster:
                    continue
                mask_other = labels == j
                if np.sum(mask_other) > 0:
                    mean_dist: float = float(np.mean(dist_matrix[i, mask_other]))
                    b_i = min(b_i, mean_dist)

            if b_i == np.inf:
                b_i = 0.0

            denom: float = max(a_i, b_i)
            sample_scores[i] = (b_i - a_i) / denom if denom > 0 else 0.0

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
        """Elbow method for selecting optimal number of clusters."""
        data = np.asarray(data, dtype=float)
        n: int = data.shape[0]

        if k_range is None:
            max_k_eff: int = min(max_k, n - 1)
            k_range = list(range(2, max_k_eff + 1))

        results: List[Dict[str, Any]] = []
        for k in k_range:
            result = ClusterAnalyzer.kmeans(data, k=k, n_init=n_init, seed=seed)
            sil = ClusterAnalyzer.silhouette_score(data, result["labels"])
            results.append({
                "k": k,
                "inertia": result["inertia"],
                "silhouette": sil["overall_score"],
                "cluster_sizes": result["cluster_sizes"],
            })

        for i in range(len(results)):
            if i == 0:
                results[i]["delta"] = None
                results[i]["acceleration"] = None
            else:
                delta: float = results[i - 1]["inertia"] - results[i]["inertia"]
                results[i]["delta"] = round(delta, 4)
                if i >= 2:
                    accel: float = results[i - 1]["delta"] - delta
                    results[i]["acceleration"] = round(accel, 4)
                else:
                    results[i]["acceleration"] = None

        accels = [
            (r["k"], r["acceleration"])
            for r in results
            if r["acceleration"] is not None
        ]
        recommended_k: int = max(accels, key=lambda x: x[1])[0] if accels else max(results, key=lambda x: x["silhouette"])["k"]

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
        """Market segmentation using K-means clustering."""
        data = np.asarray(data, dtype=float)
        n, d = data.shape

        if feature_names is None:
            feature_names = [f"feature_{i}" for i in range(d)]

        elbow = ClusterAnalyzer.elbow_method(data, max_k=max_k, seed=seed)
        optimal_k: int = elbow["recommended_k"]

        result = ClusterAnalyzer.kmeans(data, k=optimal_k, seed=seed)
        sil = ClusterAnalyzer.silhouette_score(data, result["labels"])

        segments: List[Dict[str, Any]] = []
        for j in range(optimal_k):
            mask = result["labels"] == j
            members = data[mask]
            profile: Dict[str, Dict[str, float]] = {}
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


__all__ = ["ClusterAnalyzer"]
