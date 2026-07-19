"""
Statistical Foundation Layer — Backward-Compatible Facade.

This module re-exports all classes from the decomposed sub-modules
under app/services/statistical/ for backward compatibility.

The monolithic 2,288-line implementation has been split into:
- statistical/bayesian.py      — BayesianUpdater, KernelDensityEstimator (STA 341, STA 444)
- statistical/hypothesis.py    — HypothesisTester, BootstrapInference, DistributionFitter (STA 342, STA 444)
- statistical/multivariate.py  — PCAAnalyzer, FactorAnalyzer, DiscriminantAnalyzer, MANOVA (STA 442)
- statistical/clustering.py    — ClusterAnalyzer (K-means) (STA 442)
- statistical/simulation.py    — MonteCarloEngine, MCMCSampler (STA 347)

All existing imports continue to work:
    from app.services.statistical_foundation import BayesianUpdater  # ✓
    from app.services.statistical_foundation import kde_estimator    # ✓

For new code, prefer:
    from app.services.statistical import BayesianUpdater
"""

# Re-export all classes from sub-modules for backward compatibility
from app.services.statistical.bayesian import BayesianUpdater, KernelDensityEstimator
from app.services.statistical.clustering import ClusterAnalyzer
from app.services.statistical.frontier import DEAAnalyzer, SFAAnalyzer
from app.services.statistical.hypothesis import (
    BootstrapInference,
    DistributionFitter,
    HypothesisTester,
)
from app.services.statistical.inequality import InequalityAnalyzer, PovertyAnalyzer
from app.services.statistical.multivariate import (
    DiscriminantAnalyzer,
    FactorAnalyzer,
    PCAAnalyzer,
)
from app.services.statistical.simulation import MCMCSampler, MonteCarloEngine

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
inequality_analyzer = InequalityAnalyzer()
poverty_analyzer = PovertyAnalyzer()
dea_analyzer = DEAAnalyzer()
sfa_analyzer = SFAAnalyzer()
