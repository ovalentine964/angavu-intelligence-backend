// credit/shap_explainer.rs
//
// KernelSHAP Approximation for Credit Score Explainability
//
// Replaces hand-crafted ScoreFactor heuristics with computed Shapley values.
// EU AI Act (enforced 2026) requires "meaningful explanations" for AI credit decisions.
//
// Mathematical Foundation:
//   Shapley values: φᵢ = Σ_{S⊆N\{i}} |S|!(|N|-|S|-1)!/|N|! × [f(S∪{i}) - f(S)]
//   KernelSHAP approximation uses a weighted linear regression on coalitions.
//
// For logistic regression, we exploit the model structure:
//   P(Y=1|X) = σ(β₀ + Σ βᵢxᵢ)
//   The Shapley value for feature i is approximately: φᵢ ≈ βᵢ × (xᵢ - x̄ᵢ)
//   where x̄ᵢ is the background/reference value for feature i.
//
// This is exact for linear models (no interaction terms), making KernelSHAP
// unnecessary in practice — but we implement the general KernelSHAP path
// as a fallback for non-linear model extensions.
//
// Reference: Lundberg & Lee (2017), "A Unified Approach to Interpreting Model Predictions"

use super::logistic_regression::LogisticRegression;
use super::score_fusion::ScoreFactor;
use serde::{Deserialize, Serialize};

/// Explanation for a single credit score computation
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CreditExplanation {
    /// The predicted probability (raw score)
    pub predicted_probability: f64,
    /// Base value (mean prediction across background dataset)
    pub base_value: f64,
    /// Shapley values per feature
    pub shapley_values: Vec<ShapleyValue>,
    /// Human-readable top factors (sorted by |impact| descending)
    pub top_factors: Vec<ScoreFactor>,
    /// Total absolute Shapley sum (should ≈ |prediction - base_value|)
    pub shapley_sum: f64,
    /// Whether linear approximation was used (exact for logistic regression)
    pub linear_approximation: bool,
    /// Explanation generation timestamp (Unix seconds)
    pub computed_at: u64,
    /// Model version / feature set identifier
    pub model_version: String,
}

/// A single feature's Shapley value contribution
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ShapleyValue {
    /// Feature name (e.g., "transaction_volume")
    pub feature_name: String,
    /// Feature value for this observation
    pub feature_value: f64,
    /// Shapley value (contribution to prediction vs base)
    pub shapley_value: f64,
    /// Absolute contribution (for ranking)
    pub abs_contribution: f64,
    /// Direction: "positive" (improves score) or "negative" (reduces score)
    pub direction: String,
    /// Human-readable description
    pub description: String,
}

/// Background dataset statistics for computing reference values
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BackgroundStats {
    /// Mean feature values across training population
    pub mean_features: Vec<f64>,
    /// Feature standard deviations
    pub std_features: Vec<f64>,
    /// Number of observations in background
    pub n_observations: usize,
    /// Mean prediction across background
    pub mean_prediction: f64,
}

/// KernelSHAP configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct KernelShapConfig {
    /// Number of coalition samples for KernelSHAP approximation
    pub n_coalitions: usize,
    /// Use linear approximation (exact for logistic regression)
    pub prefer_linear: bool,
    /// Maximum features to include in explanation
    pub max_features_in_explanation: usize,
    /// Seed for reproducibility
    pub seed: u64,
}

impl Default for KernelShapConfig {
    fn default() -> Self {
        Self {
            n_coalitions: 256,
            prefer_linear: true,
            max_features_in_explanation: 10,
            seed: 42,
        }
    }
}

/// SHAP Explainer for credit scoring models
pub struct ShapExplainer {
    config: KernelShapConfig,
    background: BackgroundStats,
}

impl ShapExplainer {
    /// Create a new SHAP explainer with background statistics
    pub fn new(config: KernelShapConfig, background: BackgroundStats) -> Self {
        Self { config, background }
    }

    /// Compute Shapley values for a single observation.
    ///
    /// For logistic regression (linear model), uses the exact linear formula:
    ///   φᵢ = βᵢ × (xᵢ - x̄ᵢ)
    ///
    /// This is mathematically exact because logistic regression has no
    /// feature interaction terms (the log-odds is a linear function).
    pub fn explain(
        &self,
        model: &LogisticRegression,
        features: &[f64],
        feature_names: &[String],
    ) -> CreditExplanation {
        assert_eq!(
            features.len(),
            model.coefficients.len(),
            "Feature count mismatch"
        );
        assert_eq!(
            features.len(),
            feature_names.len(),
            "Feature names count mismatch"
        );

        let predicted = model.predict_probability(features);

        if self.config.prefer_linear {
            self.explain_linear(model, features, feature_names, predicted)
        } else {
            self.explain_kernel_shap(model, features, feature_names, predicted)
        }
    }

    /// Exact Shapley values for linear models.
    /// φᵢ = βᵢ × (xᵢ - x̄ᵢ)
    fn explain_linear(
        &self,
        model: &LogisticRegression,
        features: &[f64],
        feature_names: &[String],
        predicted: f64,
    ) -> CreditExplanation {
        let base_value = self.background.mean_prediction;
        let mut shapley_values: Vec<ShapleyValue> = features
            .iter()
            .zip(model.coefficients.iter())
            .zip(feature_names.iter())
            .zip(self.background.mean_features.iter())
            .map(|(((x_i, beta_i), name), x_bar_i)| {
                // Linear Shapley: contribution = βᵢ × (xᵢ - x̄ᵢ)
                let shap = beta_i * (x_i - x_bar_i);
                let direction = if shap >= 0.0 { "positive" } else { "negative" };

                ShapleyValue {
                    feature_name: name.clone(),
                    feature_value: *x_i,
                    shapley_value: shap,
                    abs_contribution: shap.abs(),
                    direction: direction.to_string(),
                    description: self.describe_feature(name, *x_i, shap, *x_bar_i),
                }
            })
            .collect();

        // Sort by absolute contribution descending
        shapley_values.sort_by(|a, b| {
            b.abs_contribution
                .partial_cmp(&a.abs_contribution)
                .unwrap_or(std::cmp::Ordering::Equal)
        });

        let shapley_sum: f64 = shapley_values.iter().map(|sv| sv.shapley_value).sum();

        // Convert to ScoreFactor format for backward compatibility
        let top_factors: Vec<ScoreFactor> = shapley_values
            .iter()
            .take(self.config.max_features_in_explanation)
            .map(|sv| ScoreFactor {
                name: sv.feature_name.clone(),
                impact: sv.shapley_value,
                weight: sv.abs_contribution / shapley_sum.abs().max(1e-10),
                description: sv.description.clone(),
            })
            .collect();

        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs();

        CreditExplanation {
            predicted_probability: predicted,
            base_value,
            shapley_values,
            top_factors,
            shapley_sum,
            linear_approximation: true,
            computed_at: now,
            model_version: format!("logistic_regression_{}features", features.len()),
        }
    }

    /// KernelSHAP approximation for non-linear models.
    ///
    /// Samples coalitions and fits a weighted linear model:
    ///   minimize Σ π(zₛ) × (f(zₛ) - φᵀzₛ)²
    /// where zₛ is the binary coalition vector and π(zₛ) is the SHAP kernel weight.
    fn explain_kernel_shap(
        &self,
        model: &LogisticRegression,
        features: &[f64],
        feature_names: &[String],
        predicted: f64,
    ) -> CreditExplanation {
        let n_features = features.len();
        let base_value = self.background.mean_prediction;
        let n_coalitions = self.config.n_coalitions.min(1 << n_features.min(20));

        // Generate coalition samples using quasi-random approach
        let coalitions = self.sample_coalitions(n_features, n_coalitions);

        // Evaluate model on each coalition
        // For coalition S: replace features not in S with background values
        let mut coalition_outputs = Vec::with_capacity(coalitions.len());
        let mut coalition_weights = Vec::with_capacity(coalitions.len());

        for coalition in &coalitions {
            let mut masked_features = features.to_vec();
            for (j, &in_coalition) in coalition.iter().enumerate() {
                if in_coalition == 0 && j < self.background.mean_features.len() {
                    masked_features[j] = self.background.mean_features[j];
                }
            }
            let output = model.predict_probability(&masked_features);
            coalition_outputs.push(output);

            // SHAP kernel weight: π(z) = (M-1) / (C(M,|z|) × |z| × (M-|z|))
            let k: usize = coalition.iter().map(|&v| v as usize).sum();
            let weight = shap_kernel_weight(n_features, k);
            coalition_weights.push(weight);
        }

        // Fit weighted linear regression: coalition_outputs ≈ φ₀ + Σ φᵢ × zᵢ
        let shapley_coeffs =
            weighted_linear_regression(&coalitions, &coalition_outputs, &coalition_weights);

        let mut shapley_values: Vec<ShapleyValue> = (0..n_features)
            .map(|i| {
                let shap = shapley_coeffs.get(i + 1).copied().unwrap_or(0.0);
                let direction = if shap >= 0.0 { "positive" } else { "negative" };
                ShapleyValue {
                    feature_name: feature_names
                        .get(i)
                        .cloned()
                        .unwrap_or_else(|| format!("feature_{}", i)),
                    feature_value: features[i],
                    shapley_value: shap,
                    abs_contribution: shap.abs(),
                    direction: direction.to_string(),
                    description: self.describe_feature(
                        feature_names
                            .get(i)
                            .map(|s| s.as_str())
                            .unwrap_or("unknown"),
                        features[i],
                        shap,
                        self.background.mean_features.get(i).copied().unwrap_or(0.0),
                    ),
                }
            })
            .collect();

        shapley_values.sort_by(|a, b| {
            b.abs_contribution
                .partial_cmp(&a.abs_contribution)
                .unwrap_or(std::cmp::Ordering::Equal)
        });

        let shapley_sum: f64 = shapley_values.iter().map(|sv| sv.shapley_value).sum();

        let top_factors: Vec<ScoreFactor> = shapley_values
            .iter()
            .take(self.config.max_features_in_explanation)
            .map(|sv| ScoreFactor {
                name: sv.feature_name.clone(),
                impact: sv.shapley_value,
                weight: sv.abs_contribution / shapley_sum.abs().max(1e-10),
                description: sv.description.clone(),
            })
            .collect();

        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs();

        CreditExplanation {
            predicted_probability: predicted,
            base_value,
            shapley_values,
            top_factors,
            shapley_sum,
            linear_approximation: false,
            computed_at: now,
            model_version: format!("logistic_regression_{}features_kernelshap", features.len()),
        }
    }

    /// Generate human-readable description for a feature contribution
    fn describe_feature(&self, name: &str, value: f64, shap: f64, background_mean: f64) -> String {
        let direction = if shap > 0.0 { "increases" } else { "decreases" };
        let comparison = if value > background_mean {
            "above average"
        } else if value < background_mean {
            "below average"
        } else {
            "at average"
        };

        match name {
            "transaction_volume" => format!(
                "Transaction volume ({:.2}, {}) {} your credit score by {:.3}",
                value,
                comparison,
                direction,
                shap.abs()
            ),
            "active_days_ratio" => format!(
                "Active days ratio ({:.0}%, {}) {} your credit score by {:.3}",
                value * 100.0,
                comparison,
                direction,
                shap.abs()
            ),
            "revenue_stability" => format!(
                "Revenue stability ({:.0}%, {}) {} your credit score by {:.3}",
                value * 100.0,
                comparison,
                direction,
                shap.abs()
            ),
            "product_diversity" => format!(
                "Product diversity ({:.0}, {}) {} your credit score by {:.3}",
                value,
                comparison,
                direction,
                shap.abs()
            ),
            "income_consistency" => format!(
                "Income consistency ({:.0}%, {}) {} your credit score by {:.3}",
                value * 100.0,
                comparison,
                direction,
                shap.abs()
            ),
            "repayment_history" => format!(
                "Repayment history ({:.0}, {}) {} your credit score by {:.3}",
                value,
                comparison,
                direction,
                shap.abs()
            ),
            "loan_count" => format!(
                "Active loans ({:.0}, {}) {} your credit score by {:.3}",
                value,
                comparison,
                direction,
                shap.abs()
            ),
            "recency" => format!(
                "Transaction recency ({:.0}%, {}) {} your credit score by {:.3}",
                value * 100.0,
                comparison,
                direction,
                shap.abs()
            ),
            "region_economic_index" => format!(
                "Regional economic index ({:.2}, {}) {} your credit score by {:.3}",
                value,
                comparison,
                direction,
                shap.abs()
            ),
            "income_trajectory" => format!(
                "Income trajectory ({:.2}, {}) {} your credit score by {:.3}",
                value,
                comparison,
                direction,
                shap.abs()
            ),
            _ => format!(
                "{} ({:.3}, {}) {} your credit score by {:.3}",
                name,
                value,
                comparison,
                direction,
                shap.abs()
            ),
        }
    }

    /// Sample coalitions for KernelSHAP using quasi-random approach.
    /// Returns a vector of binary vectors (1 = feature present, 0 = masked).
    fn sample_coalitions(&self, n_features: usize, n_coalitions: usize) -> Vec<Vec<u8>> {
        let mut rng_state = self.config.seed;
        let mut coalitions = Vec::with_capacity(n_coalitions);

        // Always include empty and full coalitions
        coalitions.push(vec![0u8; n_features]);
        coalitions.push(vec![1u8; n_features]);

        // Generate random coalitions with stratified sampling by size
        for _ in 2..n_coalitions {
            let coalition: Vec<u8> = (0..n_features)
                .map(|_| {
                    rng_state = rng_state
                        .wrapping_mul(6364136223846793005)
                        .wrapping_add(1442695040888963407);
                    if (rng_state >> 63) & 1 == 1 {
                        1u8
                    } else {
                        0u8
                    }
                })
                .collect();

            // Skip if all zeros or all ones (already included)
            let sum: u8 = coalition.iter().sum();
            if sum > 0 && sum < n_features as u8 {
                coalitions.push(coalition);
            }
        }

        coalitions
    }
}

/// SHAP kernel weight: π(z) = (M-1) / (C(M, |z|) × |z| × (M - |z|))
/// where M = total features, |z| = number of features in coalition
fn shap_kernel_weight(m: usize, k: usize) -> f64 {
    if k == 0 || k == m {
        return 1e6; // large weight for boundary coalitions
    }
    let m_f = m as f64;
    let k_f = k as f64;
    let binom = binomial_coefficient(m, k);
    (m_f - 1.0) / (binom * k_f * (m_f - k_f))
}

/// Binomial coefficient C(n, k) with overflow protection
fn binomial_coefficient(n: usize, k: usize) -> f64 {
    if k > n {
        return 0.0;
    }
    if k == 0 || k == n {
        return 1.0;
    }
    let k = k.min(n - k);
    let mut result = 1.0_f64;
    for i in 0..k {
        result *= (n - i) as f64;
        result /= (i + 1) as f64;
    }
    result
}

/// Weighted least squares regression for KernelSHAP.
/// Solves: minimize Σ wᵢ(yᵢ - xᵢᵀβ)²
/// Returns coefficients [intercept, φ₁, φ₂, ..., φₚ]
fn weighted_linear_regression(X: &[Vec<u8>], y: &[f64], weights: &[f64]) -> Vec<f64> {
    let n = X.len();
    if n == 0 {
        return Vec::new();
    }
    let p = X[0].len();
    let p_full = p + 1; // +1 for intercept

    // Build XᵀWX and XᵀWy
    let mut xtwx = vec![vec![0.0f64; p_full]; p_full];
    let mut xtwy = vec![0.0f64; p_full];

    for i in 0..n {
        let wi = weights[i];
        let yi = y[i];

        // Row: [1, xᵢ₁, xᵢ₂, ..., xᵢₚ]
        let mut row = Vec::with_capacity(p_full);
        row.push(1.0);
        row.extend(X[i].iter().map(|&v| v as f64));

        for j in 0..p_full {
            xtwy[j] += wi * row[j] * yi;
            for k in 0..p_full {
                xtwx[j][k] += wi * row[j] * row[k];
            }
        }
    }

    // Add small regularization for numerical stability
    for j in 0..p_full {
        xtwx[j][j] += 1e-8;
    }

    // Solve via Cholesky
    match cholesky_solve(&xtwx, &xtwy) {
        Ok(x) => x,
        Err(_) => vec![0.0; p_full],
    }
}

/// Cholesky decomposition solve (reused from logistic_regression.rs)
fn cholesky_solve(A: &[Vec<f64>], b: &[f64]) -> Result<Vec<f64>, String> {
    let n = A.len();
    let mut L = vec![vec![0.0f64; n]; n];

    for i in 0..n {
        for j in 0..=i {
            if i == j {
                let mut sum = 0.0;
                for k in 0..j {
                    sum += L[j][k].powi(2);
                }
                let diag = A[j][j] - sum;
                if diag <= 1e-12 {
                    return Err(format!("Matrix not positive definite at row {}", j));
                }
                L[j][j] = diag.sqrt();
            } else {
                let mut sum = 0.0;
                for k in 0..j {
                    sum += L[i][k] * L[j][k];
                }
                L[i][j] = (A[i][j] - sum) / L[j][j];
            }
        }
    }

    let mut y = vec![0.0f64; n];
    for i in 0..n {
        let mut sum = 0.0;
        for j in 0..i {
            sum += L[i][j] * y[j];
        }
        y[i] = (b[i] - sum) / L[i][i];
    }

    let mut x = vec![0.0f64; n];
    for i in (0..n).rev() {
        let mut sum = 0.0;
        for j in (i + 1)..n {
            sum += L[j][i] * x[j];
        }
        x[i] = (y[i] - sum) / L[i][i];
    }

    Ok(x)
}

/// Build background statistics from training data.
/// Call this once after model training.
pub fn compute_background_stats(X: &[Vec<f64>], model: &LogisticRegression) -> BackgroundStats {
    let n = X.len() as f64;
    let p = X[0].len();

    let mean_features: Vec<f64> = (0..p)
        .map(|j| X.iter().map(|x| x[j]).sum::<f64>() / n)
        .collect();

    let std_features: Vec<f64> = (0..p)
        .map(|j| {
            let mean = mean_features[j];
            let variance = X.iter().map(|x| (x[j] - mean).powi(2)).sum::<f64>() / n;
            variance.sqrt()
        })
        .collect();

    let mean_prediction = X.iter().map(|x| model.predict_probability(x)).sum::<f64>() / n;

    BackgroundStats {
        mean_features,
        std_features,
        n_observations: X.len(),
        mean_prediction,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_test_model() -> LogisticRegression {
        let mut model = LogisticRegression::new(3);
        model.coefficients = vec![1.5, -0.8, 0.5];
        model.intercept = -0.2;
        model.trained = true;
        model
    }

    fn make_background() -> BackgroundStats {
        BackgroundStats {
            mean_features: vec![0.5, 0.6, 0.4],
            std_features: vec![0.2, 0.15, 0.3],
            n_observations: 100,
            mean_prediction: 0.45,
        }
    }

    #[test]
    fn test_linear_shap_exact() {
        let model = make_test_model();
        let background = make_background();
        let config = KernelShapConfig {
            prefer_linear: true,
            ..Default::default()
        };
        let explainer = ShapExplainer::new(config, background.clone());

        let features = vec![0.8, 0.3, 0.9];
        let names = vec![
            "transaction_volume".to_string(),
            "active_days_ratio".to_string(),
            "revenue_stability".to_string(),
        ];

        let explanation = explainer.explain(&model, &features, &names);

        // Verify Shapley values are exact for linear model
        // φ₁ = β₁ × (x₁ - x̄₁) = 1.5 × (0.8 - 0.5) = 0.45
        // φ₂ = β₂ × (x₂ - x̄₂) = -0.8 × (0.3 - 0.6) = 0.24
        // φ₃ = β₃ × (x₃ - x̄₃) = 0.5 × (0.9 - 0.4) = 0.25
        let sv_map: std::collections::HashMap<String, f64> = explanation
            .shapley_values
            .iter()
            .map(|sv| (sv.feature_name.clone(), sv.shapley_value))
            .collect();

        assert!((sv_map["transaction_volume"] - 0.45).abs() < 1e-10);
        assert!((sv_map["active_days_ratio"] - 0.24).abs() < 1e-10);
        assert!((sv_map["revenue_stability"] - 0.25).abs() < 1e-10);
        assert!(explanation.linear_approximation);
    }

    #[test]
    fn test_shapley_sum_approximates_prediction_minus_base() {
        let model = make_test_model();
        let background = make_background();
        let config = KernelShapConfig::default();
        let explainer = ShapExplainer::new(config, background.clone());

        let features = vec![0.8, 0.3, 0.9];
        let names = vec!["f1".to_string(), "f2".to_string(), "f3".to_string()];

        let explanation = explainer.explain(&model, &features, &names);

        // For linear models: base_value + Σφᵢ should ≈ predicted
        let reconstructed = explanation.base_value + explanation.shapley_sum;
        assert!(
            (reconstructed - explanation.predicted_probability).abs() < 1e-6,
            "SHAP sum should reconstruct prediction: base={} + sum={} ≈ pred={}, diff={}",
            explanation.base_value,
            explanation.shapley_sum,
            explanation.predicted_probability,
            (reconstructed - explanation.predicted_probability).abs()
        );
    }

    #[test]
    fn test_kernel_shap_runs() {
        let model = make_test_model();
        let background = make_background();
        let config = KernelShapConfig {
            prefer_linear: false,
            n_coalitions: 64,
            ..Default::default()
        };
        let explainer = ShapExplainer::new(config, background);

        let features = vec![0.8, 0.3, 0.9];
        let names = vec!["f1".to_string(), "f2".to_string(), "f3".to_string()];

        let explanation = explainer.explain(&model, &features, &names);
        assert!(!explanation.linear_approximation);
        assert_eq!(explanation.shapley_values.len(), 3);
    }

    #[test]
    fn test_background_stats() {
        let X = vec![
            vec![1.0, 2.0, 3.0],
            vec![3.0, 4.0, 5.0],
            vec![2.0, 3.0, 4.0],
        ];
        let model = make_test_model();
        let bg = compute_background_stats(&X, &model);

        assert_eq!(bg.n_observations, 3);
        assert!((bg.mean_features[0] - 2.0).abs() < 1e-10);
        assert!((bg.mean_features[1] - 3.0).abs() < 1e-10);
        assert!((bg.mean_features[2] - 4.0).abs() < 1e-10);
    }

    #[test]
    fn test_binomial_coefficient() {
        assert_eq!(binomial_coefficient(5, 0), 1.0);
        assert_eq!(binomial_coefficient(5, 5), 1.0);
        assert_eq!(binomial_coefficient(5, 2), 10.0);
        assert_eq!(binomial_coefficient(10, 3), 120.0);
    }
}
