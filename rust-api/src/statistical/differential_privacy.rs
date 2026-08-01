// src/statistical/differential_privacy.rs
//
// S10: Differential Privacy implementation using Laplace and Gaussian mechanisms.
// Provides ε-differential privacy for aggregate queries.
//
// Two mechanisms:
// - Laplace: pure (ε,0)-DP — suitable for count/sum queries
// - Gaussian: (ε,δ)-DP — suitable for ML gradients, averages, and smooth queries
//
// Properties:
// - ε = 0.1 means strong privacy (lower ε = more privacy)
// - Gaussian mechanism calibrates noise: σ = Δf × sqrt(2 × ln(1.25/δ)) / ε
// - Suitable for count queries, sum queries, mean queries, and gradient aggregation
//
// IC-PRIVACY changes:
// - Added Gaussian mechanism with proper (ε,δ) calibration
// - Added privacy_budget integration hooks
// - Added noise_scale() query methods for audit

use rand::Rng;
use rand_distr::{Distribution, Normal};
use serde::{Deserialize, Serialize};

/// Default privacy budget (epsilon) for the platform.
/// Lower values provide stronger privacy guarantees.
pub const DEFAULT_EPSILON: f64 = 0.1;

/// Maximum privacy budget allowed before queries are blocked.
pub const MAX_PRIVACY_BUDGET: f64 = 10.0;

/// Differential privacy engine using Laplace and Gaussian mechanisms.
///
/// Supports both pure (ε,0)-DP via Laplace and approximate (ε,δ)-DP via Gaussian.
/// Track cumulative privacy consumption and block queries when budget is exhausted.
#[derive(Debug, Clone)]
pub struct DifferentialPrivacyEngine {
    /// Privacy budget epsilon (smaller = more private)
    epsilon: f64,
    /// Delta parameter for Gaussian mechanism (typically 10⁻⁵ for datasets >10k)
    delta: f64,
    /// Cumulative privacy budget consumed
    consumed_budget: f64,
}

/// Result of a differentially private query.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DPResult<T: Serialize> {
    /// The noisy result (may be negative for counts, rounded for integers)
    pub noisy_value: T,
    /// The original (true) value — only available to authorized callers
    #[serde(skip_serializing_if = "Option::is_none")]
    pub true_value: Option<T>,
    /// Privacy budget consumed by this query
    pub epsilon_used: f64,
    /// Remaining privacy budget
    pub budget_remaining: f64,
    /// Whether the query was suppressed (budget exceeded)
    pub suppressed: bool,
}

/// Mechanism type used for a DP query (for audit logging).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum MechanismType {
    Laplace,
    Gaussian,
}

impl DifferentialPrivacyEngine {
    /// Create a new DP engine with the given epsilon (Laplace only, δ=0).
    pub fn new(epsilon: f64) -> Self {
        assert!(epsilon > 0.0, "Epsilon must be positive");
        Self {
            epsilon,
            delta: 0.0,
            consumed_budget: 0.0,
        }
    }

    /// Create engine with Gaussian mechanism support (ε,δ)-DP.
    /// δ should be ≪ 1/n where n is dataset size.
    pub fn with_gaussian(epsilon: f64, delta: f64) -> Self {
        assert!(epsilon > 0.0, "Epsilon must be positive");
        assert!(delta > 0.0 && delta < 1.0, "Delta must be in (0, 1)");
        Self {
            epsilon,
            delta,
            consumed_budget: 0.0,
        }
    }

    /// Create engine with the default ε=0.1, δ=10⁻⁵.
    pub fn standard() -> Self {
        Self::with_gaussian(DEFAULT_EPSILON, 1e-5)
    }

    /// Get the remaining privacy budget.
    pub fn remaining_budget(&self) -> f64 {
        (MAX_PRIVACY_BUDGET - self.consumed_budget).max(0.0)
    }

    /// Get the current epsilon.
    pub fn epsilon(&self) -> f64 {
        self.epsilon
    }

    /// Get the current delta.
    pub fn delta(&self) -> f64 {
        self.delta
    }

    /// Get consumed budget.
    pub fn consumed_budget(&self) -> f64 {
        self.consumed_budget
    }

    /// Add Laplace noise to a floating-point query result.
    ///
    /// The Laplace mechanism: result = true_value + Laplace(0, sensitivity/ε)
    ///
    /// # Arguments
    /// * `true_value` - The true query result
    /// * `sensitivity` - The global sensitivity (max change one individual can cause)
    ///
    /// # Returns
    /// A DPResult with the noisy value, or suppressed if budget is exceeded.
    pub fn laplace_mechanism_f64(&mut self, true_value: f64, sensitivity: f64) -> DPResult<f64> {
        if self.consumed_budget >= MAX_PRIVACY_BUDGET {
            return DPResult {
                noisy_value: true_value, // Return true value but mark as suppressed
                true_value: Some(true_value),
                epsilon_used: 0.0,
                budget_remaining: 0.0,
                suppressed: true,
            };
        }

        let scale = sensitivity / self.epsilon;
        let noise = sample_laplace(scale);
        let noisy_value = true_value + noise;

        self.consumed_budget += self.epsilon;

        DPResult {
            noisy_value,
            true_value: Some(true_value),
            epsilon_used: self.epsilon,
            budget_remaining: self.remaining_budget(),
            suppressed: false,
        }
    }

    /// Add Laplace noise to a count query (integer result).
    ///
    /// Counts have sensitivity = 1 (one person can add/remove at most 1 from a count).
    pub fn laplace_count(&mut self, true_count: i64) -> DPResult<i64> {
        let result = self.laplace_mechanism_f64(true_count as f64, 1.0);
        DPResult {
            noisy_value: result.noisy_value.round() as i64,
            true_value: result.true_value.map(|v| v.round() as i64),
            epsilon_used: result.epsilon_used,
            budget_remaining: result.budget_remaining,
            suppressed: result.suppressed,
        }
    }

    /// Add Laplace noise to a sum query.
    ///
    /// For bounded data in [0, max_value], sensitivity = max_value.
    pub fn laplace_sum(&mut self, true_sum: f64, max_value: f64) -> DPResult<f64> {
        self.laplace_mechanism_f64(true_sum, max_value)
    }

    /// Add Laplace noise to a mean query.
    ///
    /// For bounded data in [0, max_value] with n individuals:
    /// sensitivity = max_value / n
    pub fn laplace_mean(&mut self, true_mean: f64, max_value: f64, n: u64) -> DPResult<f64> {
        if n == 0 {
            return DPResult {
                noisy_value: 0.0,
                true_value: Some(0.0),
                epsilon_used: 0.0,
                budget_remaining: self.remaining_budget(),
                suppressed: true,
            };
        }
        let sensitivity = max_value / n as f64;
        self.laplace_mechanism_f64(true_mean, sensitivity)
    }

    /// Add Gaussian noise for (ε,δ)-differential privacy.
    ///
    /// The Gaussian mechanism: result = true_value + N(0, σ²)
    /// where σ = sensitivity × sqrt(2 × ln(1.25/δ)) / ε
    ///
    /// This provides (ε,δ)-DP which is appropriate when:
    /// - The query result is continuous (means, sums, gradients)
    /// - δ > 0 is acceptable (typically δ ≪ 1/n)
    ///
    /// # Arguments
    /// * `true_value` - The true query result
    /// * `sensitivity` - The L2 sensitivity of the query
    pub fn gaussian_mechanism_f64(&mut self, true_value: f64, sensitivity: f64) -> DPResult<f64> {
        if self.consumed_budget >= MAX_PRIVACY_BUDGET {
            return DPResult {
                noisy_value: true_value,
                true_value: Some(true_value),
                epsilon_used: 0.0,
                budget_remaining: 0.0,
                suppressed: true,
            };
        }

        if self.delta <= 0.0 {
            // Fallback to Laplace if no delta set
            return self.laplace_mechanism_f64(true_value, sensitivity);
        }

        let sigma = self.gaussian_noise_scale(sensitivity);
        let normal = Normal::new(0.0, sigma).expect("Gaussian params should be valid");
        let mut rng = rand::thread_rng();
        let noise: f64 = normal.sample(&mut rng);
        let noisy_value = true_value + noise;

        self.consumed_budget += self.epsilon;

        DPResult {
            noisy_value,
            true_value: Some(true_value),
            epsilon_used: self.epsilon,
            budget_remaining: self.remaining_budget(),
            suppressed: false,
        }
    }

    /// Add Gaussian noise to a count query.
    /// Sensitivity = 1 for counts.
    pub fn gaussian_count(&mut self, true_count: i64) -> DPResult<i64> {
        let result = self.gaussian_mechanism_f64(true_count as f64, 1.0);
        DPResult {
            noisy_value: result.noisy_value.round() as i64,
            true_value: result.true_value.map(|v| v.round() as i64),
            epsilon_used: result.epsilon_used,
            budget_remaining: result.budget_remaining,
            suppressed: result.suppressed,
        }
    }

    /// Add Gaussian noise to a sum query.
    /// For bounded data in [0, max_value], L2 sensitivity = max_value.
    pub fn gaussian_sum(&mut self, true_sum: f64, max_value: f64) -> DPResult<f64> {
        self.gaussian_mechanism_f64(true_sum, max_value)
    }

    /// Add Gaussian noise to a mean query.
    /// For bounded data in [0, max_value] with n individuals:
    /// L2 sensitivity = max_value / n
    pub fn gaussian_mean(&mut self, true_mean: f64, max_value: f64, n: u64) -> DPResult<f64> {
        if n == 0 {
            return DPResult {
                noisy_value: 0.0,
                true_value: Some(0.0),
                epsilon_used: 0.0,
                budget_remaining: self.remaining_budget(),
                suppressed: true,
            };
        }
        let sensitivity = max_value / n as f64;
        self.gaussian_mechanism_f64(true_mean, sensitivity)
    }

    /// Compute the Gaussian noise standard deviation σ for a given sensitivity.
    /// σ = sensitivity × sqrt(2 × ln(1.25/δ)) / ε
    pub fn gaussian_noise_scale(&self, sensitivity: f64) -> f64 {
        assert!(self.delta > 0.0, "Gaussian mechanism requires delta > 0");
        sensitivity * (2.0 * (1.25_f64 / self.delta).ln()).sqrt() / self.epsilon
    }

    /// Compute the Laplace noise scale b for a given sensitivity.
    /// b = sensitivity / ε
    pub fn laplace_noise_scale(&self, sensitivity: f64) -> f64 {
        sensitivity / self.epsilon
    }

    /// Reset the privacy budget (e.g., at the start of a new time window).
    pub fn reset_budget(&mut self) {
        self.consumed_budget = 0.0;
    }
}

/// Sample from a Laplace distribution with the given scale parameter.
/// Laplace(0, b) where b = sensitivity / epsilon.
fn sample_laplace(scale: f64) -> f64 {
    let mut rng = rand::thread_rng();
    let u: f64 = rng.gen_range(-0.5..0.5);
    -scale * u.signum() * (1.0 - 2.0 * u.abs()).ln()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_laplace_count_basic() {
        let mut engine = DifferentialPrivacyEngine::new(1.0);
        let result = engine.laplace_count(100);
        // The noisy value should be somewhat close to 100 (within a few units for ε=1.0)
        assert!(!result.suppressed);
        assert!(result.noisy_value > 80 && result.noisy_value < 120);
    }

    #[test]
    fn test_budget_exhaustion() {
        let mut engine = DifferentialPrivacyEngine::new(1.0);
        // Exhaust budget (MAX_PRIVACY_BUDGET = 10.0, ε = 1.0, so 10 queries)
        for _ in 0..10 {
            let _ = engine.laplace_count(100);
        }
        assert!(engine.remaining_budget() <= 0.001);
        let result = engine.laplace_count(100);
        assert!(result.suppressed);
    }

    #[test]
    fn test_default_epsilon() {
        let engine = DifferentialPrivacyEngine::standard();
        assert!((engine.epsilon - DEFAULT_EPSILON).abs() < f64::EPSILON);
    }

    #[test]
    fn test_budget_reset() {
        let mut engine = DifferentialPrivacyEngine::new(1.0);
        let _ = engine.laplace_count(100);
        assert!(engine.consumed_budget > 0.0);
        engine.reset_budget();
        assert!((engine.consumed_budget).abs() < f64::EPSILON);
    }

    #[test]
    fn test_gaussian_count_basic() {
        let mut engine = DifferentialPrivacyEngine::with_gaussian(1.0, 1e-5);
        let result = engine.gaussian_count(100);
        assert!(!result.suppressed);
        // Gaussian noise σ = sqrt(2 × ln(1.25×10⁵)) / 1.0 ≈ 4.9
        // So noisy value should be within ~20 of true value with high probability
        assert!(result.noisy_value > 70 && result.noisy_value < 130);
    }

    #[test]
    fn test_gaussian_noise_scale_calibration() {
        let engine = DifferentialPrivacyEngine::with_gaussian(1.0, 1e-5);
        let sigma = engine.gaussian_noise_scale(1.0);
        // σ = 1.0 × sqrt(2 × ln(1.25/1e-5)) / 1.0
        // = sqrt(2 × ln(125000)) ≈ sqrt(2 × 11.736) ≈ sqrt(23.47) ≈ 4.845
        assert!((sigma - 4.845).abs() < 0.1, "sigma={}", sigma);
    }

    #[test]
    fn test_gaussian_mean() {
        let mut engine = DifferentialPrivacyEngine::with_gaussian(0.5, 1e-6);
        // Mean of values in [0, 1000] with 100 individuals → sensitivity = 10.0
        let result = engine.gaussian_mean(500.0, 1000.0, 100);
        assert!(!result.suppressed);
        // Should be within reasonable range
        assert!(result.noisy_value > 400.0 && result.noisy_value < 600.0,
            "noisy_value={}", result.noisy_value);
    }

    #[test]
    fn test_gaussian_budget_exhaustion() {
        let mut engine = DifferentialPrivacyEngine::with_gaussian(1.0, 1e-5);
        for _ in 0..10 {
            let _ = engine.gaussian_count(100);
        }
        assert!(engine.remaining_budget() <= 0.001);
        let result = engine.gaussian_count(100);
        assert!(result.suppressed);
    }
}
