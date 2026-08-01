/// Angavu Intelligence Backend — Statistical Methods Module
///
/// Bridges Python statistical methods to the Rust backend.
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
///
/// Available methods from python/statistical/econometrics.py (ECO 414/424, STA 442):
///   - OLSRegression: Ordinary Least Squares with full diagnostics
///   - HeteroskedasticityTests: Breusch-Pagan, White test, robust SE
///   - IV2SLS: Instrumental Variables / Two-Stage Least Squares
///   - GMMEstimator: Generalized Method of Moments (two-step)
///   - PanelDataEstimator: Fixed/Random Effects, Hausman test
///   - LimitedDependentVariable: Probit/Logit for binary outcomes
///   - VARModel: Vector Autoregression with Granger causality
///   - CointegrationTest: Engle-Granger cointegration test
///   - VECMModel: Vector Error Correction Model
///   - BootstrapHypothesisTest: Bootstrap-t for regression coefficients
///
/// Available methods from python/statistical/multivariate.py (STA 343/346):
///   - PCAAnalysis: Principal Component Analysis (eigendecomposition)
///   - DBSCANClusterer: Density-based clustering for anomaly detection
///   - LDAClassifier: Linear Discriminant Analysis (classification)
///   - QDAClassifier: Quadratic Discriminant Analysis (classification)
///   - MANOVATest: Multivariate Analysis of Variance (Wilks' Lambda)
///
/// Available methods from python/statistical/nonparametric_extended.py (STA 442/443):
///   - FriedmanTest: Non-parametric repeated measures
///   - KolmogorovSmirnovTest: Distribution goodness-of-fit
///   - AndersonDarlingTest: Distribution fit assessment (tail-sensitive)
///   - LOESSRegression: Non-parametric local polynomial regression
///   - BootstrapBCa: Bias-corrected accelerated bootstrap CI
///   - NonparametricSplineRegression: Cubic smoothing splines
///
/// Available methods from python/statistical/distributions.py (STA 241/341):
///   - DistributionFitter: MLE fitting for Normal, Exponential, Gamma, Beta, etc.
///   - MomentGeneratingFunction: MGF computation for distributions
///   - CentralLimitTheorem: CLT demonstration and sampling distributions
///   - GoodnessOfFit: Chi-squared, KS, Anderson-Darling tests
///   - ParametricBootstrap: Parametric bootstrap CIs
///
/// Available methods from python/statistical/stationarity_causality.py:
///   - KPSS_test: Stationarity test (complement to ADF)
///   - GrangerCausalityTest: Granger causality for economic variables
///   - ConfidenceIntervals: Comprehensive CI computation
///   - BootstrapBCa: Bias-corrected accelerated bootstrap CIs
///
/// Available methods from python/statistical/control_charts.py:
///   - CUSUMChart: Cumulative sum chart for small shift detection
///   - EWMAChart: Exponentially weighted moving average chart
///   - ProcessCapability: Cp, Cpk indices for model quality

pub mod nonparametric_bridge;
/// STA 442/443: Extended non-parametric methods (Friedman, KS, AD, LOESS, BCa, Splines)
pub mod extended_nonparametric_bridge;
/// STA 343/346: Multivariate analysis bridge (PCA, DBSCAN, LDA, QDA, MANOVA)
pub mod multivariate_bridge;
/// ECO 414/424: Econometrics bridge (OLS, 2SLS, GMM, Panel, Probit/Logit, VAR/VECM)
pub mod econometrics_bridge;
pub mod types;
/// S10: Differential privacy implementation using the Laplace mechanism
pub mod differential_privacy;
/// STA 241/341: Distribution fitting, MGF, CLT, goodness-of-fit
pub mod distributions_bridge;
/// KPSS stationarity, Granger causality, confidence intervals, BCa bootstrap
pub mod stationarity_bridge;
/// STA 346: CUSUM, EWMA control charts, process capability (Cp, Cpk)
pub mod control_charts_bridge;

pub use nonparametric_bridge::NonparametricBridge;
pub use extended_nonparametric_bridge::ExtendedNonparametricBridge;
pub use multivariate_bridge::MultivariateBridge;
pub use econometrics_bridge::*;
pub use types::*;
pub use differential_privacy::{DifferentialPrivacyEngine, MechanismType};
pub use distributions_bridge::DistributionBridge;
pub use stationarity_bridge::StationarityBridge;
pub use control_charts_bridge::ControlChartsBridge;
