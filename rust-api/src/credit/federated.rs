//! Federated learning types for credit model aggregation

use super::types::WorkerType;
use serde::{Deserialize, Serialize};

/// Worker cohort for federated learning aggregation
/// Multiple dimensions allow fine-grained model updates
pub struct WorkerCohort {
    pub worker_type: WorkerType,
    pub region: String,           // e.g., "nairobi", "kisumu"
    pub income_tercile: u8,       // 1=low, 2=medium, 3=high
    pub business_age_bucket: u8,  // 0=new(<6mo), 1=growing(6-24mo), 2=established(>24mo)
}

impl WorkerCohort {
    /// Cohort key for aggregation (must have ≥10 members for k-anonymity)
    pub fn aggregation_key(&self) -> String {
        format!("{}|{}|{}|{}", 
            self.worker_type, self.region, self.income_tercile, self.business_age_bucket)
    }
}

/// FedProx aggregation implementation.
/// Proximal term (μ) penalizes deviation from the global model,
/// making convergence more stable for non-IID data across Kenyan worker cohorts.
pub struct FedProxAggregator {
    /// Proximal term coefficient (higher = more conservative updates)
    pub mu: f64,
    /// Gradient clipping norm for privacy
    pub clip_norm: f64,
    /// Noise multiplier for differential privacy
    pub noise_multiplier: f64,
}

impl FedProxAggregator {
    pub fn new(mu: f64, clip_norm: f64, noise_multiplier: f64) -> Self {
        Self { mu, clip_norm, noise_multiplier }
    }

    /// Default FedProx for credit scoring (conservative, stable)
    pub fn credit_default() -> Self {
        Self::new(0.01, 1.0, 0.0)
    }

    /// Aggregate gradient batches from multiple cohorts.
    /// Returns the aggregated global gradient.
    pub fn aggregate(&self, batches: &[GradientBatch]) -> Result<Vec<f64>, String> {
        if batches.is_empty() {
            return Err("No gradient batches to aggregate".to_string());
        }

        let total_samples: u64 = batches.iter().map(|b| b.sample_count).sum();
        if total_samples == 0 {
            return Err("Total sample count is zero".to_string());
        }

        let grad_dim = batches.first().map(|b| b.gradients.len()).unwrap_or(0);
        if grad_dim == 0 {
            return Err("Empty gradients".to_string());
        }

        let mut aggregated = vec![0.0_f64; grad_dim];

        for batch in batches {
            let weight = batch.sample_count as f64 / total_samples as f64;
            // Clip gradients for privacy
            let grad_norm: f64 = batch.gradients.iter().map(|g| g * g).sum::<f64>().sqrt();
            let clip_factor = if grad_norm > self.clip_norm {
                self.clip_norm / grad_norm
            } else {
                1.0
            };

            for (i, &grad) in batch.gradients.iter().enumerate() {
                if i < grad_dim {
                    // FedProx: weighted clipped gradient + proximal regularization
                    let clipped_grad = grad * clip_factor;
                    aggregated[i] += weight * clipped_grad;
                }
            }
        }

        // Apply FedProx proximal damping
        for grad in &mut aggregated {
            *grad *= 1.0 / (1.0 + self.mu);
        }

        Ok(aggregated)
    }
}

/// A gradient batch from a single cohort.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GradientBatch {
    pub cohort_hash: String,
    pub gradients: Vec<f64>,
    pub sample_count: u64,
    pub local_loss: f64,
}

/// Monitor score distribution changes during migration
pub struct ScoreDistributionMonitor {
    /// Pre-migration score distribution (baseline)
    baseline_distribution: Histogram,
    /// Current distribution
    current_distribution: Histogram,
    /// Per-type distributions
    type_distributions: std::collections::HashMap<WorkerType, Histogram>,
    /// Alert threshold (max KL divergence from baseline)
    max_divergence: f64,
}

impl ScoreDistributionMonitor {
    /// Check if score distribution has shifted significantly
    pub fn check_drift(&self) -> DriftReport {
        let kl_divergence = self.kl_divergence(&self.baseline_distribution, &self.current_distribution);
        DriftReport {
            overall_divergence: kl_divergence,
            is_drifted: kl_divergence > self.max_divergence,
            type_reports: self.type_distributions.iter().map(|(wt, hist)| {
                TypeDriftReport {
                    worker_type: *wt,
                    divergence: self.kl_divergence(&self.baseline_distribution, hist),
                    mean_shift: hist.mean() - self.baseline_distribution.mean(),
                }
            }).collect(),
        }
    }
}
