// credit/score_fusion.rs

use super::types::{WorkerType, TypeFeatures};
use super::base_features::AdjustedBaseFeatures;

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
    /// Factor breakdown for explainability
    pub factors: Vec<ScoreFactor>,
    /// Whether seasonal adjustment was applied
    pub seasonally_adjusted: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScoreFactor {
    pub name: String,
    pub impact: f64,        // positive = improves score, negative = reduces
    pub weight: f64,        // importance weight
    pub description: String,
}

pub struct ScoreFusionEngine {
    /// Type head weights (β) — can be updated via calibration
    type_weights: std::collections::HashMap<WorkerType, f64>,
    /// Per-type calibrators for post-fusion adjustment
    type_calibrators: std::collections::HashMap<WorkerType, TypeCalibrator>,
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

        Self { type_weights, type_calibrators }
    }

    /// Compute fused score
    pub fn compute_score(
        &self,
        base_score: f64,
        base_features: &AdjustedBaseFeatures,
        type_features: Option<&TypeFeatures>,
        worker_type: WorkerType,
    ) -> FusedAlamaScore {
        let beta = self.type_weights.get(&worker_type).copied().unwrap_or(0.0);
        let alpha = 1.0 - beta;

        let (type_score, factors) = if let Some(tf) = type_features {
            let raw_type = self.compute_type_score(tf);
            let factors = self.extract_factors(base_features, tf);
            (Some(raw_type), factors)
        } else {
            (None, Vec::new())
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

        FusedAlamaScore {
            alama_score: alama_score.clamp(300, 850),
            raw_score: calibrated,
            base_score,
            type_score,
            worker_type,
            type_weight: beta,
            confidence,
            factors,
            seasonally_adjusted: base_features.is_seasonal,
        }
    }

    fn compute_type_score(&self, features: &TypeFeatures) -> f64 {
        // Simple weighted sum of normalized feature vector
        // In production: this would be a trained model per type
        if features.feature_vector.is_empty() {
            return 0.5; // neutral
        }
        let sum: f64 = features.feature_vector.iter().sum();
        let mean = sum / features.feature_vector.len() as f64;
        mean.clamp(0.0, 1.0)
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
                format!("Seasonal income stability: {:.0}% (adjusted for crop cycle)", 
                    base.adjusted_stability * 100.0)
            } else {
                format!("Income consistency: {:.0}%", base.raw.consistency_score * 100.0)
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
}
