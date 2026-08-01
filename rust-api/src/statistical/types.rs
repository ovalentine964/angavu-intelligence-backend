/// Types for statistical methods bridge.
use serde::{Deserialize, Serialize};

/// Result from Mann-Whitney U test.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MannWhitneyResult {
    pub test_name: String,
    pub u_statistic: f64,
    pub p_value: f64,
    pub significant_at_05: bool,
    pub effect_size_rank_biserial: f64,
    pub effect_size_label: String,
    pub common_language_effect_size: f64,
    pub n1: usize,
    pub n2: usize,
    pub alternative: String,
    pub median_difference: f64,
}

/// Result from Kruskal-Wallis test.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct KruskalWallisResult {
    pub test_name: String,
    pub h_statistic: f64,
    pub p_value: f64,
    pub significant_at_05: bool,
    pub effect_size_epsilon_sq: f64,
    pub effect_size_label: String,
    pub n_groups: usize,
    pub total_n: usize,
    pub group_statistics: Vec<GroupStats>,
    pub post_hoc_comparisons: Vec<PostHocComparison>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GroupStats {
    pub group: usize,
    pub n: usize,
    pub median: f64,
    pub iqr: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PostHocComparison {
    pub group_i: usize,
    pub group_j: usize,
    pub z_statistic: f64,
    pub p_value_adjusted: f64,
    pub significant: bool,
}

/// Result from bootstrap confidence interval.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BootstrapResult {
    pub estimate: f64,
    pub ci_lower: f64,
    pub ci_upper: f64,
    pub confidence: f64,
    pub bootstrap_se: f64,
    pub bias: f64,
    pub n_bootstrap: usize,
    pub n_observations: usize,
}

/// Result from permutation test.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PermutationResult {
    pub test_name: String,
    pub observed_statistic: f64,
    pub p_value: f64,
    pub significant_at_05: bool,
    pub n_permutations: usize,
    pub n1: usize,
    pub n2: usize,
}

/// Result from power analysis.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PowerAnalysisResult {
    pub test: String,
    pub effect_size_cohens_d: f64,
    pub alpha: f64,
    pub power: f64,
    pub n_per_group: usize,
    pub total_n: usize,
}

/// Result from KDE.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct KDEResult {
    pub evaluation_points: Vec<f64>,
    pub density_values: Vec<f64>,
    pub n_modes: usize,
    pub mode_locations: Vec<f64>,
    pub is_multimodal: bool,
}

/// Result from market concentration analysis.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConcentrationResult {
    pub hhi: f64,
    pub concentration_level: String,
    pub n_firms: usize,
    pub gini: f64,
    pub gini_interpretation: String,
}

/// Generic error from Python bridge.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StatisticalError {
    pub error: String,
    pub method: String,
}

/// Result from distribution fitting.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DistributionFitResult {
    pub distribution: String,
    pub parameters: std::collections::HashMap<String, f64>,
    pub log_likelihood: f64,
    pub aic: f64,
    pub bic: f64,
    pub n: usize,
    pub ks_statistic: f64,
    pub ks_p_value: f64,
    pub goodness_of_fit: String,
}

/// Result from KPSS stationarity test.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct KPSSResult {
    pub kpss_statistic: f64,
    pub critical_values: std::collections::HashMap<String, f64>,
    pub is_stationary: bool,
    pub regression: String,
    pub lags: usize,
    pub n: usize,
    pub conclusion: String,
}

/// Result from Granger causality test.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GrangerCausalityResult {
    pub f_statistic: f64,
    pub p_value: f64,
    pub df1: usize,
    pub df2: usize,
    pub granger_causes: bool,
    pub lag: usize,
    pub rss_restricted: f64,
    pub rss_unrestricted: f64,
    pub conclusion: String,
}

/// Result from CUSUM chart analysis.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CUSUMResult {
    pub target: f64,
    pub sigma: f64,
    pub k: f64,
    pub h: f64,
    pub signals_upper: Vec<usize>,
    pub signals_lower: Vec<usize>,
    pub in_control: bool,
    pub arl0_in_control: f64,
    pub n: usize,
}

/// Result from EWMA chart analysis.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EWMAResult {
    pub ewma: Vec<f64>,
    pub ucl: Vec<f64>,
    pub lcl: Vec<f64>,
    pub target: f64,
    pub sigma: f64,
    pub lambda_param: f64,
    pub signals: Vec<usize>,
    pub in_control: bool,
    pub n: usize,
}

/// Result from process capability analysis.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProcessCapabilityResult {
    pub cp: f64,
    pub cpk: f64,
    pub cpu: f64,
    pub cpl: f64,
    pub cpm: f64,
    pub interpretation: String,
    pub mu: f64,
    pub sigma: f64,
    pub usl: f64,
    pub lsl: f64,
    pub ppm_defect_rate: f64,
    pub sigma_level: f64,
    pub n: usize,
}

/// Result from confidence interval computation.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConfidenceIntervalResult {
    pub estimate: f64,
    pub ci_lower: f64,
    pub ci_upper: f64,
    pub margin_of_error: f64,
    pub method: String,
    pub n: usize,
}

// ═══════════════════════════════════════════════════════════════
// Multivariate Analysis Types (STA 343/346)
// ═══════════════════════════════════════════════════════════════

/// Result from PCA (Principal Component Analysis).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PCAResult {
    pub n_components: usize,
    pub eigenvalues: Vec<f64>,
    pub variance_explained: Vec<f64>,
    pub cumulative_variance: Vec<f64>,
    pub components: Vec<Vec<f64>>,
    pub projected_data: Vec<Vec<f64>>,
    pub loadings: Vec<Vec<f64>>,
    pub total_variance_explained: f64,
}

/// Result from DBSCAN clustering.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DBSCANResult {
    pub labels: Vec<i32>,
    pub n_clusters: usize,
    pub cluster_sizes: std::collections::HashMap<usize, usize>,
    pub cluster_centers: std::collections::HashMap<usize, Vec<f64>>,
    pub noise_points: usize,
    pub noise_indices: Vec<usize>,
    pub anomaly_fraction: f64,
}

/// Result from LDA (Linear Discriminant Analysis).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LDAResult {
    pub classes: Vec<i32>,
    pub priors: std::collections::HashMap<i32, f64>,
    pub means: std::collections::HashMap<i32, Vec<f64>>,
    pub coefficients: std::collections::HashMap<i32, Vec<f64>>,
    pub intercepts: std::collections::HashMap<i32, f64>,
    pub pooled_covariance: Vec<Vec<f64>>,
    pub training_accuracy: f64,
    pub fisher_direction: Option<Vec<f64>>,
}

/// Result from QDA (Quadratic Discriminant Analysis).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QDAResult {
    pub classes: Vec<i32>,
    pub priors: std::collections::HashMap<i32, f64>,
    pub means: std::collections::HashMap<i32, Vec<f64>>,
    pub covariances: std::collections::HashMap<i32, Vec<Vec<f64>>>,
    pub training_accuracy: f64,
}

/// Result from MANOVA.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MANOVAResult {
    pub test_name: String,
    pub wilks_lambda: f64,
    pub pillai_trace: f64,
    pub lawley_hotelling_trace: f64,
    pub f_statistic: f64,
    pub df1: usize,
    pub df2: usize,
    pub p_value: f64,
    pub significant_at_05: bool,
    pub n_groups: usize,
    pub n_variables: usize,
    pub total_n: usize,
    pub group_means: Vec<Vec<f64>>,
}

// ═══════════════════════════════════════════════════════════════
// Extended Non-Parametric Types (STA 442/443)
// ═══════════════════════════════════════════════════════════════

/// Result from Friedman test.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FriedmanResult {
    pub test_name: String,
    pub chi_square: f64,
    pub df: usize,
    pub p_value: f64,
    pub significant_at_05: bool,
    pub kendall_w: f64,
    pub mean_ranks: Vec<f64>,
    pub n_blocks: usize,
    pub n_treatments: usize,
    pub post_hoc_comparisons: Vec<FriedmanComparison>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FriedmanComparison {
    pub treatment_i: usize,
    pub treatment_j: usize,
    pub rank_diff: f64,
    pub z_statistic: f64,
    pub p_adjusted: f64,
    pub significant: bool,
}

/// Result from Kolmogorov-Smirnov test.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct KSResult {
    pub test_name: String,
    pub d_statistic: f64,
    pub p_value: f64,
    pub significant_at_05: bool,
    pub n: usize,
    pub distribution: String,
}

/// Result from Anderson-Darling test.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AndersonDarlingResult {
    pub test_name: String,
    pub statistic: f64,
    pub critical_values: std::collections::HashMap<String, f64>,
    pub p_value_approx: f64,
    pub significant_at_05: bool,
    pub n: usize,
    pub distribution: String,
}

/// Result from LOESS regression.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LOESSResult {
    pub x_eval: Vec<f64>,
    pub y_eval: Vec<f64>,
    pub r_squared: f64,
    pub span: f64,
    pub degree: usize,
    pub n_points: usize,
}

/// Result from BCa bootstrap.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BootstrapBCaResult {
    pub estimate: f64,
    pub bca_ci_lower: f64,
    pub bca_ci_upper: f64,
    pub percentile_ci_lower: f64,
    pub percentile_ci_upper: f64,
    pub confidence: f64,
    pub bootstrap_se: f64,
    pub bias_correction: f64,
    pub acceleration: f64,
    pub n_bootstrap: usize,
    pub n_observations: usize,
}

/// Result from spline regression.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SplineResult {
    pub x_eval: Vec<f64>,
    pub y_eval: Vec<f64>,
    pub r_squared: f64,
    pub n_knots: usize,
    pub effective_df: f64,
    pub gcv_score: f64,
    pub aic: f64,
}
