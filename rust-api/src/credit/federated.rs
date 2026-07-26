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
