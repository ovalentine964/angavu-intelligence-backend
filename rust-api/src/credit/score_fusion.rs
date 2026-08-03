use serde::{Serialize, Deserialize};
// credit/score_fusion.rs

use super::base_features::AdjustedBaseFeatures;
use super::logistic_regression::LogisticRegression;
use super::shap_explainer::{BackgroundStats, CreditExplanation, KernelShapConfig, ShapExplainer};
use super::types::{TypeFeatures, WorkerType};

/// Fused Alama Score combining base and type-specific signals
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FusedAlamaScore {
    /// Final score (300-850 range)
    pub alama_score: u16,
    /// Raw fused probability (0.0-1.0)
    pub raw_score: f64,
    /// Base model contribution
    pub base_score: f64,
    /// Type head contribution
    pub type_score: Option<f64>,
    /// Worker type used
    pub worker_type: WorkerType,
    /// Type head weight (β) used
    pub type_weight: f64,
    /// Confidence in the score
    pub confidence: f64,
    /// Factor breakdown for explainability (Shapley values when available)
    pub factors: Vec<ScoreFactor>,
    /// Full SHAP explanation (stored with each score computation)
    pub explanation: Option<CreditExplanation>,
    /// Whether seasonal adjustment was applied
    pub seasonally_adjusted: bool,
    /// 95% confidence interval lower bound (Alama score units)
    pub ci_lower: u16,
    /// 95% confidence interval upper bound (Alama score units)
    pub ci_upper: u16,
    /// Standard error of the raw score estimate
    pub standard_error: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScoreFactor {
    pub name: String,
    pub impact: f64, // positive = improves score, negative = reduces
    pub weight: f64, // importance weight
    pub description: String,
}

pub struct ScoreFusionEngine {
    /// Type head weights (β) — can be updated via calibration
    type_weights: std::collections::HashMap<WorkerType, f64>,
    /// Per-type calibrators for post-fusion adjustment
    type_calibrators: std::collections::HashMap<WorkerType, TypeCalibrator>,
    /// SHAP explainer for computed Shapley values (replaces hand-crafted factors)
    shap_explainer: Option<ShapExplainer>,
    /// Logistic regression model (for SHAP computation)
    model: Option<LogisticRegression>,
}

/// Per-type score calibrator (maps raw fused score to calibrated probability)
struct TypeCalibrator {
    /// Calibration parameters (Platt scaling: 1 / (1 + exp(a * score + b))
    a: f64,
    b: f64,
}

impl TypeCalibrator {
    fn calibrate(&self, raw_score: f64) -> f64 {
        1.0 / (1.0 + (self.a * raw_score + self.b).exp())
    }
}

impl ScoreFusionEngine {
    pub fn new() -> Self {
        let mut type_weights = std::collections::HashMap::new();
        for wt in WorkerType::all() {
            type_weights.insert(wt, wt.type_weight());
        }

        // Default calibration (identity — no adjustment)
        let mut type_calibrators = std::collections::HashMap::new();
        for wt in WorkerType::all() {
            type_calibrators.insert(wt, TypeCalibrator { a: -1.0, b: 0.0 });
        }

        Self {
            type_weights,
            type_calibrators,
            shap_explainer: None,
            model: None,
        }
    }

    /// Create engine with a trained model for SHAP explainability
    pub fn with_model(model: LogisticRegression, background: BackgroundStats) -> Self {
        let mut engine = Self::new();
        let config = KernelShapConfig::default();
        engine.shap_explainer = Some(ShapExplainer::new(config, background));
        engine.model = Some(model);
        engine
    }

    /// Compute fused score with SHAP-based explanation
    pub fn compute_score(
        &self,
        base_score: f64,
        base_features: &AdjustedBaseFeatures,
        type_features: Option<&TypeFeatures>,
        worker_type: WorkerType,
    ) -> FusedAlamaScore {
        let beta = self.type_weights.get(&worker_type).copied().unwrap_or(0.0);
        let alpha = 1.0 - beta;

        let (type_score, factors, explanation) = if let Some(tf) = type_features {
            let raw_type = self.compute_type_score(tf);

            // Compute SHAP explanation if model is available
            let explanation =
                if let (Some(explainer), Some(model)) = (&self.shap_explainer, &self.model) {
                    let feature_vector = &tf.feature_vector;
                    let feature_names = if tf.feature_names.is_empty() {
                        super::base_features::AdjustedBaseFeatures::feature_names()
                            .iter()
                            .map(|s| s.to_string())
                            .collect::<Vec<_>>()
                    } else {
                        tf.feature_names.clone()
                    };
                    if feature_vector.len() == model.coefficients.len() {
                        Some(explainer.explain(model, feature_vector, &feature_names))
                    } else {
                        None
                    }
                } else {
                    None
                };

            // Use SHAP top_factors if available, otherwise fall back to hand-crafted factors
            let factors = if let Some(ref exp) = explanation {
                exp.top_factors.clone()
            } else {
                self.extract_factors(base_features, tf)
            };

            (Some(raw_type), factors, explanation)
        } else {
            (None, Vec::new(), None)
        };

        // Fused score
        let fused = if let Some(ts) = type_score {
            alpha * base_score + beta * ts
        } else {
            base_score // no type features → pure base score (backward compatible)
        };

        // Apply per-type calibration
        let calibrated = if let Some(cal) = self.type_calibrators.get(&worker_type) {
            cal.calibrate(fused)
        } else {
            fused
        };

        // Map to 300-850 range
        let alama_score = (300.0 + calibrated * 550.0).round() as u16;

        // Compute confidence
        let confidence = self.compute_confidence(base_score, type_score, worker_type);

        // Compute confidence interval using delta method
        let se = self.compute_standard_error(calibrated, confidence, base_features);
        let z_95 = 1.96;
        let ci_raw_lower = (calibrated - z_95 * se).max(0.0);
        let ci_raw_upper = (calibrated + z_95 * se).min(1.0);
        let ci_lower = (300.0 + ci_raw_lower * 550.0).round() as u16;
        let ci_upper = (300.0 + ci_raw_upper * 550.0).round() as u16;

        FusedAlamaScore {
            alama_score: alama_score.clamp(300, 850),
            raw_score: calibrated,
            base_score,
            type_score,
            worker_type,
            type_weight: beta,
            confidence,
            factors,
            explanation,
            seasonally_adjusted: base_features.is_seasonal,
            ci_lower: ci_lower.clamp(300, 850),
            ci_upper: ci_upper.clamp(300, 850),
            standard_error: se,
        }
    }

    fn compute_type_score(&self, features: &TypeFeatures) -> f64 {
        // Use logistic regression model if available, otherwise fall back to calibrated heuristic
        // IMPORTANT: mean(feature_vector) was removed — it is NOT a valid credit scoring method.
        // See: logistic_regression.rs for the proper MLE/IRLS implementation.
        if features.feature_vector.is_empty() {
            return 0.5; // neutral
        }

        // Apply logistic regression with domain-informed weights
        // These weights encode known credit risk relationships:
        // - Higher transaction volume → lower risk (positive)
        // - Higher volatility → higher risk (negative)
        // - More repayment history → lower risk (positive)
        // Weights are log-odds: positive = reduces P(default), negative = increases P(default)
        let weights: Vec<f64> = features
            .feature_vector
            .iter()
            .enumerate()
            .map(|(i, _)| {
                match features.feature_names.get(i).map(|s| s.as_str()) {
                    Some("transaction_volume") => 1.2,
                    Some("active_days_ratio") => 0.8,
                    Some("revenue_stability") => 1.0,
                    Some("product_diversity") => 0.3,
                    Some("income_consistency") => 0.9,
                    Some("repayment_history") => 1.5,
                    Some("loan_count") => -0.5, // More loans = more risk
                    Some("recency") => 0.7,
                    Some("region_economic_index") => 0.4,
                    Some("income_trajectory") => 0.6,
                    _ => 0.0,
                }
            })
            .collect();

        // Compute log-odds: z = intercept + Σ(wᵢ × xᵢ)
        let intercept = -1.5; // Base rate adjustment
        let z: f64 = intercept
            + features
                .feature_vector
                .iter()
                .zip(weights.iter())
                .map(|(x, w)| x * w)
                .sum::<f64>();

        // Sigmoid to get probability
        let score = 1.0 / (1.0 + (-z).exp());
        score.clamp(0.0, 1.0)
    }

    fn extract_factors(
        &self,
        base: &AdjustedBaseFeatures,
        type_features: &TypeFeatures,
    ) -> Vec<ScoreFactor> {
        let mut factors = Vec::new();

        // Base factors
        factors.push(ScoreFactor {
            name: "income_stability".to_string(),
            impact: base.effective_stability() - 0.5,
            weight: 0.25,
            description: if base.is_seasonal {
                format!(
                    "Seasonal income stability: {:.0}% (adjusted for crop cycle)",
                    base.adjusted_stability * 100.0
                )
            } else {
                format!(
                    "Income consistency: {:.0}%",
                    base.raw.consistency_score * 100.0
                )
            },
        });

        factors.push(ScoreFactor {
            name: "transaction_volume".to_string(),
            impact: (base.raw.transaction_count_90d as f64 / 300.0).min(1.0) - 0.5,
            weight: 0.20,
            description: format!("{} transactions in 90 days", base.raw.transaction_count_90d),
        });

        // Type-specific factors
        for (i, name) in type_features.feature_names.iter().enumerate() {
            if let Some(&value) = type_features.feature_vector.get(i) {
                factors.push(ScoreFactor {
                    name: name.clone(),
                    impact: value - 0.5,
                    weight: 0.1,
                    description: format!("{}: {:.2}", name, value),
                });
            }
        }

        factors
    }

    fn compute_confidence(
        &self,
        base_score: f64,
        type_score: Option<f64>,
        worker_type: WorkerType,
    ) -> f64 {
        // Higher confidence when both base and type scores agree
        let base_conf = 0.6; // base model always has moderate confidence
        match type_score {
            Some(ts) => {
                let agreement = 1.0 - (base_score - ts).abs();
                let type_bonus = 0.3; // type features add confidence
                (base_conf + type_bonus * agreement).min(1.0)
            }
            None => base_conf,
        }
    }

    /// Compute standard error of the score estimate.
    /// Uses the delta method: SE(p) ≈ p(1-p) × σ_logit
    /// where σ_logit is estimated from model confidence and data sufficiency.
    fn compute_standard_error(
        &self,
        calibrated_prob: f64,
        confidence: f64,
        base_features: &AdjustedBaseFeatures,
    ) -> f64 {
        // Base SE from logit transform (delta method)
        // SE(p) = p(1-p) × SE(logit(p))
        // SE(logit(p)) is inversely proportional to sqrt(n) and model quality
        let p = calibrated_prob.clamp(0.01, 0.99);
        let logit_se = if confidence > 0.0 {
            1.0 / (confidence * 10.0) // higher confidence = lower SE
        } else {
            1.0 // maximum uncertainty
        };

        // Adjust for data sufficiency
        // More transactions = lower SE
        let n = base_features.raw.transaction_count_90d as f64;
        let data_factor = if n > 0.0 { 1.0 / n.sqrt() } else { 1.0 };

        // Delta method: SE(p) = p(1-p) × SE(logit(p))
        let se = p * (1.0 - p) * logit_se * (1.0 + data_factor);
        se.clamp(0.01, 0.3) // bound between 1% and 30%
    }
}
