"""
Multivariate Analysis Methods for Angavu Intelligence Backend (STA 343/346)

Implements multivariate statistical methods for worker profile analysis,
anomaly detection, and credit scoring classification:

1. PCA — Principal Component Analysis (eigendecomposition)
2. DBSCAN — Density-Based Spatial Clustering (anomaly detection)
3. LDA — Linear Discriminant Analysis (classification)
4. QDA — Quadratic Discriminant Analysis (classification)
5. MANOVA — Multivariate Analysis of Variance

Mathematical Justification:
- PCA: X = UΣV' (SVD), reduce p features to k components capturing max variance
- DBSCAN: Core/border/noise points via ε-neighborhood density
- LDA: w = S_W^{-1}(μ₁-μ₂), maximize between/within scatter ratio
- QDA: Quadratic decision boundary, class-specific covariances
- MANOVA: Wilks' Λ = |W|/|T|, multivariate extension of ANOVA

Application to Angavu:
- PCA: reduce 20+ transaction features to 3-5 components for visualization
- DBSCAN: detect anomalous transaction patterns (fraud, errors)
- LDA/QDA: classify creditworthy vs non-creditworthy workers
- MANOVA: compare worker groups across multiple financial metrics simultaneously
"""

import numpy as np
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass


@dataclass
class PCAResult:
    """Result from Principal Component Analysis."""
    n_components: int
    eigenvalues: np.ndarray
    variance_explained: np.ndarray
    cumulative_variance: np.ndarray
    components: np.ndarray  # eigenvectors (p × k)
    projected_data: np.ndarray  # (n × k)
    loadings: np.ndarray  # feature loadings


class PCAAnalysis:
    """Principal Component Analysis via eigendecomposition of covariance matrix.

    STA 346: Reduce dimensionality while preserving maximum variance.
    """

    @staticmethod
    def fit(data: np.ndarray, n_components: Optional[int] = None) -> Dict[str, Any]:
        """Fit PCA to data matrix X (n × p).

        Args:
            data: n × p data matrix
            n_components: number of components to retain (default: min(n, p))

        Returns:
            PCAResult with eigenvalues, components, projected data
        """
        n, p = data.shape
        if n < 3:
            raise ValueError("Need ≥3 observations for PCA")

        k = n_components or min(n, p)
        k = min(k, p)

        # Center the data
        means = data.mean(axis=0)
        centered = data - means

        # Covariance matrix (unbiased: 1/(n-1))
        cov = centered.T @ centered / (n - 1)

        # Eigendecomposition
        eigenvalues, eigenvectors = np.linalg.eigh(cov)

        # Sort by eigenvalue descending
        idx = np.argsort(eigenvalues)[::-1]
        eigenvalues = eigenvalues[idx]
        eigenvectors = eigenvectors[:, idx]

        # Variance explained
        total_var = eigenvalues.sum()
        var_explained = eigenvalues / total_var
        cum_var = np.cumsum(var_explained)

        # Project data
        components = eigenvectors[:, :k]
        projected = centered @ components

        # Loadings (correlation between features and PCs)
        loadings = components * np.sqrt(eigenvalues[:k])

        return {
            "n_components": int(k),
            "eigenvalues": eigenvalues[:k].tolist(),
            "variance_explained": var_explained[:k].tolist(),
            "cumulative_variance": cum_var[:k].tolist(),
            "components": components.tolist(),
            "projected_data": projected.tolist(),
            "loadings": loadings.tolist(),
            "total_variance_explained": float(cum_var[k - 1]),
        }


class DBSCANClusterer:
    """DBSCAN — Density-Based Spatial Clustering for anomaly detection.

    STA 343: Groups points by density, identifies noise (anomalies).
    No assumption on cluster shape or number.

    Algorithm:
        1. For each unvisited point p:
        2.   Find all points within ε (eps) of p → N(p)
        3.   If |N(p)| ≥ minPts → p is core point, start cluster
        4.   Expand cluster by adding density-reachable points
        5.   Points not in any cluster → noise (potential anomalies)
    """

    @staticmethod
    def fit(data: np.ndarray, eps: float = 0.5, min_pts: int = 5) -> Dict[str, Any]:
        """Run DBSCAN clustering.

        Args:
            data: n × p data matrix
            eps: neighborhood radius
            min_pts: minimum points for core point

        Returns:
            Dict with labels, cluster info, noise points
        """
        n = data.shape[0]
        labels = np.full(n, -1, dtype=int)  # -1 = unvisited/noise
        cluster_id = 0

        # Precompute pairwise distances
        dists = np.sqrt(((data[:, np.newaxis] - data[np.newaxis, :]) ** 2).sum(axis=2))

        for i in range(n):
            if labels[i] != -1:
                continue  # already assigned

            # Find neighbors
            neighbors = np.where(dists[i] <= eps)[0]

            if len(neighbors) < min_pts:
                labels[i] = -1  # noise
                continue

            # Start new cluster
            labels[i] = cluster_id

            # Expand cluster
            seed_set = list(neighbors)
            j = 0
            while j < len(seed_set):
                q = seed_set[j]
                if labels[q] == -1:
                    labels[q] = cluster_id  # border point
                elif labels[q] == -1 or labels[q] == -2:
                    labels[q] = cluster_id
                    q_neighbors = np.where(dists[q] <= eps)[0]
                    if len(q_neighbors) >= min_pts:
                        seed_set.extend(q_neighbors.tolist())
                j += 1

            cluster_id += 1

        # Compute cluster statistics
        noise_mask = labels == -1
        cluster_sizes = {}
        cluster_centers = {}
        for c in range(cluster_id):
            mask = labels == c
            cluster_sizes[c] = int(mask.sum())
            cluster_centers[c] = data[mask].mean(axis=0).tolist()

        return {
            "labels": labels.tolist(),
            "n_clusters": cluster_id,
            "cluster_sizes": cluster_sizes,
            "cluster_centers": cluster_centers,
            "noise_points": int(noise_mask.sum()),
            "noise_indices": np.where(noise_mask)[0].tolist(),
            "anomaly_fraction": float(noise_mask.sum() / n),
        }


class LDAClassifier:
    """Linear Discriminant Analysis — Fisher's LDA for classification.

    STA 346: Assumes equal covariance matrices across classes.
    Decision boundary is linear.

    Mathematical basis:
        w = S_W^{-1}(μ₁ - μ₂)
        δ_k(x) = x'Σ^{-1}μ_k - ½μ_k'Σ^{-1}μ_k + ln(π_k)
    """

    @staticmethod
    def fit(X: np.ndarray, y: np.ndarray) -> Dict[str, Any]:
        """Fit LDA model.

        Args:
            X: n × p feature matrix
            y: n-length class labels (0, 1, ..., K-1)

        Returns:
            Dict with model parameters and training accuracy
        """
        classes = np.unique(y)
        n, p = X.shape
        k = len(classes)

        # Class priors, means
        priors = {}
        means = {}
        for c in classes:
            mask = y == c
            priors[int(c)] = mask.sum() / n
            means[int(c)] = X[mask].mean(axis=0)

        # Pooled within-class covariance
        S_W = np.zeros((p, p))
        for c in classes:
            mask = y == c
            X_c = X[mask] - means[int(c)]
            S_W += X_c.T @ X_c
        S_W /= (n - k)

        # Inverse of pooled covariance
        try:
            S_W_inv = np.linalg.inv(S_W)
        except np.linalg.LinAlgError:
            S_W_inv = np.linalg.pinv(S_W)

        # Discriminant functions: δ_k(x) = x'Σ^{-1}μ_k - ½μ_k'Σ^{-1}μ_k + ln(π_k)
        coeffs = {}
        intercepts = {}
        for c in classes:
            mu = means[int(c)]
            coeffs[int(c)] = S_W_inv @ mu
            intercepts[int(c)] = -0.5 * mu @ S_W_inv @ mu + np.log(priors[int(c)])

        # Predict training data
        scores = np.zeros((n, k))
        for idx, c in enumerate(classes):
            scores[:, idx] = X @ coeffs[int(c)] + intercepts[int(c)]
        predictions = classes[scores.argmax(axis=1)]
        accuracy = (predictions == y).mean()

        # Fisher's discriminant direction (for 2 classes)
        fisher_w = None
        if k == 2:
            diff = means[int(classes[1])] - means[int(classes[0])]
            fisher_w = S_W_inv @ diff
            fisher_w = fisher_w / np.linalg.norm(fisher_w)

        return {
            "classes": classes.tolist(),
            "priors": priors,
            "means": {int(c): m.tolist() for c, m in means.items()},
            "coefficients": {int(c): v.tolist() for c, v in coeffs.items()},
            "intercepts": intercepts,
            "pooled_covariance": S_W.tolist(),
            "training_accuracy": float(accuracy),
            "fisher_direction": fisher_w.tolist() if fisher_w is not None else None,
        }

    @staticmethod
    def predict(X: np.ndarray, model: Dict[str, Any]) -> Dict[str, Any]:
        """Predict classes using fitted LDA model."""
        classes = model["classes"]
        n = X.shape[0]
        scores = np.zeros((n, len(classes)))
        for idx, c in enumerate(classes):
            coeffs = np.array(model["coefficients"][str(c)])
            scores[:, idx] = X @ coeffs + model["intercepts"][str(c)]
        predictions = [classes[s] for s in scores.argmax(axis=1)]
        return {"predictions": predictions, "scores": scores.tolist()}


class QDAClassifier:
    """Quadratic Discriminant Analysis — class-specific covariances.

    STA 346: Like LDA but allows different covariance per class.
    Decision boundary is quadratic.

    δ_k(x) = -½log|Σ_k| - ½(x-μ_k)'Σ_k^{-1}(x-μ_k) + ln(π_k)
    """

    @staticmethod
    def fit(X: np.ndarray, y: np.ndarray) -> Dict[str, Any]:
        """Fit QDA model.

        Args:
            X: n × p feature matrix
            y: n-length class labels

        Returns:
            Dict with model parameters
        """
        classes = np.unique(y)
        n, p = X.shape

        priors = {}
        means = {}
        covs = {}
        cov_invs = {}
        cov_log_dets = {}

        for c in classes:
            mask = y == c
            n_c = mask.sum()
            priors[int(c)] = n_c / n
            X_c = X[mask]
            means[int(c)] = X_c.mean(axis=0)
            cov = np.cov(X_c, rowvar=False, bias=False)
            if cov.ndim == 0:
                cov = np.array([[cov]])
            # Regularize for stability
            cov += np.eye(p) * 1e-6
            covs[int(c)] = cov
            cov_invs[int(c)] = np.linalg.inv(cov)
            sign, logdet = np.linalg.slogdet(cov)
            cov_log_dets[int(c)] = logdet

        # Training accuracy
        scores = np.zeros((n, len(classes)))
        for idx, c in enumerate(classes):
            mu = means[int(c)]
            diff = X - mu
            inv = cov_invs[int(c)]
            logdet = cov_log_dets[int(c)]
            mahal = np.sum(diff @ inv * diff, axis=1)
            scores[:, idx] = -0.5 * logdet - 0.5 * mahal + np.log(priors[int(c)])

        predictions = [classes[s] for s in scores.argmax(axis=1)]
        accuracy = (np.array(predictions) == y).mean()

        return {
            "classes": classes.tolist(),
            "priors": priors,
            "means": {int(c): m.tolist() for c, m in means.items()},
            "covariances": {int(c): cov.tolist() for c, cov in covs.items()},
            "training_accuracy": float(accuracy),
        }


class MANOVATest:
    """MANOVA — Multivariate Analysis of Variance.

    STA 343: Test whether group means differ across multiple dependent variables.
    Extension of ANOVA to multivariate response.

    Wilks' Λ = |W| / |T| where W = within-group SSCP, T = total SSCP
    Approximate F-test via Rao's approximation.
    """

    @staticmethod
    def test(groups: List[np.ndarray]) -> Dict[str, Any]:
        """Run one-way MANOVA.

        Args:
            groups: list of arrays, each (n_i × p) for group i

        Returns:
            Dict with Wilks' lambda, F-statistic, p-value
        """
        k = len(groups)
        if k < 2:
            raise ValueError("Need ≥2 groups")

        p = groups[0].shape[1]
        if any(g.shape[1] != p for g in groups):
            raise ValueError("All groups must have same number of variables")

        ns = [g.shape[0] for g in groups]
        N = sum(ns)

        # Grand mean
        all_data = np.vstack(groups)
        grand_mean = all_data.mean(axis=0)

        # Between-group SSCP (H)
        H = np.zeros((p, p))
        for i, g in enumerate(groups):
            mean_i = g.mean(axis=0)
            diff = mean_i - grand_mean
            H += ns[i] * np.outer(diff, diff)

        # Within-group SSCP (W)
        W = np.zeros((p, p))
        for i, g in enumerate(groups):
            centered = g - g.mean(axis=0)
            W += centered.T @ centered

        # Total SSCP (T = H + W)
        T = H + W

        # Wilks' Lambda
        try:
            wilks = np.linalg.det(W) / np.linalg.det(T)
        except np.linalg.LinAlgError:
            wilks = np.nan

        # Approximate F-test (Rao's approximation)
        s = min(k - 1, p)
        m_val = (abs(k - 1 - p) - 1) / 2
        n_val = (N - k - p - 1) / 2

        if wilks > 0 and wilks < 1:
            # Pillai's trace as alternative
            V = np.trace(H @ np.linalg.pinv(T))

            # Lawley-Hotelling trace
            try:
                U = np.trace(H @ np.linalg.pinv(W))
            except:
                U = 0.0

            # Approximate F for Wilks' Lambda
            df1 = s * (2 * m_val + s + 1) if s * (2 * m_val + s + 1) > 0 else p
            df2 = s * (2 * n_val + s + 1) if s * (2 * n_val + s + 1) > 0 else N - k

            if wilks > 0:
                f_stat = ((1 - wilks) / wilks) * (df2 / df1) if df1 > 0 and df2 > 0 else 0
            else:
                f_stat = float('inf')

            # Rough p-value (F-distribution approximation)
            from scipy import stats as scipy_stats
            p_value = 1 - scipy_stats.f.cdf(max(0, f_stat), df1, df2) if df1 > 0 and df2 > 0 else 1.0
        else:
            V = 0.0; U = 0.0; f_stat = 0.0; p_value = 1.0; df1 = 0; df2 = 0

        return {
            "test_name": "MANOVA (Wilks' Lambda)",
            "wilks_lambda": float(wilks),
            "pillai_trace": float(V),
            "lawley_hotelling_trace": float(U),
            "f_statistic": float(f_stat),
            "df1": int(df1),
            "df2": int(df2),
            "p_value": float(p_value),
            "significant_at_05": p_value < 0.05,
            "n_groups": k,
            "n_variables": p,
            "total_n": N,
            "group_means": [g.mean(axis=0).tolist() for g in groups],
        }
