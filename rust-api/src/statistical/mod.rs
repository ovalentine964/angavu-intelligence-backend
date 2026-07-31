/// Angavu Intelligence Backend — Statistical Methods Module
///
/// Bridges Python statistical methods (nonparametric.py) to the Rust backend.
/// Uses subprocess execution for Python calls with JSON serialization.
///
/// Available methods from python/statistical/nonparametric.py:
///   - KernelDensityEstimator: Non-parametric density estimation
///   - MannWhitneyTest: Non-parametric two-sample comparison
///   - KruskalWallisTest: Non-parametric multi-group comparison
///   - BootstrapInference: Distribution-free confidence intervals
///   - PermutationTest: Exact hypothesis testing
///   - PowerAnalysis: Sample size determination
///   - DifferentialPrivacy: Privacy-preserving statistics
///   - MarketConcentration: HHI, Gini, Theil index

pub mod nonparametric_bridge;
pub mod types;
/// S10: Differential privacy implementation using the Laplace mechanism
pub mod differential_privacy;

pub use nonparametric_bridge::NonparametricBridge;
pub use types::*;
pub use differential_privacy::DifferentialPrivacyEngine;
