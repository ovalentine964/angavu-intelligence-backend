"""
Angavu Intelligence Backend — Statistical Methods Package

Non-parametric, distribution-free, and econometric inference methods
for the Kenyan informal sector.

Modules:
- nonparametric: KDE, Mann-Whitney, Kruskal-Wallis, Bootstrap, Permutation tests
- econometrics: OLS, IV/2SLS, GMM, Panel Data, Probit/Logit, VAR/VECM, Cointegration
"""

from .nonparametric import (
    BootstrapInference,
    DifferentialPrivacy,
    KernelDensityEstimator,
    KruskalWallisTest,
    MannWhitneyTest,
    MarketConcentration,
    PermutationTest,
    PowerAnalysis,
)

from .econometrics import (
    OLSRegression,
    HeteroskedasticityTests,
    IV2SLS,
    GMMEstimator,
    PanelDataEstimator,
    LimitedDependentVariable,
    VARModel,
    CointegrationTest,
    VECMModel,
    BootstrapHypothesisTest,
)

from .international_economics import (
    ExchangeRateTracker,
    CrossBorderTradeAdvisor,
    FiscalPolicyAnalyzer,
    MarketStructureAnalyzer,
)

# CLI runners for Rust backend bridge
# Note: runners are standalone scripts (use absolute imports),
# invoked via subprocess from Rust. Not imported as modules.
# - nonparametric_runner.py
# - econometrics_runner.py
# - international_economics_runner.py

__all__ = [
    "BootstrapInference",
    "DifferentialPrivacy",
    "KernelDensityEstimator",
    "KruskalWallisTest",
    "MannWhitneyTest",
    "MarketConcentration",
    "PermutationTest",
    "PowerAnalysis",
    "OLSRegression",
    "HeteroskedasticityTests",
    "IV2SLS",
    "GMMEstimator",
    "PanelDataEstimator",
    "LimitedDependentVariable",
    "VARModel",
    "CointegrationTest",
    "VECMModel",
    "BootstrapHypothesisTest",
    "ExchangeRateTracker",
    "CrossBorderTradeAdvisor",
    "FiscalPolicyAnalyzer",
    "MarketStructureAnalyzer",
    "nonparametric_runner",
    "econometrics_runner",
    "international_economics_runner",
]
