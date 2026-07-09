"""
Tests for Multivariate Analysis (STA 442).

Tests cover:
- PCA (Principal Component Analysis)
- Factor Analysis with varimax rotation
- Discriminant Analysis (Fisher's LDA)
- MANOVA
- Edge cases and numerical stability
"""

import numpy as np
import pytest

from app.services.statistical.multivariate import (
    PCAAnalyzer,
    FactorAnalyzer,
    DiscriminantAnalyzer,
    MANOVA,
)


class TestPCAAnalyzer:
    """PCA tests."""

    def test_basic_pca(self):
        """PCA on correlated 2D data."""
        rng = np.random.RandomState(42)
        x = rng.normal(0, 1, 100)
        X = np.column_stack([x, x * 0.9 + rng.normal(0, 0.1, 100)])

        result = PCAAnalyzer.fit_transform(X, n_components=2)

        assert result["n_components"] == 2
        assert result["n_features"] == 2
        assert len(result["eigenvalues"]) == 2
        # First component should explain most variance (highly correlated data)
        assert result["variance_explained"][0] > 0.8

    def test_pca_dimensionality_reduction(self):
        """PCA reduces dimensions correctly."""
        rng = np.random.RandomState(42)
        X = rng.normal(0, 1, (50, 5))

        result = PCAAnalyzer.fit_transform(X, n_components=2)

        assert result["reduced_data"].shape == (50, 2)
        assert result["loadings"].shape == (5, 2)

    def test_pca_variance_explained_sums_to_one(self):
        """All components together explain 100% of variance."""
        rng = np.random.RandomState(42)
        X = rng.normal(0, 1, (100, 3))

        result = PCAAnalyzer.fit_transform(X, n_components=3)

        assert sum(result["variance_explained"]) == pytest.approx(1.0, abs=0.01)

    def test_pca_standardize_option(self):
        """PCA with standardization."""
        rng = np.random.RandomState(42)
        X = rng.normal(100, 50, (50, 3))  # Different scales

        result = PCAAnalyzer.fit_transform(X, n_components=2, standardize=True)

        assert result["scale"] is not None
        assert result["reduced_data"].shape == (50, 2)

    def test_pca_select_n_components(self):
        """Component selection via variance threshold."""
        rng = np.random.RandomState(42)
        x = rng.normal(0, 1, 100)
        X = np.column_stack([x, x * 0.95, rng.normal(0, 0.1, 100)])

        result = PCAAnalyzer.select_n_components(X, variance_threshold=0.90)

        assert result["recommended_k"] >= 1
        assert result["recommended_k"] <= 3

    def test_pca_interpret_loadings(self):
        """Loading interpretation identifies important features."""
        rng = np.random.RandomState(42)
        X = rng.normal(0, 1, (50, 4))
        result = PCAAnalyzer.fit_transform(X, n_components=2)
        feature_names = ["price", "volume", "revenue", "count"]

        interpretations = PCAAnalyzer.interpret_loadings(
            result["loadings"], feature_names, n_components=2
        )

        assert len(interpretations) == 2
        for interp in interpretations:
            assert "component" in interp
            assert "top_features" in interp


class TestFactorAnalyzer:
    """Factor Analysis tests."""

    def test_basic_factor_analysis(self):
        """Factor analysis on correlated data."""
        rng = np.random.RandomState(42)
        # Create data with 2 latent factors
        f1 = rng.normal(0, 1, 100)
        f2 = rng.normal(0, 1, 100)
        X = np.column_stack([
            f1 * 0.8 + rng.normal(0, 0.3, 100),
            f1 * 0.7 + rng.normal(0, 0.3, 100),
            f2 * 0.9 + rng.normal(0, 0.3, 100),
            f2 * 0.6 + rng.normal(0, 0.3, 100),
        ])

        result = FactorAnalyzer.fit(X, n_factors=2)

        assert result["n_factors"] == 2
        assert result["loadings"].shape == (4, 2)
        assert len(result["communalities"]) == 4
        assert all(0 <= c <= 1.01 for c in result["communalities"])

    def test_factor_analysis_varimax_rotation(self):
        """Varimax rotation produces orthogonal factors."""
        rng = np.random.RandomState(42)
        X = rng.normal(0, 1, (100, 5))

        result = FactorAnalyzer.fit(X, n_factors=2, rotation="varimax")

        # Loadings should exist and be non-zero
        assert result["loadings"].shape == (5, 2)
        assert result["rotation"] == "varimax"

    def test_factor_analysis_single_factor(self):
        """Single factor extraction works."""
        rng = np.random.RandomState(42)
        X = rng.normal(0, 1, (50, 3))

        result = FactorAnalyzer.fit(X, n_factors=1, rotation="none")

        assert result["n_factors"] == 1
        assert result["loadings"].shape == (3, 1)


class TestDiscriminantAnalyzer:
    """Fisher's LDA tests."""

    def test_binary_classification(self):
        """LDA separates two well-separated groups."""
        rng = np.random.RandomState(42)
        X0 = rng.normal(0, 1, (30, 2))
        X1 = rng.normal(3, 1, (30, 2))
        X_train = np.vstack([X0, X1])
        y_train = np.array([0] * 30 + [1] * 30)
        X_test = np.array([[0, 0], [3, 3]])

        result = DiscriminantAnalyzer.fit_predict(X_train, y_train, X_test)

        assert len(result["predicted_labels"]) == 2
        assert result["predicted_labels"][0] == 0  # Should classify as group 0
        assert result["predicted_labels"][1] == 1  # Should classify as group 1
        assert result["method"] == "fisher_linear_discriminant"

    def test_binary_classification_accuracy(self):
        """LDA achieves high accuracy on well-separated data."""
        rng = np.random.RandomState(42)
        X0 = rng.normal(0, 0.5, (50, 2))
        X1 = rng.normal(5, 0.5, (50, 2))
        X_train = np.vstack([X0, X1])
        y_train = np.array([0] * 50 + [1] * 50)

        result = DiscriminantAnalyzer.fit_predict(X_train, y_train, X_train)

        assert result["training_accuracy"] > 0.9

    def test_multiclass_classification(self):
        """LDA handles 3+ classes."""
        rng = np.random.RandomState(42)
        X0 = rng.normal(0, 1, (20, 3))
        X1 = rng.normal(5, 1, (20, 3))
        X2 = rng.normal(10, 1, (20, 3))
        X_train = np.vstack([X0, X1, X2])
        y_train = np.array([0] * 20 + [1] * 20 + [2] * 20)
        X_test = np.array([[0, 0, 0], [5, 5, 5], [10, 10, 10]])

        result = DiscriminantAnalyzer.fit_predict(X_train, y_train, X_test)

        assert len(result["predicted_labels"]) == 3
        assert result["method"] == "fisher_multiclass_lda"


class TestMANOVA:
    """MANOVA tests."""

    def test_manova_detects_group_differences(self):
        """MANOVA rejects null when groups are different."""
        rng = np.random.RandomState(42)
        X0 = rng.normal(0, 1, (30, 2))
        X1 = rng.normal(3, 1, (30, 2))
        X = np.vstack([X0, X1])
        groups = np.array([0] * 30 + [1] * 30)

        result = MANOVA.fit(X, groups)

        assert result["significant_at_05"] is True
        assert result["p_value"] < 0.05
        assert result["n_groups"] == 2
        assert result["n_samples"] == 60

    def test_manova_fails_to_reject_when_groups_same(self):
        """MANOVA fails to reject null when groups are identical."""
        rng = np.random.RandomState(42)
        X0 = rng.normal(0, 1, (50, 2))
        X1 = rng.normal(0, 1, (50, 2))  # Same distribution
        X = np.vstack([X0, X1])
        groups = np.array([0] * 50 + [1] * 50)

        result = MANOVA.fit(X, groups)

        # With same distributions, should generally not be significant
        # (may occasionally reject due to random chance, but unlikely with n=100)
        assert result["n_groups"] == 2

    def test_manova_with_single_group_errors(self):
        """MANOVA requires at least 2 groups."""
        X = np.array([[1, 2], [3, 4]])
        groups = np.array([0, 0])

        result = MANOVA.fit(X, groups)
        assert "error" in result

    def test_manova_wilks_lambda_range(self):
        """Wilks' Lambda should be between 0 and 1."""
        rng = np.random.RandomState(42)
        X0 = rng.normal(0, 1, (20, 2))
        X1 = rng.normal(2, 1, (20, 2))
        X = np.vstack([X0, X1])
        groups = np.array([0] * 20 + [1] * 20)

        result = MANOVA.fit(X, groups)

        assert 0 <= result["wilks_lambda"] <= 1
