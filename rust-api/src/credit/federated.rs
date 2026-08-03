//! Federated learning types for credit model aggregation
//!
//! Task 1 (IC-PRIVACY): FedProxAggregator now applies calibrated Gaussian noise
//! using the `noise_multiplier` field for (ε,δ)-differential privacy.
//! Noise is added per-dimension after gradient aggregation and proximal damping.

use super::types::WorkerType;
use rand_distr::{Distribution, Normal};
use serde::{Deserialize, Serialize};

/// Worker cohort for federated learning aggregation
/// Multiple dimensions allow fine-grained model updates
pub struct WorkerCohort {
    pub worker_type: WorkerType,
    pub region: String,          // e.g., "nairobi", "kisumu"
    pub income_tercile: u8,      // 1=low, 2=medium, 3=high
    pub business_age_bucket: u8, // 0=new(<6mo), 1=growing(6-24mo), 2=established(>24mo)
}

impl WorkerCohort {
    /// Cohort key for aggregation (must have ≥10 members for k-anonymity)
    pub fn aggregation_key(&self) -> String {
        format!(
            "{}|{}|{}|{}",
            self.worker_type, self.region, self.income_tercile, self.business_age_bucket
        )
    }
}

/// FedProx aggregation implementation.
/// Proximal term (μ) penalizes deviation from the global model,
/// making convergence more stable for non-IID data across Kenyan worker cohorts.
///
/// ## Differential Privacy
/// When `noise_multiplier > 0`, Gaussian noise is added to the aggregated
/// gradient to satisfy (ε,δ)-differential privacy. The noise is calibrated as:
///
///   σ = noise_multiplier × clip_norm
///
/// where `noise_multiplier = sensitivity × sqrt(2 × ln(1.25/δ)) / ε`.
/// The default `credit_default()` constructor sets `noise_multiplier = 0.0`
/// (no noise); production deployments MUST set a positive value.
pub struct FedProxAggregator {
    /// Proximal term coefficient (higher = more conservative updates)
    pub mu: f64,
    /// Gradient clipping norm — also serves as the L2 sensitivity bound.
    /// Each gradient is clipped to this norm before aggregation.
    pub clip_norm: f64,
    /// Noise multiplier for differential privacy.
    /// σ = noise_multiplier × clip_norm.
    /// Set to 0.0 to disable noise (NOT recommended for production).
    pub noise_multiplier: f64,
}

impl FedProxAggregator {
    pub fn new(mu: f64, clip_norm: f64, noise_multiplier: f64) -> Self {
        Self {
            mu,
            clip_norm,
            noise_multiplier,
        }
    }

    /// Default FedProx for credit scoring (conservative, stable).
    /// NOTE: `noise_multiplier` is 0.0 — NO differential privacy.
    /// Use `credit_private(epsilon, delta)` for production.
    pub fn credit_default() -> Self {
        Self::new(0.01, 1.0, 0.0)
    }

    /// Production-ready FedProx with differential privacy.
    /// Calibrates noise_multiplier from (ε, δ) and the clip_norm (sensitivity).
    ///
    /// Formula: σ = clip_norm × sqrt(2 × ln(1.25/δ)) / ε
    /// noise_multiplier = σ / clip_norm = sqrt(2 × ln(1.25/δ)) / ε
    pub fn credit_private(epsilon: f64, delta: f64) -> Self {
        assert!(epsilon > 0.0, "epsilon must be positive");
        assert!(delta > 0.0 && delta < 1.0, "delta must be in (0, 1)");
        let clip_norm = 1.0;
        let noise_multiplier = (2.0 * (1.25_f64 / delta).ln()).sqrt() / epsilon;
        Self::new(0.01, clip_norm, noise_multiplier)
    }

    /// Compute the actual noise standard deviation σ.
    pub fn noise_sigma(&self) -> f64 {
        self.noise_multiplier * self.clip_norm
    }

    /// Aggregate gradient batches from multiple cohorts.
    /// Returns the aggregated global gradient with calibrated Gaussian noise
    /// when `noise_multiplier > 0`.
    ///
    /// Steps:
    /// 1. Clip each cohort gradient to `clip_norm` (L2 sensitivity bound)
    /// 2. Weighted average of clipped gradients
    /// 3. Apply FedProx proximal damping
    /// 4. Add Gaussian noise N(0, σ²I) where σ = noise_multiplier × clip_norm
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
            // Clip gradients for privacy (L2 clipping)
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

        // ═══════════════════════════════════════════════════════════
        //  DP-FL: Add calibrated Gaussian noise to aggregated gradient
        //  σ = noise_multiplier × clip_norm
        //  This provides (ε,δ)-differential privacy for the aggregation.
        // ═══════════════════════════════════════════════════════════
        if self.noise_multiplier > 0.0 {
            let sigma = self.noise_sigma();
            let normal = Normal::new(0.0, sigma)
                .map_err(|e| format!("Failed to create Gaussian distribution: {}", e))?;
            let mut rng = rand::thread_rng();

            for grad in &mut aggregated {
                let noise: f64 = normal.sample(&mut rng);
                *grad += noise;
            }

            tracing::info!(
                sigma = %sigma,
                noise_multiplier = %self.noise_multiplier,
                clip_norm = %self.clip_norm,
                grad_dim = %grad_dim,
                "Applied Gaussian DP noise to federated gradient aggregation"
            );
        } else {
            tracing::warn!(
                "FedProxAggregator running WITHOUT differential privacy (noise_multiplier=0)"
            );
        }

        Ok(aggregated)
    }

    /// Aggregate with full DP metadata returned alongside the gradient.
    /// Useful for audit trails and privacy budget accounting.
    pub fn aggregate_with_metadata(
        &self,
        batches: &[GradientBatch],
    ) -> Result<AggregatedGradient, String> {
        let gradients = self.aggregate(batches)?;
        let total_samples: u64 = batches.iter().map(|b| b.sample_count).sum();
        let num_cohorts = batches.len() as u32;

        Ok(AggregatedGradient {
            gradients,
            noise_sigma: self.noise_sigma(),
            noise_multiplier: self.noise_multiplier,
            clip_norm: self.clip_norm,
            total_samples,
            num_cohorts,
            dp_applied: self.noise_multiplier > 0.0,
        })
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

/// Result of an aggregation with DP metadata for audit trails.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AggregatedGradient {
    pub gradients: Vec<f64>,
    /// The noise standard deviation σ that was applied (0 if no DP).
    pub noise_sigma: f64,
    pub noise_multiplier: f64,
    pub clip_norm: f64,
    pub total_samples: u64,
    pub num_cohorts: u32,
    /// Whether DP noise was actually applied.
    pub dp_applied: bool,
}

/// P2: Convergence monitoring for federated learning rounds.
/// Tracks loss, gradient norm, and model drift per round to detect
/// convergence issues early and trigger alerts.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConvergenceMonitor {
    /// Per-round loss history
    pub round_losses: Vec<f64>,
    /// Per-round gradient norms (L2)
    pub gradient_norms: Vec<f64>,
    /// Per-round number of participating cohorts
    pub cohort_counts: Vec<u32>,
    /// Loss improvement threshold for convergence detection
    pub convergence_threshold: f64,
    /// Maximum rounds before forced stop
    pub max_rounds: u32,
}

impl ConvergenceMonitor {
    pub fn new(convergence_threshold: f64, max_rounds: u32) -> Self {
        Self {
            round_losses: Vec::new(),
            gradient_norms: Vec::new(),
            cohort_counts: Vec::new(),
            convergence_threshold,
            max_rounds,
        }
    }

    /// Record a completed FL round's metrics
    pub fn record_round(&mut self, loss: f64, gradient_norm: f64, cohort_count: u32) {
        self.round_losses.push(loss);
        self.gradient_norms.push(gradient_norm);
        self.cohort_counts.push(cohort_count);
    }

    /// Check if training has converged (loss improvement < threshold for 3 rounds)
    pub fn has_converged(&self) -> bool {
        if self.round_losses.len() < 4 {
            return false;
        }
        let n = self.round_losses.len();
        let recent = &self.round_losses[n - 4..];
        // Check if all recent improvements are below threshold
        recent
            .windows(2)
            .all(|w| (w[0] - w[1]).abs() < self.convergence_threshold)
    }

    /// Check if max rounds exceeded
    pub fn max_rounds_exceeded(&self) -> bool {
        self.round_losses.len() as u32 >= self.max_rounds
    }

    /// Get the latest gradient norm (for drift detection)
    pub fn latest_gradient_norm(&self) -> Option<f64> {
        self.gradient_norms.last().copied()
    }

    /// Detect gradient explosion (norm > 10× average)
    pub fn detect_gradient_explosion(&self) -> bool {
        if self.gradient_norms.len() < 3 {
            return false;
        }
        let avg: f64 = self.gradient_norms.iter().sum::<f64>() / self.gradient_norms.len() as f64;
        let latest = self.gradient_norms.last().copied().unwrap_or(0.0);
        latest > avg * 10.0
    }

    /// Generate a convergence report
    pub fn report(&self) -> ConvergenceReport {
        ConvergenceReport {
            total_rounds: self.round_losses.len() as u32,
            latest_loss: self.round_losses.last().copied(),
            latest_gradient_norm: self.gradient_norms.last().copied(),
            converged: self.has_converged(),
            max_rounds_reached: self.max_rounds_exceeded(),
            gradient_explosion_detected: self.detect_gradient_explosion(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConvergenceReport {
    pub total_rounds: u32,
    pub latest_loss: Option<f64>,
    pub latest_gradient_norm: Option<f64>,
    pub converged: bool,
    pub max_rounds_reached: bool,
    pub gradient_explosion_detected: bool,
}

// ═══════════════════════════════════════════════════════════
//  P1: Gradient Sparsification — Top-K for communication efficiency
// ═══════════════════════════════════════════════════════════

/// Gradient sparsification strategy for communication efficiency.
/// Reduces communication cost by transmitting only the top-K largest
/// gradient components (by absolute value).
///
/// Research shows top-10% sparsification reduces communication by 10×
/// with <1% accuracy loss (Alistarh et al., 2017).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum SparsificationStrategy {
    /// No sparsification — transmit all gradients
    None,
    /// Keep top-K gradients by absolute value
    TopK { k: usize },
    /// Keep gradients above a threshold
    Threshold { threshold: f64 },
    /// Random sparsification with uniform sampling
    RandomK { k: usize },
}

impl SparsificationStrategy {
    /// Default for credit scoring FL: top 10% of gradients
    pub fn credit_default(num_params: usize) -> Self {
        Self::TopK {
            k: (num_params / 10).max(1),
        }
    }
}

/// Sparsify a gradient vector according to the given strategy.
/// Returns (sparse_indices, sparse_values) for efficient transmission.
pub fn sparsify_gradient(
    gradient: &[f64],
    strategy: &SparsificationStrategy,
) -> (Vec<usize>, Vec<f64>) {
    match strategy {
        SparsificationStrategy::None => (
            gradient.iter().enumerate().map(|(i, _)| i).collect(),
            gradient.to_vec(),
        ),
        SparsificationStrategy::TopK { k } => {
            let k = (*k).min(gradient.len());
            let mut indexed: Vec<(usize, f64)> = gradient
                .iter()
                .enumerate()
                .map(|(i, &v)| (i, v.abs()))
                .collect();
            indexed.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
            let indices: Vec<usize> = indexed[..k].iter().map(|(i, _)| *i).collect();
            let values: Vec<f64> = indices.iter().map(|&i| gradient[i]).collect();
            (indices, values)
        }
        SparsificationStrategy::Threshold { threshold } => {
            let indices: Vec<usize> = gradient
                .iter()
                .enumerate()
                .filter(|(_, v)| v.abs() >= *threshold)
                .map(|(i, _)| i)
                .collect();
            let values: Vec<f64> = indices.iter().map(|&i| gradient[i]).collect();
            (indices, values)
        }
        SparsificationStrategy::RandomK { k } => {
            use rand::seq::SliceRandom;
            let k = (*k).min(gradient.len());
            let mut all_indices: Vec<usize> = (0..gradient.len()).collect();
            let mut rng = rand::thread_rng();
            all_indices.shuffle(&mut rng);
            let indices: Vec<usize> = all_indices[..k].to_vec();
            let mut sorted_indices = indices.clone();
            sorted_indices.sort();
            let values: Vec<f64> = sorted_indices.iter().map(|&i| gradient[i]).collect();
            (sorted_indices, values)
        }
    }
}

/// Reconstruct a dense gradient from sparse (indices, values) representation.
pub fn densify_gradient(sparse_indices: &[usize], sparse_values: &[f64], dim: usize) -> Vec<f64> {
    let mut dense = vec![0.0_f64; dim];
    for (&idx, &val) in sparse_indices.iter().zip(sparse_values.iter()) {
        if idx < dim {
            dense[idx] = val;
        }
    }
    dense
}

// ═══════════════════════════════════════════════════════════
//  P1: Byzantine-Robust Aggregation — RobustMedian / Trimmed Mean
// ═══════════════════════════════════════════════════════════

/// Aggregation strategy for Byzantine robustness.
/// Protects against malicious or corrupted cohort gradients.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AggregationStrategy {
    /// Standard weighted average (vulnerable to Byzantine faults)
    WeightedAverage,
    /// Coordinate-wise trimmed mean — discards top/bottom β fraction
    TrimmedMean { trim_fraction: f64 },
    /// Coordinate-wise median (most robust, less efficient)
    CoordinateMedian,
    /// Krum — selects the gradient closest to its neighbors
    Krum,
}

impl AggregationStrategy {
    pub fn robust_default() -> Self {
        Self::TrimmedMean { trim_fraction: 0.1 }
    }
}

/// Apply Byzantine-robust aggregation to gradient batches.
/// Returns the aggregated gradient.
pub fn robust_aggregate(
    batches: &[GradientBatch],
    strategy: &AggregationStrategy,
) -> Result<Vec<f64>, String> {
    if batches.is_empty() {
        return Err("No batches to aggregate".to_string());
    }

    let dim = batches[0].gradients.len();
    if dim == 0 {
        return Err("Empty gradients".to_string());
    }

    match strategy {
        AggregationStrategy::WeightedAverage => {
            // Standard weighted average (same as FedProxAggregator)
            let total: u64 = batches.iter().map(|b| b.sample_count).sum();
            if total == 0 {
                return Err("Zero total samples".to_string());
            }
            let mut result = vec![0.0_f64; dim];
            for batch in batches {
                let w = batch.sample_count as f64 / total as f64;
                for (i, &g) in batch.gradients.iter().enumerate() {
                    if i < dim {
                        result[i] += w * g;
                    }
                }
            }
            Ok(result)
        }
        AggregationStrategy::TrimmedMean { trim_fraction } => {
            // Coordinate-wise trimmed mean
            let n = batches.len();
            let trim = ((n as f64 * trim_fraction).floor() as usize).max(0);
            let keep_start = trim;
            let keep_end = n - trim;

            let mut result = vec![0.0_f64; dim];
            for d in 0..dim {
                let mut values: Vec<f64> = batches
                    .iter()
                    .filter_map(|b| b.gradients.get(d).copied())
                    .collect();
                values.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));

                if keep_start < keep_end && keep_end <= values.len() {
                    let kept = &values[keep_start..keep_end];
                    result[d] = kept.iter().sum::<f64>() / kept.len() as f64;
                } else {
                    result[d] = values.iter().sum::<f64>() / values.len().max(1) as f64;
                }
            }
            Ok(result)
        }
        AggregationStrategy::CoordinateMedian => {
            let mut result = vec![0.0_f64; dim];
            for d in 0..dim {
                let mut values: Vec<f64> = batches
                    .iter()
                    .filter_map(|b| b.gradients.get(d).copied())
                    .collect();
                values.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
                result[d] = if values.len() % 2 == 0 && values.len() >= 2 {
                    (values[values.len() / 2 - 1] + values[values.len() / 2]) / 2.0
                } else if !values.is_empty() {
                    values[values.len() / 2]
                } else {
                    0.0
                };
            }
            Ok(result)
        }
        AggregationStrategy::Krum => {
            // Krum: select the gradient with the smallest sum of distances to its k-nearest neighbors
            let n = batches.len();
            let k = (n - 2).max(1); // k = n - 2 by default

            // Compute pairwise distances
            let mut distances = vec![vec![0.0_f64; n]; n];
            for i in 0..n {
                for j in (i + 1)..n {
                    let dist: f64 = batches[i]
                        .gradients
                        .iter()
                        .zip(batches[j].gradients.iter())
                        .map(|(a, b)| (a - b).powi(2))
                        .sum::<f64>()
                        .sqrt();
                    distances[i][j] = dist;
                    distances[j][i] = dist;
                }
            }

            // For each gradient, sum distances to k-nearest neighbors
            let mut scores: Vec<(usize, f64)> = (0..n)
                .map(|i| {
                    let mut dists: Vec<f64> = distances[i]
                        .iter()
                        .enumerate()
                        .filter(|(j, _)| *j != i)
                        .map(|(_, d)| *d)
                        .collect();
                    dists.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
                    let score: f64 = dists[..k.min(dists.len())].iter().sum();
                    (i, score)
                })
                .collect();

            scores.sort_by(|a, b| a.1.partial_cmp(&b.1).unwrap_or(std::cmp::Ordering::Equal));
            let winner = scores[0].0;
            Ok(batches[winner].gradients.clone())
        }
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
        let kl_divergence =
            self.kl_divergence(&self.baseline_distribution, &self.current_distribution);
        DriftReport {
            overall_divergence: kl_divergence,
            is_drifted: kl_divergence > self.max_divergence,
            type_reports: self
                .type_distributions
                .iter()
                .map(|(wt, hist)| TypeDriftReport {
                    worker_type: *wt,
                    divergence: self.kl_divergence(&self.baseline_distribution, hist),
                    mean_shift: hist.mean() - self.baseline_distribution.mean(),
                })
                .collect(),
        }
    }
}
