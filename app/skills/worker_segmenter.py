"""
Worker Segmenter — STA 442: Applied Multivariate Analysis

Maps STA 442 (Applied Multivariate Analysis) course unit into
executable worker segmentation and profiling capabilities.

Capabilities:
- PCA for dimensionality reduction of worker features
- Factor analysis for latent creditworthiness factors
- Cluster analysis for worker segmentation
- LDA for worker type classification
- MANOVA for group comparison

Theoretical Foundations:
- Principal Component Analysis (Hotelling, 1933)
- Factor Analysis (Spearman, 1900; Kaiser varimax rotation)
- K-means clustering with k-means++ initialization
- Fisher's Linear Discriminant Analysis
- MANOVA (Wilks' Lambda, Pillai's trace)

Wired into: WorkerClassifier, ReportGenerator
"""

from __future__ import annotations

from typing import Any

import numpy as np
import structlog

from app.skills.base import BaseSkill, SkillResult

logger = structlog.get_logger(__name__)


class WorkerSegmenter(BaseSkill):
    """
    STA 442 — Applied Multivariate Analysis

    Segments workers using PCA, factor analysis, and clustering
    to create actionable intelligence profiles.
    """

    def __init__(self):
        super().__init__(
            name="worker_segmenter",
            course_unit="STA 442 — Applied Multivariate Analysis",
            description=(
                "PCA for dimensionality reduction, factor analysis for latent variables, "
                "and cluster analysis for worker segmentation."
            ),
            version="1.0.0",
            agent_bindings=["ReportGenerator", "IntelligenceGenerator"],
        )

    async def execute(self, action: str, **kwargs) -> SkillResult:
        actions = {
            "pca": self._pca,
            "factor_analysis": self._factor_analysis,
            "cluster_segment": self._cluster_segment,
            "elbow_method": self._elbow_method,
            "lda_classify": self._lda_classify,
            "manova_test": self._manova_test,
            "profile_segments": self._profile_segments,
        }

        if action not in actions:
            return SkillResult(
                success=False,
                skill_name=self.name,
                error=f"Unknown action: {action}. Available: {list(actions.keys())}",
            )

        try:
            data = await actions[action](**kwargs)
            return SkillResult(
                success=True,
                skill_name=self.name,
                data=data,
                confidence=data.get("_confidence", 0.85),
            )
        except Exception as exc:
            return SkillResult(
                success=False,
                skill_name=self.name,
                error=str(exc),
            )

    async def _pca(
        self,
        X: list[list[float]],
        n_components: int = 3,
        feature_names: list[str] | None = None,
        standardize: bool = False,
    ) -> dict[str, Any]:
        """
        Principal Component Analysis for dimensionality reduction.

        Args:
            X: Data matrix (n × p)
            n_components: Number of components to retain
            feature_names: Names for features
            standardize: Whether to standardize first

        Returns:
            Dict with reduced data, eigenvalues, loadings, variance explained
        """
        from app.services.statistical_foundation import PCAAnalyzer

        data = np.array(X, dtype=float)
        result = PCAAnalyzer.fit_transform(data, n_components=n_components, standardize=standardize)

        # Add interpretation
        if feature_names:
            interpretations = PCAAnalyzer.interpret_loadings(
                result["loadings"], feature_names, n_components
            )
            result["interpretations"] = interpretations

        # Convert numpy arrays to lists for JSON serialization
        result["reduced_data"] = result["reduced_data"].tolist()
        result["eigenvalues"] = [round(float(v), 4) for v in result["eigenvalues"]]
        result["variance_explained"] = [round(float(v), 4) for v in result["variance_explained"]]
        result["cumulative_variance"] = [round(float(v), 4) for v in result["cumulative_variance"]]
        result["loadings"] = result["loadings"].tolist()

        result["_confidence"] = 0.9
        return result

    async def _factor_analysis(
        self,
        X: list[list[float]],
        n_factors: int = 3,
        feature_names: list[str] | None = None,
        factor_names: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Factor Analysis for latent variable extraction.

        Extracts latent factors (e.g., Transaction Intensity,
        Financial Discipline, Market Position) from correlated
        worker features.

        Args:
            X: Data matrix (n × p)
            n_factors: Number of latent factors
            feature_names: Observed variable names
            factor_names: Latent factor labels

        Returns:
            Dict with factor loadings, communalities, interpretations
        """
        from app.services.statistical_foundation import FactorAnalyzer

        data = np.array(X, dtype=float)
        result = FactorAnalyzer.fit(data, n_factors=n_factors)

        if feature_names:
            interpretation = FactorAnalyzer.interpret_factors(
                result["loadings"], feature_names, factor_names,
            )
            result["factor_interpretations"] = interpretation

        # Serialize
        result["loadings"] = result["loadings"].tolist()
        result["communalities"] = [round(float(v), 4) for v in result["communalities"]]
        result["uniquenesses"] = [round(float(v), 4) for v in result["uniquenesses"]]
        result["variance_explained_pct"] = [round(float(v), 2) for v in result["variance_explained_pct"]]

        result["_confidence"] = 0.85
        return result

    async def _cluster_segment(
        self,
        X: list[list[float]],
        feature_names: list[str] | None = None,
        max_k: int = 8,
        seed: int = 42,
    ) -> dict[str, Any]:
        """
        Market/worker segmentation using K-means clustering.

        Automatically selects optimal k, runs clustering, and
        produces interpretable segment profiles.

        Args:
            X: Feature matrix (n × d)
            feature_names: Feature names
            max_k: Maximum clusters to try
            seed: Random seed

        Returns:
            Dict with segments, profiles, quality metrics
        """
        from app.services.statistical_foundation import ClusterAnalyzer

        data = np.array(X, dtype=float)
        result = ClusterAnalyzer.segment_market(data, feature_names=feature_names, max_k=max_k, seed=seed)

        # Serialize labels
        result["labels"] = result["labels"] if isinstance(result["labels"], list) else result["labels"].tolist()

        result["_confidence"] = 0.8
        return result

    async def _elbow_method(
        self,
        X: list[list[float]],
        max_k: int = 10,
    ) -> dict[str, Any]:
        """
        Elbow method for optimal cluster count selection.
        """
        from app.services.statistical_foundation import ClusterAnalyzer

        data = np.array(X, dtype=float)
        result = ClusterAnalyzer.elbow_method(data, max_k=max_k)

        result["_confidence"] = 0.85
        return result

    async def _lda_classify(
        self,
        X_train: list[list[float]],
        y_train: list[int],
        X_test: list[list[float]],
    ) -> dict[str, Any]:
        """
        Fisher's Linear Discriminant Analysis for classification.

        Finds the projection that maximizes between-group to
        within-group variance ratio.
        """
        from app.services.statistical_foundation import DiscriminantAnalyzer

        result = DiscriminantAnalyzer.fit_predict(
            np.array(X_train, dtype=float),
            np.array(y_train),
            np.array(X_test, dtype=float),
        )

        # Serialize
        result["predicted_labels"] = result["predicted_labels"].tolist()
        if isinstance(result.get("discriminant_scores"), np.ndarray):
            result["discriminant_scores"] = result["discriminant_scores"].tolist()

        result["_confidence"] = 0.8
        return result

    async def _manova_test(
        self,
        X: list[list[float]],
        groups: list[int],
    ) -> dict[str, Any]:
        """
        MANOVA test for group mean differences across multiple variables.
        """
        from app.services.statistical_foundation import MANOVA

        result = MANOVA.fit(
            np.array(X, dtype=float),
            np.array(groups),
        )

        result["_confidence"] = 0.85
        return result

    async def _profile_segments(
        self,
        X: list[list[float]],
        labels: list[int],
        feature_names: list[str],
    ) -> dict[str, Any]:
        """
        Generate interpretable profiles for each segment.

        For each cluster, computes mean, std, min, max for each feature
        and assigns descriptive labels.
        """
        data = np.array(X, dtype=float)
        labels_arr = np.array(labels)
        unique_labels = sorted(set(labels))

        segments = []
        for label in unique_labels:
            mask = labels_arr == label
            members = data[mask]
            n_members = int(np.sum(mask))

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

            # Auto-label based on dominant features
            means = {fname: profile[fname]["mean"] for fname in feature_names}
            sorted_features = sorted(means.items(), key=lambda x: x[1], reverse=True)
            label_desc = f"High {sorted_features[0][0]}, Low {sorted_features[-1][0]}"

            segments.append({
                "segment_id": int(label),
                "size": n_members,
                "proportion": round(n_members / len(data), 4),
                "profile": profile,
                "auto_label": label_desc,
            })

        return {
            "n_segments": len(unique_labels),
            "segments": segments,
            "feature_names": feature_names,
            "_confidence": 0.85,
        }
