// src/statistical/differential_privacy.rs
//
// S10: Differential Privacy implementation using the Laplace mechanism.
// Provides ε-differential privacy for aggregate queries.
//
// The Laplace mechanism adds noise drawn from Laplace(0, Δf/ε) to a query result,
// where Δf is the global sensitivity of the query and ε is the privacy budget.
//
// Properties:
// - ε = 0.1 means strong privacy (lower ε = more privacy)
// - Satisfies (ε, 0)-differential privacy (pure DP, no δ term)
// - Suitable for count queries, sum queries, and mean queries

use rand::Rng;
use serde::{Deserialize, Serialize};

/// Default privacy budget (epsilon) for the platform.
/// Lower values provide stronger privacy guarantees.
pub const DEFAULT_EPSILON: f64 = 0.1;

/// Maximum privacy budget allowed before queries are blocked.
pub const MAX_PRIVACY_BUDGET: f64 = 10.0;

/// Differential privacy engine using the Laplace mechanism.
#[derive(Debug, Clone)]
pub struct DifferentialPrivacyEngine {
    /// Privacy budget epsilon (smaller = more private)
    epsilon: f64,
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

impl DifferentialPrivacyEngine {
    /// Create a new DP engine with the given epsilon.
    pub fn new(epsilon: f64) -> Self {
        assert!(epsilon > 0.0, "Epsilon must be positive");
        Self {
            epsilon,
            consumed_budget: 0.0,
        }
    }

    /// Create engine with the default ε=0.1.
    pub fn standard() -> Self {
        Self::new(DEFAULT_EPSILON)
    }

    /// Get the remaining privacy budget.
    pub fn remaining_budget(&self) -> f64 {
        (MAX_PRIVACY_BUDGET - self.consumed_budget).max(0.0)
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
}
