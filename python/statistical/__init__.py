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

from .nonparametric_advanced import (
    SignTest,
    RunsTest,
    MoodsMedianTest,
    NonparametricCI,
    NonparametricEffectSize,
)

from .spc_full import (
    XbarChart,
    RChart,
    PChart,
    CChart,
    AcceptanceSampling,
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

from .time_series_models import (
    ARIMAModel,
    SARIMAModel,
    ETSModel,
    StructuralBreakTests,
)

from .macro_models import (
    PhillipsCurve,
    ISLMModel,
    SolowGrowthModel,
    DemographicModels,
    TaylorRule,
    OkunsLaw,
    FisherEquation,
    MoneyMultiplier,
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
    "SignTest",
    "RunsTest",
    "MoodsMedianTest",
    "NonparametricCI",
    "NonparametricEffectSize",
    "XbarChart",
    "RChart",
    "PChart",
    "CChart",
    "AcceptanceSampling",
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
    # Time series models (STA 244)
    "ARIMAModel",
    "SARIMAModel",
    "ETSModel",
    "StructuralBreakTests",
    # Macroeconomic models (ECO 311/414)
    "PhillipsCurve",
    "ISLMModel",
    "SolowGrowthModel",
    "DemographicModels",
    "TaylorRule",
    "OkunsLaw",
    "FisherEquation",
    "MoneyMultiplier",
    "nonparametric_runner",
    "econometrics_runner",
    "international_economics_runner",
    "time_series_runner",
    "macro_runner",
]
