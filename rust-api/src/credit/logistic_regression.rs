// credit/logistic_regression.rs
//
// Logistic Regression via Iteratively Reweighted Least Squares (IRLS)
// Replaces the broken `mean(feature_vector)` credit scoring with a proper MLE model.
//
// Mathematical Foundation:
//   P(Y=1|X) = σ(Xβ) = 1 / (1 + exp(-Xβ))
//   Log-likelihood: ℓ(β) = Σ[yᵢ log(pᵢ) + (1-yᵢ) log(1-pᵢ)]
//   Score: ∂ℓ/∂β = Xᵀ(y - p)
//   Hessian: ∂²ℓ/∂β² = -XᵀWX  where W = diag(pᵢ(1-pᵢ))
//   IRLS update: β⁽ᵗ⁺¹⁾ = β⁽ᵗ⁾ + (XᵀW⁽ᵗ⁾X)⁻¹ Xᵀ(y - p⁽ᵗ⁾)
//
// Reference: McCullagh & Nelder (1989), Generalized Linear Models

use serde::{Deserialize, Serialize};

/// Logistic regression model trained via IRLS (Iteratively Reweighted Least Squares)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LogisticRegression {
    /// Feature coefficients (β₁, β₂, ..., βₚ)
    pub coefficients: Vec<f64>,
    /// Intercept (β₀)
    pub intercept: f64,
    /// Whether the model has been trained
    pub trained: bool,
    /// Training metrics
    pub training_metrics: Option<TrainingMetrics>,
    /// Feature names for interpretability
    pub feature_names: Vec<String>,
}

/// Model training metrics
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TrainingMetrics {
    /// Final log-likelihood
    pub log_likelihood: f64,
    /// Number of IRLS iterations
    pub iterations: usize,
    /// Whether IRLS converged
    pub converged: bool,
    /// AIC = -2ℓ + 2k
    pub aic: f64,
    /// BIC = -2ℓ + k·ln(n)
    pub bic: f64,
    /// Pseudo R² (McFadden): 1 - ℓ_model / ℓ_null
    pub pseudo_r_squared: f64,
    /// AUC-ROC (on training set — use cross-validation for real evaluation)
    pub auc_roc: f64,
    /// Hosmer-Lemeshow test p-value (goodness of fit)
    pub hosmer_lemeshow_p: f64,
    /// Confusion matrix at threshold 0.5
    pub confusion_matrix: ConfusionMatrix,
}

/// Confusion matrix
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConfusionMatrix {
    pub true_positives: u32,
    pub true_negatives: u32,
    pub false_positives: u32,
    pub false_negatives: u32,
    pub precision: f64,
    pub recall: f64,
    pub f1_score: f64,
    pub accuracy: f64,
}

/// Cross-validation result
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CrossValidationResult {
    /// Mean AUC-ROC across folds
    pub mean_auc_roc: f64,
    /// Std of AUC-ROC across folds
    pub std_auc_roc: f64,
    /// Per-fold AUC-ROC scores
    pub fold_scores: Vec<f64>,
    /// Number of folds
    pub n_folds: usize,
    /// Mean precision across folds
    pub mean_precision: f64,
    /// Mean recall across folds
    pub mean_recall: f64,
}

/// Model evaluation on held-out test set
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModelEvaluation {
    pub auc_roc: f64,
    pub confusion_matrix: ConfusionMatrix,
    /// ROC curve points (fpr, tpr)
    pub roc_curve: Vec<(f64, f64)>,
    /// Odds ratios for each feature: exp(βᵢ)
    pub odds_ratios: Vec<f64>,
    /// Marginal effects at means: βᵢ × p̄ × (1 - p̄)
    pub marginal_effects: Vec<f64>,
}

impl LogisticRegression {
    /// Create an untrained model with p features
    pub fn new(n_features: usize) -> Self {
        Self {
            coefficients: vec![0.0; n_features],
            intercept: 0.0,
            trained: false,
            training_metrics: None,
            feature_names: (0..n_features).map(|i| format!("feature_{}", i)).collect(),
        }
    }

    /// Create model with named features
    pub fn with_feature_names(feature_names: Vec<String>) -> Self {
        let n = feature_names.len();
        Self {
            coefficients: vec![0.0; n],
            intercept: 0.0,
            trained: false,
            training_metrics: None,
            feature_names,
        }
    }

    /// Sigmoid function σ(z) = 1 / (1 + exp(-z))
    /// Clamped to avoid overflow
    pub fn sigmoid(z: f64) -> f64 {
        if z >= 0.0 {
            let exp_neg_z = (-z).exp();
            1.0 / (1.0 + exp_neg_z)
        } else {
            let exp_z = z.exp();
            exp_z / (1.0 + exp_z)
        }
    }

    /// Predict probability P(Y=1|X) for a single observation
    pub fn predict_probability(&self, features: &[f64]) -> f64 {
        assert_eq!(features.len(), self.coefficients.len(), "Feature count mismatch");
        let z = self.intercept + features.iter()
            .zip(self.coefficients.iter())
            .map(|(x, b)| x * b)
            .sum::<f64>();
        Self::sigmoid(z)
    }

    /// Predict binary outcome (0 or 1) at given threshold
    pub fn predict(&self, features: &[f64], threshold: f64) -> u8 {
        if self.predict_probability(features) >= threshold { 1 } else { 0 }
    }

    /// Predict probabilities for a batch
    pub fn predict_batch(&self, X: &[Vec<f64>]) -> Vec<f64> {
        X.iter().map(|x| self.predict_probability(x)).collect()
    }

    /// Train using IRLS (Iteratively Reweighted Least Squares)
    ///
    /// # Arguments
    /// * `X` - Feature matrix (n × p), each row is an observation
    /// * `y` - Binary outcome vector (0 or 1)
    /// * `max_iterations` - Maximum IRLS iterations
    /// * `tolerance` - Convergence tolerance on coefficient change
    /// * `l2_penalty` - L2 regularization strength (0 = no regularization)
    ///
    /// # Returns
    /// Trained model with metrics
    pub fn fit(
        X: &[Vec<f64>],
        y: &[u8],
        max_iterations: usize,
        tolerance: f64,
        l2_penalty: f64,
    ) -> Result<Self, String> {
        let n = X.len();
        if n == 0 {
            return Err("Empty training data".to_string());
        }
        if n != y.len() {
            return Err(format!("X has {} rows but y has {} elements", n, y.len()));
        }

        let p = X[0].len();
        for (i, row) in X.iter().enumerate() {
            if row.len() != p {
                return Err(format!("Row {} has {} features, expected {}", i, row.len(), p));
            }
        }

        // Check for separation (perfect or quasi-complete)
        let y_sum: f64 = y.iter().map(|&v| v as f64).sum();
        if y_sum == 0.0 || y_sum == n as f64 {
            return Err("Perfect separation: all outcomes are the same class".to_string());
        }

        // Initialize coefficients to zero
        let mut beta = vec![0.0f64; p];
        let mut intercept = 0.0f64;

        let n_f = n as f64;
        let mut converged = false;
        let mut iterations = 0;

        for iter in 0..max_iterations {
            iterations = iter + 1;

            // Compute predicted probabilities
            let probs: Vec<f64> = X.iter().map(|x| {
                let z = intercept + x.iter().zip(beta.iter()).map(|(xi, bi)| xi * bi).sum::<f64>();
                Self::sigmoid(z)
            }).collect();

            // Compute working weights and working response
            // W = diag(pᵢ(1-pᵢ)), z = Xβ + (y-p) / (p(1-p))
            let mut weights = Vec::with_capacity(n);
            let mut working_response = Vec::with_capacity(n);

            for i in 0..n {
                let pi = probs[i].clamp(1e-10, 1.0 - 1e-10);
                let wi = pi * (1.0 - pi);
                weights.push(wi);
                let eta = intercept + X[i].iter().zip(beta.iter()).map(|(x, b)| x * b).sum::<f64>();
                working_response.push(eta + (y[i] as f64 - pi) / wi);
            }

            // Solve weighted least squares: (XᵀWX + λI)β_new = XᵀWz
            // Build X̃ = [1 | X] (add intercept column)
            let p_full = p + 1;

            // Compute XᵀWX and XᵀWz
            let mut xtwx = vec![vec![0.0f64; p_full]; p_full];
            let mut xtwz = vec![0.0f64; p_full];

            for i in 0..n {
                let wi = weights[i];
                let zi = working_response[i];

                // Row: [1, xᵢ₁, xᵢ₂, ..., xᵢₚ]
                let mut row = Vec::with_capacity(p_full);
                row.push(1.0);
                row.extend_from_slice(&X[i]);

                for j in 0..p_full {
                    xtwz[j] += wi * row[j] * zi;
                    for k in 0..p_full {
                        xtwx[j][k] += wi * row[j] * row[k];
                    }
                }
            }

            // Add L2 regularization (don't penalize intercept)
            for j in 1..p_full {
                xtwx[j][j] += l2_penalty;
            }

            // Solve via Cholesky decomposition
            let solution = cholesky_solve(&xtwx, &xtwz)?;

            // Update coefficients
            let new_intercept = solution[0];
            let new_beta: Vec<f64> = solution[1..].to_vec();

            // Check convergence
            let delta_intercept = (new_intercept - intercept).abs();
            let delta_beta: f64 = new_beta.iter().zip(beta.iter())
                .map(|(nb, ob)| (nb - ob).abs())
                .sum();

            intercept = new_intercept;
            beta = new_beta;

            if delta_intercept + delta_beta < tolerance {
                converged = true;
                break;
            }
        }

        // Compute final metrics
        let probs: Vec<f64> = X.iter().map(|x| {
            let z = intercept + x.iter().zip(beta.iter()).map(|(xi, bi)| xi * bi).sum::<f64>();
            Self::sigmoid(z)
        }).collect();

        // Log-likelihood
        let log_likelihood: f64 = y.iter().zip(probs.iter()).map(|(&yi, &pi)| {
            let pi = pi.clamp(1e-10, 1.0 - 1e-10);
            yi as f64 * pi.ln() + (1.0 - yi as f64) * (1.0 - pi).ln()
        }).sum();

        // Null model log-likelihood (intercept only)
        let p_bar = y_sum / n_f;
        let null_ll: f64 = y.iter().map(|&yi| {
            yi as f64 * p_bar.ln() + (1.0 - yi as f64) * (1.0 - p_bar).ln()
        }).sum();

        let k = (p + 1) as f64;
        let aic = -2.0 * log_likelihood + 2.0 * k;
        let bic = -2.0 * log_likelihood + k * n_f.ln();
        let pseudo_r_squared = 1.0 - log_likelihood / null_ll;

        // Confusion matrix
        let confusion = Self::compute_confusion_matrix(y, &probs, 0.5);

        // AUC-ROC
        let auc_roc = Self::compute_auc_roc(y, &probs);

        // Hosmer-Lemeshow test
        let hl_p = Self::hosmer_lemeshow_test(y, &probs, 10);

        let metrics = TrainingMetrics {
            log_likelihood,
            iterations,
            converged,
            aic,
            bic,
            pseudo_r_squared,
            auc_roc,
            hosmer_lemeshow_p: hl_p,
            confusion_matrix: confusion,
        };

        Ok(Self {
            coefficients: beta,
            intercept,
            trained: true,
            training_metrics: Some(metrics),
            feature_names: if X[0].len() == p {
                (0..p).map(|i| format!("feature_{}", i)).collect()
            } else {
                vec!["unknown".to_string(); p]
            },
        })
    }

    /// K-fold cross-validation for model evaluation
    pub fn cross_validate(
        X: &[Vec<f64>],
        y: &[u8],
        n_folds: usize,
        max_iterations: usize,
        tolerance: f64,
        l2_penalty: f64,
    ) -> Result<CrossValidationResult, String> {
        let n = X.len();
        if n < n_folds {
            return Err(format!("Need at least {} samples for {}-fold CV", n_folds, n_folds));
        }

        let fold_size = n / n_folds;
        let mut fold_aucs = Vec::with_capacity(n_folds);
        let mut fold_precisions = Vec::with_capacity(n_folds);
        let mut fold_recalls = Vec::with_capacity(n_folds);

        for fold in 0..n_folds {
            let test_start = fold * fold_size;
            let test_end = if fold == n_folds - 1 { n } else { test_start + fold_size };

            // Split into train/test
            let mut X_train = Vec::with_capacity(n - (test_end - test_start));
            let mut y_train = Vec::with_capacity(n - (test_end - test_start));
            let mut X_test = Vec::with_capacity(test_end - test_start);
            let mut y_test = Vec::with_capacity(test_end - test_start);

            for i in 0..n {
                if i >= test_start && i < test_end {
                    X_test.push(X[i].clone());
                    y_test.push(y[i]);
                } else {
                    X_train.push(X[i].clone());
                    y_train.push(y[i]);
                }
            }

            // Train on fold
            let model = Self::fit(&X_train, &y_train, max_iterations, tolerance, l2_penalty)?;
            let probs = model.predict_batch(&X_test);

            let auc = Self::compute_auc_roc(&y_test, &probs);
            let cm = Self::compute_confusion_matrix(&y_test, &probs, 0.5);

            fold_aucs.push(auc);
            fold_precisions.push(cm.precision);
            fold_recalls.push(cm.recall);
        }

        let mean_auc = fold_aucs.iter().sum::<f64>() / n_folds as f64;
        let var_auc = fold_aucs.iter().map(|a| (a - mean_auc).powi(2)).sum::<f64>() / n_folds as f64;
        let mean_prec = fold_precisions.iter().sum::<f64>() / n_folds as f64;
        let mean_rec = fold_recalls.iter().sum::<f64>() / n_folds as f64;

        Ok(CrossValidationResult {
            mean_auc_roc: mean_auc,
            std_auc_roc: var_auc.sqrt(),
            fold_scores: fold_aucs,
            n_folds,
            mean_precision: mean_prec,
            mean_recall: mean_rec,
        })
    }

    /// Compute AUC-ROC using the trapezoidal rule
    pub fn compute_auc_roc(y_true: &[u8], y_scores: &[f64]) -> f64 {
        let n = y_true.len();
        let n_pos = y_true.iter().filter(|&&v| v == 1).count() as f64;
        let n_neg = n as f64 - n_pos;

        if n_pos == 0.0 || n_neg == 0.0 {
            return 0.5; // undefined
        }

        // Sort by descending score
        let mut indexed: Vec<(f64, u8)> = y_scores.iter().zip(y_true.iter())
            .map(|(&s, &y)| (s, y))
            .collect();
        indexed.sort_by(|a, b| b.0.partial_cmp(&a.0).unwrap());

        let mut auc = 0.0;
        let mut tp = 0.0;
        let mut fp = 0.0;
        let mut prev_tpr = 0.0;
        let mut prev_fpr = 0.0;

        let mut i = 0;
        while i < n {
            let threshold = indexed[i].0;
            // Count all tied scores
            let mut tie_pos = 0.0;
            let mut tie_neg = 0.0;
            while i < n && (indexed[i].0 - threshold).abs() < 1e-10 {
                if indexed[i].1 == 1 { tie_pos += 1.0; } else { tie_neg += 1.0; }
                i += 1;
            }
            tp += tie_pos;
            fp += tie_neg;
            let tpr = tp / n_pos;
            let fpr = fp / n_neg;
            // Trapezoidal rule
            auc += (fpr - prev_fpr) * (tpr + prev_tpr) / 2.0;
            prev_tpr = tpr;
            prev_fpr = fpr;
        }

        auc
    }

    /// Compute confusion matrix at a given threshold
    fn compute_confusion_matrix(y_true: &[u8], probs: &[f64], threshold: f64) -> ConfusionMatrix {
        let mut tp = 0u32;
        let mut tn = 0u32;
        let mut fp = 0u32;
        let mut fn_ = 0u32;

        for (&yi, &pi) in y_true.iter().zip(probs.iter()) {
            let pred = if pi >= threshold { 1 } else { 0 };
            match (yi, pred) {
                (1, 1) => tp += 1,
                (0, 0) => tn += 1,
                (0, 1) => fp += 1,
                (1, 0) => fn_ += 1,
                _ => {}
            }
        }

        let precision = if tp + fp > 0 { tp as f64 / (tp + fp) as f64 } else { 0.0 };
        let recall = if tp + fn_ > 0 { tp as f64 / (tp + fn_) as f64 } else { 0.0 };
        let f1 = if precision + recall > 0.0 { 2.0 * precision * recall / (precision + recall) } else { 0.0 };
        let accuracy = (tp + tn) as f64 / (tp + tn + fp + fn_) as f64;

        ConfusionMatrix {
            true_positives: tp,
            true_negatives: tn,
            false_positives: fp,
            false_negatives: fn_,
            precision,
            recall,
            f1_score: f1,
            accuracy,
        }
    }

    /// Hosmer-Lemeshow goodness-of-fit test
    /// H₀: model fits the data well
    /// Returns p-value (higher = better fit)
    fn hosmer_lemeshow_test(y_true: &[u8], probs: &[f64], n_groups: usize) -> f64 {
        let n = y_true.len();
        if n < n_groups * 2 {
            return 1.0; // insufficient data
        }

        // Sort by predicted probability
        let mut indexed: Vec<(f64, u8)> = probs.iter().zip(y_true.iter())
            .map(|(&p, &y)| (p, y))
            .collect();
        indexed.sort_by(|a, b| a.0.partial_cmp(&b.0).unwrap());

        let group_size = n / n_groups;
        let mut chi_sq = 0.0;

        for g in 0..n_groups {
            let start = g * group_size;
            let end = if g == n_groups - 1 { n } else { start + group_size };
            let group = &indexed[start..end];

            let observed: f64 = group.iter().map(|(_, y)| *y as f64).sum();
            let expected: f64 = group.iter().map(|(p, _)| *p).sum();
            let ng = group.len() as f64;

            if expected > 0.0 && expected < ng {
                chi_sq += (observed - expected).powi(2) / expected;
                chi_sq += ((ng - observed) - (ng - expected)).powi(2) / (ng - expected);
            }
        }

        // p-value from chi-squared distribution with (n_groups - 2) df
        let df = (n_groups - 2) as f64;
        chi_squared_p_value(chi_sq, df)
    }

    /// Compute odds ratios: exp(βᵢ)
    pub fn odds_ratios(&self) -> Vec<f64> {
        self.coefficients.iter().map(|b| b.exp()).collect()
    }

    /// Compute marginal effects at means: βᵢ × p̄ × (1 - p̄)
    pub fn marginal_effects_at_means(&self, X: &[Vec<f64>]) -> Vec<f64> {
        let n = X.len() as f64;
        let p = self.coefficients.len();

        // Compute mean features
        let mean_features: Vec<f64> = (0..p).map(|j| {
            X.iter().map(|x| x[j]).sum::<f64>() / n
        }).collect();

        // Compute p at means
        let p_bar = self.predict_probability(&mean_features);

        // Marginal effect = βᵢ × p̄ × (1 - p̄)
        self.coefficients.iter().map(|b| b * p_bar * (1.0 - p_bar)).collect()
    }

    /// Generate ROC curve points
    pub fn roc_curve(y_true: &[u8], y_scores: &[f64]) -> Vec<(f64, f64)> {
        let n = y_true.len();
        let n_pos = y_true.iter().filter(|&&v| v == 1).count() as f64;
        let n_neg = n as f64 - n_pos;

        if n_pos == 0.0 || n_neg == 0.0 {
            return vec![(0.0, 0.0), (1.0, 1.0)];
        }

        let mut indexed: Vec<(f64, u8)> = y_scores.iter().zip(y_true.iter())
            .map(|(&s, &y)| (s, y))
            .collect();
        indexed.sort_by(|a, b| b.0.partial_cmp(&a.0).unwrap());

        let mut points = vec![(0.0, 0.0)];
        let mut tp = 0.0;
        let mut fp = 0.0;

        let mut i = 0;
        while i < n {
            let threshold = indexed[i].0;
            while i < n && (indexed[i].0 - threshold).abs() < 1e-10 {
                if indexed[i].1 == 1 { tp += 1.0; } else { fp += 1.0; }
                i += 1;
            }
            points.push((fp / n_neg, tp / n_pos));
        }

        points
    }
}

/// Cholesky decomposition solve for Ax = b where A is symmetric positive definite
fn cholesky_solve(A: &[Vec<f64>], b: &[f64]) -> Result<Vec<f64>, String> {
    let n = A.len();
    assert_eq!(A.len(), n);
    assert_eq!(b.len(), n);

    // Cholesky decomposition: A = LLᵀ
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

    // Forward solve: Ly = b
    let mut y = vec![0.0f64; n];
    for i in 0..n {
        let mut sum = 0.0;
        for j in 0..i {
            sum += L[i][j] * y[j];
        }
        y[i] = (b[i] - sum) / L[i][i];
    }

    // Back solve: Lᵀx = y
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

/// Chi-squared p-value approximation (Wilson-Hilferty)
fn chi_squared_p_value(chi_sq: f64, df: f64) -> f64 {
    if df <= 0.0 || chi_sq <= 0.0 {
        return 1.0;
    }
    // Wilson-Hilferty normal approximation
    let z = ((chi_sq / df).powf(1.0 / 3.0) - (1.0 - 2.0 / (9.0 * df)))
        / (2.0 / (9.0 * df)).sqrt();
    // Standard normal survival function
    0.5 * (1.0 - erf(z / std::f64::consts::SQRT_2))
}

/// Error function approximation (Abramowitz and Stegun 7.1.26)
fn erf(x: f64) -> f64 {
    let a1 = 0.254829592;
    let a2 = -0.284496736;
    let a3 = 1.421413741;
    let a4 = -1.453152027;
    let a5 = 1.061405429;
    let p = 0.3275911;

    let sign = if x < 0.0 { -1.0 } else { 1.0 };
    let x = x.abs();
    let t = 1.0 / (1.0 + p * x);
    let y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * (-x * x).exp();
    sign * y
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_sigmoid() {
        assert!((LogisticRegression::sigmoid(0.0) - 0.5).abs() < 1e-10);
        assert!(LogisticRegression::sigmoid(100.0) > 0.99);
        assert!(LogisticRegression::sigmoid(-100.0) < 0.01);
    }

    #[test]
    fn test_fit_basic() {
        let n = 200;
        let mut rng_state = 42u64;
        let mut X = Vec::with_capacity(n);
        let mut y = Vec::with_capacity(n);

        for _ in 0..n {
            let x1 = rand_normal(&mut rng_state);
            let z = -1.0 + 2.0 * x1;
            let p = LogisticRegression::sigmoid(z);
            let yi = if rand_uniform(&mut rng_state) < p { 1u8 } else { 0 };
            X.push(vec![x1]);
            y.push(yi);
        }

        let model = LogisticRegression::fit(&X, &y, 100, 1e-6, 0.0).unwrap();
        assert!(model.trained);
        // Coefficient should be positive (true value is 2.0)
        assert!(model.coefficients[0] > 0.5, "Expected positive coeff, got {}", model.coefficients[0]);
        // Intercept should be negative (true value is -1.0)
        assert!(model.intercept < 0.0, "Expected negative intercept, got {}", model.intercept);
    }

    #[test]
    fn test_auc_roc_perfect_separation() {
        let y = vec![0, 0, 0, 1, 1, 1];
        let scores = vec![0.1, 0.2, 0.3, 0.7, 0.8, 0.9];
        let auc = LogisticRegression::compute_auc_roc(&y, &scores);
        assert!((auc - 1.0).abs() < 0.01, "AUC should be ~1.0, got {}", auc);
    }

    #[test]
    fn test_auc_roc_random() {
        // Random scores should give AUC ~0.5
        let n = 1000;
        let mut rng_state = 123u64;
        let y: Vec<u8> = (0..n).map(|i| if i < n / 2 { 1 } else { 0 }).collect();
        let scores: Vec<f64> = (0..n).map(|_| rand_uniform(&mut rng_state)).collect();
        let auc = LogisticRegression::compute_auc_roc(&y, &scores);
        assert!((auc - 0.5).abs() < 0.1, "AUC should be ~0.5, got {}", auc);
    }

    #[test]
    fn test_cholesky_solve() {
        let A = vec![
            vec![4.0, 2.0],
            vec![2.0, 3.0],
        ];
        let b = vec![6.0, 5.0];
        let x = cholesky_solve(&A, &b).unwrap();
        // 4x + 2y = 6, 2x + 3y = 5 => x=1, y=1
        assert!((x[0] - 1.0).abs() < 1e-10);
        assert!((x[1] - 1.0).abs() < 1e-10);
    }

    // Simple deterministic PRNG for tests
    fn rand_uniform(state: &mut u64) -> f64 {
        *state = state.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
        ((*state >> 33) as f64) / (1u64 << 31) as f64
    }

    fn rand_normal(state: &mut u64) -> f64 {
        let u1 = rand_uniform(state).max(1e-10);
        let u2 = rand_uniform(state);
        (-2.0 * u1.ln()).sqrt() * (2.0 * std::f64::consts::PI * u2).cos()
    }
}
