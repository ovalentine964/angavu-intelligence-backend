"""
Multivariate Analysis — PCA, Factor Analysis, Discriminant Analysis, MANOVA (STA 442).

Classes:
- PCAAnalyzer: Principal Component Analysis
- FactorAnalyzer: Exploratory Factor Analysis with varimax rotation
- DiscriminantAnalyzer: Fisher's Linear Discriminant Analysis
- MANOVA: Multivariate Analysis of Variance

Decomposed from statistical_foundation.py for maintainability.
"""

from typing import Any

import numpy as np
from scipy import stats


class PCAAnalyzer:
    """
    Principal Component Analysis (STA 442).

    Reduces dimensionality by projecting onto directions of maximum
    variance via eigendecomposition of the covariance matrix.
    """

    @staticmethod
    def fit_transform(
        X: np.ndarray,
        n_components: int = 3,
        standardize: bool = False,
    ) -> dict[str, Any]:
        """
        Fit PCA and transform data.

        Steps: Center → Covariance → Eigendecomposition → Project
        """
        X = np.asarray(X, dtype=float)
        n, p = X.shape

        mean = np.mean(X, axis=0)
        X_centered = X - mean

        scale: np.ndarray | None = None
        if standardize:
            scale = np.std(X, axis=0, ddof=1)
            scale = np.maximum(scale, 1e-10)
            X_centered = X_centered / scale

        cov = np.cov(X_centered, rowvar=False)
        if cov.ndim == 1:
            cov = cov.reshape(1, 1)

        eigenvalues, eigenvectors = np.linalg.eigh(cov)
        idx = np.argsort(eigenvalues)[::-1]
        eigenvalues = eigenvalues[idx]
        eigenvectors = eigenvectors[:, idx]
        eigenvalues = np.maximum(eigenvalues, 0)

        k: int = min(n_components, p)
        loadings = eigenvectors[:, :k]
        reduced = X_centered @ loadings

        total_var: float = float(np.sum(eigenvalues))
        var_explained = eigenvalues[:k] / max(total_var, 1e-10)
        cum_var = np.cumsum(var_explained)

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
    ) -> dict[str, Any]:
        """Select number of components to retain given variance proportion."""
        result = PCAAnalyzer.fit_transform(X, n_components=X.shape[1], standardize=standardize)
        cum_var = result["cumulative_variance"]
        eigenvalues = result["eigenvalues"]

        k_threshold: int = min(int(np.searchsorted(cum_var, variance_threshold) + 1), len(cum_var))

        k_elbow: int = 1
        if len(eigenvalues) >= 3:
            diffs = np.diff(eigenvalues)
            diffs2 = np.diff(diffs)
            k_elbow = int(np.argmax(diffs2) + 2)

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
        feature_names: list[str],
        n_components: int = 3,
        threshold: float = 0.3,
    ) -> list[dict[str, Any]]:
        """Interpret PCA loadings to label components."""
        interpretations: list[dict[str, Any]] = []
        k: int = min(n_components, loadings.shape[1])

        for j in range(k):
            col = loadings[:, j]
            sorted_idx = np.argsort(np.abs(col))[::-1]
            top_features: list[dict[str, Any]] = []
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


class FactorAnalyzer:
    """
    Factor Analysis (STA 442).

    Models observed variables as linear combinations of latent factors:
        X = μ + Λf + ε

    Extraction: Iterative principal axis factoring
    Rotation: Varimax (orthogonal)
    """

    @staticmethod
    def fit(
        X: np.ndarray,
        n_factors: int = 3,
        max_iter: int = 50,
        rotation: str = "varimax",
    ) -> dict[str, Any]:
        """
        Fit factor analysis model via iterative principal axis factoring.
        """
        X = np.asarray(X, dtype=float)
        n, p = X.shape
        X_c = X - np.mean(X, axis=0)

        R = np.corrcoef(X_c, rowvar=False)
        if R.ndim == 1:
            R = R.reshape(1, 1)
        R = np.nan_to_num(R, nan=0.0)
        np.fill_diagonal(R, 1.0)

        eigvals, eigvecs = np.linalg.eigh(R)
        idx = np.argsort(eigvals)[::-1]
        eigvals = eigvals[idx]
        eigvecs = eigvecs[:, idx]

        k: int = min(n_factors, p)
        loadings = eigvecs[:, :k] * np.sqrt(np.maximum(eigvals[:k], 0))

        communalities = np.sum(loadings ** 2, axis=1)
        converged: bool = False
        for _ in range(max_iter):
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

        if rotation == "varimax" and k > 1:
            rotated_loadings = FactorAnalyzer._varimax(loadings)
        else:
            rotated_loadings = loadings

        var_explained = np.sum(rotated_loadings ** 2, axis=0)
        var_pct = var_explained / max(p, 1) * 100
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
        """Varimax rotation (Kaiser, 1958)."""
        p, k = loadings.shape
        R = np.eye(k)

        for _ in range(max_iter):
            rotated = loadings @ R
            B = rotated ** 2
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
        feature_names: list[str],
        factor_names: list[str] | None = None,
        threshold: float = 0.3,
    ) -> list[dict[str, Any]]:
        """Interpret factor loadings for economic meaning."""
        k: int = loadings.shape[1]
        if factor_names is None:
            factor_names = [f"Factor_{j+1}" for j in range(k)]

        interpretations: list[dict[str, Any]] = []
        for j in range(k):
            col = loadings[:, j]
            sorted_idx = np.argsort(np.abs(col))[::-1]
            markers: list[dict[str, Any]] = []
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


class DiscriminantAnalyzer:
    """
    Linear Discriminant Analysis (STA 442).

    Fisher's LDA finds the projection that maximizes the ratio of
    between-group to within-group variance.
    """

    @staticmethod
    def fit_predict(
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_test: np.ndarray,
    ) -> dict[str, Any]:
        """
        Fit Fisher's LDA and predict test labels.
        """
        X_train = np.asarray(X_train, dtype=float)
        y_train = np.asarray(y_train)
        X_test = np.asarray(X_test, dtype=float)

        classes = np.unique(y_train)
        n_classes: int = len(classes)

        if n_classes < 2:
            return {
                "predicted_labels": np.zeros(len(X_test), dtype=int),
                "discriminant_scores": np.zeros(len(X_test)),
                "error": "Need at least 2 classes",
            }

        mu_total = np.mean(X_train, axis=0)
        p: int = X_train.shape[1]

        S_W = np.zeros((p, p))
        S_B = np.zeros((p, p))
        group_stats: dict[int, dict[str, Any]] = {}

        for c in classes:
            mask = y_train == c
            X_c = X_train[mask]
            n_c: int = len(X_c)
            mu_c = np.mean(X_c, axis=0)
            S_W += (X_c - mu_c).T @ (X_c - mu_c)
            diff = (mu_c - mu_total).reshape(-1, 1)
            S_B += n_c * (diff @ diff.T)
            group_stats[int(c)] = {
                "n": int(n_c),
                "mean": [round(float(v), 4) for v in mu_c],
            }

        S_W += np.eye(p) * 1e-6

        if n_classes == 2:
            mu0 = np.mean(X_train[y_train == classes[0]], axis=0)
            mu1 = np.mean(X_train[y_train == classes[1]], axis=0)
            try:
                S_W_inv = np.linalg.inv(S_W)
                a = S_W_inv @ (mu1 - mu0)
            except np.linalg.LinAlgError:
                a = mu1 - mu0

            scores_train = X_train @ a
            scores_test = X_test @ a
            threshold: float = 0.5 * (mu0 @ a + mu1 @ a)
            predicted = (scores_test > threshold).astype(int)

            train_pred = (scores_train > threshold).astype(int)
            y_binary = (y_train == classes[1]).astype(int)
            accuracy: float = float(np.mean(train_pred == y_binary))

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
            try:
                eigvals, eigvecs = np.linalg.eigh(np.linalg.inv(S_W) @ S_B)
                idx = np.argsort(eigvals)[::-1]
                eigvals = eigvals[idx]
                eigvecs = eigvecs[:, idx]
                n_disc: int = min(n_classes - 1, p)
                W = eigvecs[:, :n_disc]
            except np.linalg.LinAlgError:
                W = np.eye(p)[:, :min(n_classes - 1, p)]

            proj_train = X_train @ W
            proj_test = X_test @ W

            proj_means: dict[int, np.ndarray] = {}
            for c in classes:
                proj_means[int(c)] = np.mean(proj_train[y_train == c], axis=0)

            predicted = np.zeros(len(X_test), dtype=int)
            for i in range(len(X_test)):
                best_c = classes[0]
                best_dist: float = np.inf
                for c in classes:
                    d: float = float(np.linalg.norm(proj_test[i] - proj_means[int(c)]))
                    if d < best_dist:
                        best_dist = d
                        best_c = c
                predicted[i] = int(best_c)

            train_pred = np.zeros(len(X_train), dtype=int)
            for i in range(len(X_train)):
                best_c = classes[0]
                best_dist = np.inf
                for c in classes:
                    d = float(np.linalg.norm(proj_train[i] - proj_means[int(c)]))
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


class MANOVA:
    """
    Multivariate Analysis of Variance (STA 442).

    Tests whether group means differ significantly across multiple
    dependent variables simultaneously.
    """

    @staticmethod
    def fit(
        X: np.ndarray,
        groups: np.ndarray,
    ) -> dict[str, Any]:
        """Fit one-way MANOVA."""
        X = np.asarray(X, dtype=float)
        groups = np.asarray(groups)
        n, p = X.shape
        classes = np.unique(groups)
        k: int = len(classes)

        if k < 2:
            return {"error": "Need at least 2 groups"}

        mu = np.mean(X, axis=0)

        W = np.zeros((p, p))
        B = np.zeros((p, p))
        for c in classes:
            mask = groups == c
            X_c = X[mask]
            n_c: int = len(X_c)
            mu_c = np.mean(X_c, axis=0)
            W += (X_c - mu_c).T @ (X_c - mu_c)
            diff = (mu_c - mu).reshape(-1, 1)
            B += n_c * (diff @ diff.T)

        T_mat = W + B

        try:
            wilks: float = float(np.linalg.det(W) / max(np.linalg.det(T_mat), 1e-30))
        except np.linalg.LinAlgError:
            wilks = 1.0

        W_reg = W + np.eye(p) * 1e-10
        try:
            eigvals = np.abs(np.linalg.eigvalsh(np.linalg.inv(W_reg) @ B))
            eigvals = np.sort(eigvals)[::-1]
        except np.linalg.LinAlgError:
            eigvals = np.zeros(p)

        pillai: float = float(np.sum(eigvals / (1 + eigvals)))
        hotelling: float = float(np.sum(eigvals))
        roy: float = float(eigvals[0]) if len(eigvals) > 0 else 0.0

        df_hypo: int = p * (k - 1)
        df_error: int = n - k
        s_val: int = min(p, k - 1)
        if wilks > 0 and df_error > 0:
            wilks_f: float = ((1 - wilks ** (1 / s_val)) / max(wilks ** (1 / s_val), 1e-10)) * (df_error / df_hypo) if df_hypo > 0 else 0
        else:
            wilks_f = 0

        f_pvalue: float = 1 - float(stats.f.cdf(max(wilks_f, 0), df_hypo, max(df_error, 1)))

        return {
            "wilks_lambda": round(wilks, 6),
            "pillai_trace": round(pillai, 6),
            "hotelling_lawley_trace": round(hotelling, 6),
            "roys_largest_root": round(roy, 6),
            "f_approximation": round(wilks_f, 4),
            "df_hypothesis": int(df_hypo),
            "df_error": int(df_error),
            "p_value": round(f_pvalue, 6),
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


__all__ = ["MANOVA", "DiscriminantAnalyzer", "FactorAnalyzer", "PCAAnalyzer"]
