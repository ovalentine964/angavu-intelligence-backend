"""
Multivariate Analysis Module — STA 442 Applied Multivariate Analysis.

Extracted from statistical_foundation.py for modularity.

Provides multivariate statistical methods for dimensionality reduction,
latent factor extraction, and group comparison.

Classes:
- PCAAnalyzer: Principal Component Analysis
- FactorAnalyzer: Exploratory Factor Analysis with varimax rotation
- DiscriminantAnalyzer: Fisher's Linear Discriminant Analysis
- MANOVA: Multivariate Analysis of Variance

Academic Foundation:
- STA 442: Applied Multivariate Analysis → PCA, factor analysis,
  discriminant analysis, MANOVA, cluster analysis
- STA 341: Theory of Estimation → MLE for factor models

Usage:
    from app.services.multivariate_analysis import PCAAnalyzer, FactorAnalyzer
"""

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import structlog
from scipy import stats

logger = structlog.get_logger(__name__)


class PCAAnalyzer:
    """
    Principal Component Analysis (STA 442 — Applied Multivariate Analysis).

    Reduces dimensionality by finding orthogonal directions of maximum
    variance. Eigenvalue decomposition of the covariance matrix.

    Used by Alama Score for feature reduction of borrower characteristics.
    """

    @staticmethod
    def fit_transform(
        X: np.ndarray,
        n_components: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Fit PCA and transform data."""
        X = np.asarray(X, dtype=float)
        n, p = X.shape

        # Center data
        mean = np.mean(X, axis=0)
        X_centered = X - mean

        # Covariance matrix
        cov = X_centered.T @ X_centered / (n - 1)

        # Eigendecomposition
        eigenvalues, eigenvectors = np.linalg.eigh(cov)
        # Sort descending
        idx = np.argsort(eigenvalues)[::-1]
        eigenvalues = eigenvalues[idx]
        eigenvectors = eigenvectors[:, idx]

        if n_components is None:
            n_components = min(p, n)

        loadings = eigenvectors[:, :n_components]
        transformed = X_centered @ loadings

        total_var = np.sum(eigenvalues)
        var_explained = eigenvalues[:n_components] / total_var
        cum_var = np.cumsum(var_explained)

        return {
            "transformed": transformed,
            "eigenvalues": eigenvalues[:n_components],
            "loadings": loadings,
            "variance_explained": var_explained,
            "cumulative_variance": cum_var,
            "total_variance": total_var,
            "mean": mean,
            "n_components": n_components,
        }

    @staticmethod
    def select_n_components(
        X: np.ndarray,
        variance_threshold: float = 0.95,
    ) -> Dict[str, Any]:
        """Select number of components to explain threshold variance."""
        result = PCAAnalyzer.fit_transform(X)
        cum_var = result["cumulative_variance"]
        n_components = int(np.searchsorted(cum_var, variance_threshold) + 1)
        n_components = min(n_components, len(cum_var))

        return {
            "n_components": n_components,
            "variance_explained": round(float(cum_var[n_components - 1]), 4),
            "threshold": variance_threshold,
            "eigenvalues": result["eigenvalues"].tolist(),
        }

    @staticmethod
    def interpret_loadings(
        loadings: np.ndarray,
        feature_names: List[str],
        n_components: int = 3,
        threshold: float = 0.3,
    ) -> List[Dict[str, Any]]:
        """Interpret PCA loadings for each component."""
        interpretations = []
        for j in range(min(n_components, loadings.shape[1])):
            component_loadings = loadings[:, j]
            significant = []
            for i, name in enumerate(feature_names):
                if i < len(component_loadings) and abs(component_loadings[i]) >= threshold:
                    significant.append({
                        "feature": name,
                        "loading": round(float(component_loadings[i]), 3),
                        "direction": "positive" if component_loadings[i] > 0 else "negative",
                    })
            significant.sort(key=lambda x: abs(x["loading"]), reverse=True)
            interpretations.append({
                "component": j,
                "top_features": significant[:5],
                "interpretation": f"Component {j} primarily represents "
                    + ", ".join(s["feature"] for s in significant[:3]),
            })
        return interpretations


class FactorAnalyzer:
    """
    Exploratory Factor Analysis (STA 442 — Applied Multivariate Analysis).

    Identifies latent factors that explain correlations among observed
    variables. Uses principal axis factoring with varimax rotation.
    """

    @staticmethod
    def fit(
        X: np.ndarray,
        n_factors: int = 3,
        max_iter: int = 100,
    ) -> Dict[str, Any]:
        """Fit factor analysis model."""
        X = np.asarray(X, dtype=float)
        n, p = X.shape

        # Correlation matrix
        std = np.std(X, axis=0, ddof=1)
        std[std == 0] = 1.0
        X_std = (X - np.mean(X, axis=0)) / std
        R = X_std.T @ X_std / (n - 1)

        # Initial communalities (squared multiple correlations)
        R_inv = np.linalg.pinv(R)
        communalities = 1 - 1.0 / np.diag(R_inv)
        communalities = np.clip(communalities, 0.01, 0.99)

        # Iterative principal axis factoring
        for _ in range(max_iter):
            R_adj = R.copy()
            np.fill_diagonal(R_adj, communalities)
            eigenvalues, eigenvectors = np.linalg.eigh(R_adj)
            idx = np.argsort(eigenvalues)[::-1]
            eigenvalues = eigenvalues[idx][:n_factors]
            eigenvectors = eigenvectors[:, idx][:, :n_factors]

            loadings = eigenvectors @ np.diag(np.sqrt(np.maximum(eigenvalues, 0)))
            new_communalities = np.sum(loadings ** 2, axis=1)

            if np.allclose(communalities, new_communalities, atol=1e-6):
                break
            communalities = new_communalities

        # Varimax rotation
        loadings = FactorAnalyzer._varimax(loadings)
        var_explained = np.sum(loadings ** 2, axis=0)
        total_var = p
        var_pct = var_explained / total_var * 100

        return {
            "loadings": loadings,
            "communalities": communalities,
            "variance_explained_pct": var_pct,
            "n_factors": n_factors,
            "n_variables": p,
        }

    @staticmethod
    def _varimax(loadings: np.ndarray, max_iter: int = 100, tol: float = 1e-6) -> np.ndarray:
        """Varimax rotation for factor loadings."""
        p, k = loadings.shape
        rotation = np.eye(k)

        for _ in range(max_iter):
            rotated = loadings @ rotation
            d = rotated ** 2
            u = d - np.mean(d, axis=0)
            u = u.T @ rotated

            # SVD for rotation
            try:
                U, S, Vt = np.linalg.svd(u)
                rotation = U @ Vt
            except np.linalg.LinAlgError:
                break

        return loadings @ rotation

    @staticmethod
    def interpret_factors(
        loadings: np.ndarray,
        feature_names: List[str],
        threshold: float = 0.3,
    ) -> List[Dict[str, Any]]:
        """Interpret factor loadings."""
        n_factors = loadings.shape[1]
        interpretations = []
        for j in range(n_factors):
            significant = []
            for i, name in enumerate(feature_names):
                if i < loadings.shape[0] and abs(loadings[i, j]) >= threshold:
                    significant.append({
                        "feature": name,
                        "loading": round(float(loadings[i, j]), 3),
                    })
            significant.sort(key=lambda x: abs(x["loading"]), reverse=True)
            interpretations.append({
                "factor": j,
                "top_features": significant[:5],
            })
        return interpretations


class DiscriminantAnalyzer:
    """
    Fisher's Linear Discriminant Analysis (STA 442).

    Finds linear combinations that best separate classes.
    Maximizes ratio of between-class to within-class variance.
    """

    @staticmethod
    def fit_predict(
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_test: np.ndarray,
    ) -> Dict[str, Any]:
        """Fit LDA and predict test samples."""
        X_train = np.asarray(X_train, dtype=float)
        y_train = np.asarray(y_train)
        X_test = np.asarray(X_test, dtype=float)

        classes = np.unique(y_train)
        k = len(classes)
        n, p = X_train.shape

        if k < 2:
            return {"error": "Need at least 2 classes"}

        # Class means
        means = {}
        for c in classes:
            means[c] = np.mean(X_train[y_train == c], axis=0)

        # Within-class scatter
        S_W = np.zeros((p, p))
        for c in classes:
            X_c = X_train[y_train == c]
            diff = X_c - means[c]
            S_W += diff.T @ diff

        # Between-class scatter
        grand_mean = np.mean(X_train, axis=0)
        S_B = np.zeros((p, p))
        for c in classes:
            n_c = np.sum(y_train == c)
            diff = (means[c] - grand_mean).reshape(-1, 1)
            S_B += n_c * (diff @ diff.T)

        # Solve generalized eigenvalue problem
        S_W_reg = S_W + np.eye(p) * 1e-8
        try:
            eigvals, eigvecs = np.linalg.eigh(np.linalg.inv(S_W_reg) @ S_B)
            idx = np.argsort(eigvals)[::-1]
            eigvals = eigvals[idx]
            eigvecs = eigvecs[:, idx]
        except np.linalg.LinAlgError:
            return {"error": "Singular within-class scatter matrix"}

        n_components = min(k - 1, p)
        W = eigvecs[:, :n_components]

        # Project training data
        X_train_proj = X_train @ W
        X_test_proj = X_test @ W

        # Classify by nearest projected class mean
        predicted = []
        for x in X_test_proj:
            min_dist = np.inf
            best_class = classes[0]
            for c in classes:
                dist = np.linalg.norm(x - means[c] @ W)
                if dist < min_dist:
                    min_dist = dist
                    best_class = c
            predicted.append(best_class)

        # Training accuracy
        train_pred = []
        for x in X_train_proj:
            min_dist = np.inf
            best_class = classes[0]
            for c in classes:
                dist = np.linalg.norm(x - means[c] @ W)
                if dist < min_dist:
                    min_dist = dist
                    best_class = c
            train_pred.append(best_class)

        train_accuracy = float(np.mean(np.array(train_pred) == y_train))

        return {
            "predicted_labels": np.array(predicted),
            "discriminant_scores": X_test_proj[:, 0] if n_components > 0 else np.zeros(len(X_test)),
            "training_accuracy": round(train_accuracy, 4),
            "eigenvalues": eigvals[:n_components].tolist(),
            "n_components": n_components,
            "method": "fisher_linear_discriminant",
        }


class MANOVA:
    """
    Multivariate Analysis of Variance (STA 442).

    Tests whether group means differ significantly across multiple
    dependent variables simultaneously.

    H₀: μ₁ = μ₂ = ... = μₖ (all group mean vectors are equal)
    """

    @staticmethod
    def fit(X: np.ndarray, groups: np.ndarray) -> Dict[str, Any]:
        """Fit one-way MANOVA."""
        X = np.asarray(X, dtype=float)
        groups = np.asarray(groups)
        n, p = X.shape
        classes = np.unique(groups)
        k = len(classes)

        if k < 2:
            return {"error": "Need at least 2 groups"}

        mu = np.mean(X, axis=0)
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

        T_mat = W + B
        try:
            wilks = np.linalg.det(W) / max(np.linalg.det(T_mat), 1e-30)
        except np.linalg.LinAlgError:
            wilks = 1.0

        W_reg = W + np.eye(p) * 1e-10
        try:
            eigvals = np.abs(np.linalg.eigvalsh(np.linalg.inv(W_reg) @ B))
            eigvals = np.sort(eigvals)[::-1]
        except np.linalg.LinAlgError:
            eigvals = np.zeros(p)

        pillai = float(np.sum(eigvals / (1 + eigvals)))
        hotelling = float(np.sum(eigvals))
        roy = float(eigvals[0]) if len(eigvals) > 0 else 0.0

        df_hypo = p * (k - 1)
        df_error = n - k
        s_val = min(p, k - 1)
        if wilks > 0 and df_error > 0:
            wilks_f = ((1 - wilks ** (1 / s_val)) / max(wilks ** (1 / s_val), 1e-10)) * (df_error / df_hypo) if df_hypo > 0 else 0
        else:
            wilks_f = 0

        f_pvalue = 1 - stats.f.cdf(max(wilks_f, 0), df_hypo, max(df_error, 1))

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
