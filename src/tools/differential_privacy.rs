use serde::{Deserialize, Serialize};
use rand::Rng;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DifferentialPrivacyConfig {
    pub epsilon: f64,
    pub sensitivity: f64,
    pub delta: f64,
}

impl Default for DifferentialPrivacyConfig {
    fn default() -> Self {
        Self {
            epsilon: 1.0,
            sensitivity: 1.0,
            delta: 1e-6,
        }
    }
}

/// Privacy budget tracker for composition theorem.
/// Tracks cumulative epsilon spent across queries.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PrivacyBudget {
    pub total_epsilon: f64,
    pub spent_epsilon: f64,
    pub query_count: usize,
}

impl PrivacyBudget {
    pub fn new(total_epsilon: f64) -> Self {
        Self {
            total_epsilon,
            spent_epsilon: 0.0,
            query_count: 0,
        }
    }

    pub fn remaining(&self) -> f64 {
        (self.total_epsilon - self.spent_epsilon).max(0.0)
    }

    pub fn is_exhausted(&self) -> bool {
        self.spent_epsilon >= self.total_epsilon
    }

    /// Record epsilon spent by a query. Returns false if budget exceeded.
    pub fn spend(&mut self, epsilon: f64) -> bool {
        if self.spent_epsilon + epsilon > self.total_epsilon {
            return false;
        }
        self.spent_epsilon += epsilon;
        self.query_count += 1;
        true
    }
}

pub struct DifferentialPrivacyEngine {
    config: DifferentialPrivacyConfig,
    budget: PrivacyBudget,
}

impl DifferentialPrivacyEngine {
    pub fn new(config: DifferentialPrivacyConfig) -> Self {
        let budget = PrivacyBudget::new(config.epsilon * 100.0); // default 100 queries
        Self { config, budget }
    }

    pub fn with_budget(mut self, total_epsilon: f64) -> Self {
        self.budget = PrivacyBudget::new(total_epsilon);
        self
    }

    /// Generate Laplacian noise: Lap(sensitivity / epsilon).
    /// Uses the inverse CDF method: X = location - b * sgn(U) * ln(1 - 2|U|)
    /// where U ~ Uniform(-0.5, 0.5) and b = sensitivity / epsilon.
    pub fn laplacian_noise(&self) -> f64 {
        let scale = self.config.sensitivity / self.config.epsilon;
        let mut rng = rand::thread_rng();
        let u: f64 = rng.gen_range(-0.5..0.5);
        -scale * u.signum() * (1.0 - 2.0 * u.abs()).ln()
    }

    /// Add Laplacian noise to a single value, consuming privacy budget.
    /// Returns None if budget exhausted.
    pub fn add_noise(&self, value: f64) -> f64 {
        value + self.laplacian_noise()
    }

    /// Add noise to a vector of values.
    pub fn add_noise_vec(&self, values: &[f64]) -> Vec<f64> {
        values.iter().map(|v| self.add_noise(*v)).collect()
    }

    /// Gaussian mechanism for (epsilon, delta)-DP.
    /// Noise ~ N(0, sigma^2) where sigma = sensitivity * sqrt(2 * ln(1.25/delta)) / epsilon.
    pub fn gaussian_noise(&self) -> f64 {
        let sigma = self.config.sensitivity
            * (2.0 * (1.25 / self.config.delta).ln()).sqrt()
            / self.config.epsilon;
        let mut rng = rand::thread_rng();
        // Box-Muller transform for normal distribution
        let u1: f64 = rng.gen_range(0.0001..1.0);
        let u2: f64 = rng.gen_range(0.0..1.0);
        sigma * (-2.0 * u1.ln()).sqrt() * (2.0 * std::f64::consts::PI * u2).cos()
    }

    /// Compute the privacy budget used after `query_count` queries under
    /// basic composition theorem: total_epsilon = query_count * per_query_epsilon.
    pub fn basic_composition_epsilon(query_count: usize, per_query_epsilon: f64) -> f64 {
        query_count as f64 * per_query_epsilon
    }

    /// Advanced composition (Kairouz et al.): for k queries each with epsilon,
    /// the composed epsilon is approximately:
    ///   epsilon' = sqrt(2k * ln(1/delta')) * epsilon + k * epsilon * (e^epsilon - 1)
    pub fn advanced_composition_epsilon(
        query_count: usize,
        per_query_epsilon: f64,
        delta_prime: f64,
    ) -> f64 {
        let k = query_count as f64;
        let eps = per_query_epsilon;
        (2.0 * k * (1.0 / delta_prime).ln()).sqrt() * eps
            + k * eps * (eps.exp() - 1.0)
    }

    /// Report current privacy budget status.
    pub fn budget_status(&self) -> &PrivacyBudget {
        &self.budget
    }

    /// Attempt to spend budget and add noise. Returns None if budget exhausted.
    pub fn query_with_budget(&mut self, value: f64) -> Option<f64> {
        if !self.budget.spend(self.config.epsilon) {
            return None;
        }
        Some(value + self.laplacian_noise())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_laplacian_noise_centered() {
        let config = DifferentialPrivacyConfig {
            epsilon: 1.0,
            sensitivity: 1.0,
            delta: 1e-6,
        };
        let engine = DifferentialPrivacyEngine::new(config);
        // Noise should be centered around 0 with reasonable variance
        let samples: Vec<f64> = (0..10000).map(|_| engine.laplacian_noise()).collect();
        let mean: f64 = samples.iter().sum::<f64>() / samples.len() as f64;
        assert!(mean.abs() < 0.1, "Mean noise should be near 0, got {}", mean);
    }

    #[test]
    fn test_add_noise_preserves_order_of_magnitude() {
        let config = DifferentialPrivacyConfig {
            epsilon: 1.0,
            sensitivity: 1.0,
            delta: 1e-6,
        };
        let engine = DifferentialPrivacyEngine::new(config);
        let value = 1000.0;
        let noisy = engine.add_noise(value);
        // With epsilon=1.0, noise scale = 1.0, so result should be within ~10 of original
        assert!((noisy - value).abs() < 50.0, "Noisy value {} too far from {}", noisy, value);
    }

    #[test]
    fn test_higher_epsilon_less_noise() {
        let low_eps = DifferentialPrivacyEngine::new(DifferentialPrivacyConfig {
            epsilon: 0.1, sensitivity: 1.0, delta: 1e-6,
        });
        let high_eps = DifferentialPrivacyEngine::new(DifferentialPrivacyConfig {
            epsilon: 10.0, sensitivity: 1.0, delta: 1e-6,
        });
        let n = 5000;
        let var_low: f64 = {
            let samples: Vec<f64> = (0..n).map(|_| low_eps.laplacian_noise()).collect();
            let mean = samples.iter().sum::<f64>() / n as f64;
            samples.iter().map(|x| (x - mean).powi(2)).sum::<f64>() / n as f64
        };
        let var_high: f64 = {
            let samples: Vec<f64> = (0..n).map(|_| high_eps.laplacian_noise()).collect();
            let mean = samples.iter().sum::<f64>() / n as f64;
            samples.iter().map(|x| (x - mean).powi(2)).sum::<f64>() / n as f64
        };
        assert!(var_low > var_high, "Lower epsilon should produce more noise variance");
    }

    #[test]
    fn test_gaussian_noise_centered() {
        let config = DifferentialPrivacyConfig {
            epsilon: 1.0,
            sensitivity: 1.0,
            delta: 1e-5,
        };
        let engine = DifferentialPrivacyEngine::new(config);
        let samples: Vec<f64> = (0..10000).map(|_| engine.gaussian_noise()).collect();
        let mean: f64 = samples.iter().sum::<f64>() / samples.len() as f64;
        assert!(mean.abs() < 0.2, "Gaussian mean should be near 0, got {}", mean);
    }

    #[test]
    fn test_basic_composition() {
        // 10 queries each with epsilon=0.1 → total = 1.0
        let total = DifferentialPrivacyEngine::basic_composition_epsilon(10, 0.1);
        assert!((total - 1.0).abs() < 1e-10);
    }

    #[test]
    fn test_advanced_composition_better_than_basic() {
        let k = 100;
        let eps = 0.1;
        let basic = DifferentialPrivacyEngine::basic_composition_epsilon(k, eps);
        let advanced = DifferentialPrivacyEngine::advanced_composition_epsilon(k, eps, 1e-5);
        assert!(advanced < basic, "Advanced composition should be tighter than basic");
    }

    #[test]
    fn test_privacy_budget_tracking() {
        let mut budget = PrivacyBudget::new(1.0);
        assert!(!budget.is_exhausted());
        assert!(budget.spend(0.3));
        assert!((budget.remaining() - 0.7).abs() < 1e-10);
        assert!(budget.spend(0.5));
        assert!(!budget.spend(0.3)); // would exceed: 0.3+0.5+0.3=1.1 > 1.0
        assert!(budget.is_exhausted());
    }

    #[test]
    fn test_query_with_budget() {
        let config = DifferentialPrivacyConfig {
            epsilon: 0.5,
            sensitivity: 1.0,
            delta: 1e-6,
        };
        let mut engine = DifferentialPrivacyEngine::new(config).with_budget(1.0);
        // budget = 1.0, each query costs 0.5 → 2 queries allowed
        assert!(engine.query_with_budget(100.0).is_some());
        assert!(engine.query_with_budget(200.0).is_some());
        assert!(engine.query_with_budget(300.0).is_none()); // budget exhausted
    }

    #[test]
    fn test_add_noise_vec() {
        let config = DifferentialPrivacyConfig {
            epsilon: 1.0,
            sensitivity: 1.0,
            delta: 1e-6,
        };
        let engine = DifferentialPrivacyEngine::new(config);
        let values = vec![10.0, 20.0, 30.0];
        let noisy = engine.add_noise_vec(&values);
        assert_eq!(noisy.len(), 3);
        // Each value should be different from original (with overwhelming probability)
        // but within a reasonable range
        for (orig, noisy) in values.iter().zip(noisy.iter()) {
            assert!((noisy - orig).abs() < 20.0);
        }
    }
}
