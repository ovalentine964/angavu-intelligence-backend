"""
Statistical Foundation — Decomposed into focused sub-modules.

This package replaces the monolithic statistical_foundation.py (2,288 lines)
with focused modules for better maintainability:

- bayesian.py       — BayesianUpdater, KernelDensityEstimator (STA 341, STA 444)
- hypothesis.py     — HypothesisTester, BootstrapInference, DistributionFitter (STA 342, STA 444)
- multivariate.py   — PCAAnalyzer, FactorAnalyzer, DiscriminantAnalyzer, MANOVA (STA 442)
- clustering.py     — ClusterAnalyzer (K-means, hierarchical) (STA 442)
- simulation.py     — MonteCarloEngine, MCMCSampler (STA 347)

All classes are re-exported here for convenience:
    from app.services.statistical import BayesianUpdater  # works
    from app.services.statistical_foundation import BayesianUpdater  # still works (facade)
"""

from app.services.statistical.bayesian import BayesianUpdater, KernelDensityEstimator
from app.services.statistical.hypothesis import (
    BootstrapInference,
    DistributionFitter,
    HypothesisTester,
)
from app.services.statistical.multivariate import (
    DiscriminantAnalyzer,
    FactorAnalyzer,
    MANOVA,
    PCAAnalyzer,
)
from app.services.statistical.clustering import ClusterAnalyzer
from app.services.statistical.simulation import MCMCSampler, MonteCarloEngine
from app.services.statistical.inequality import InequalityAnalyzer, PovertyAnalyzer
from app.services.statistical.frontier import DEAAnalyzer, SFAAnalyzer

__all__ = [
    "BayesianUpdater",
    "KernelDensityEstimator",
    "BootstrapInference",
    "HypothesisTester",
    "DistributionFitter",
    "ClusterAnalyzer",
    "MonteCarloEngine",
    "MCMCSampler",
    "PCAAnalyzer",
    "FactorAnalyzer",
    "DiscriminantAnalyzer",
    "MANOVA",
    "InequalityAnalyzer",
    "PovertyAnalyzer",
    "DEAAnalyzer",
    "SFAAnalyzer",
]
