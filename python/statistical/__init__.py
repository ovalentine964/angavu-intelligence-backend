"""
Angavu Intelligence Backend — Statistical Methods Package

Non-parametric and distribution-free inference methods for the Kenyan
informal sector, where data is typically non-normal.

Modules:
- nonparametric: KDE, Mann-Whitney, Kruskal-Wallis, Bootstrap, Permutation tests
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

# CLI runner for Rust backend bridge
from . import nonparametric_runner

__all__ = [
    "BootstrapInference",
    "DifferentialPrivacy",
    "KernelDensityEstimator",
    "KruskalWallisTest",
    "MannWhitneyTest",
    "MarketConcentration",
    "PermutationTest",
    "PowerAnalysis",
    "nonparametric_runner",
]
