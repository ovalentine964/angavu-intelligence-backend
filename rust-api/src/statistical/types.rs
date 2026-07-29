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
