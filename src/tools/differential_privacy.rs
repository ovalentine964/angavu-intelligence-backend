use serde::{Deserialize, Serialize};
use rand::Rng;

#[derive(Debug, Serialize, Deserialize)]
pub struct DifferentialPrivacyConfig {
    pub epsilon: f64,
    pub sensitivity: f64,
}

impl Default for DifferentialPrivacyConfig {
    fn default() -> Self {
        Self { epsilon: 0.1, sensitivity: 1.0 }
    }
}

pub struct DifferentialPrivacyEngine {
    config: DifferentialPrivacyConfig,
}

impl DifferentialPrivacyEngine {
    pub fn new(config: DifferentialPrivacyConfig) -> Self { Self { config } }

    pub fn add_noise(&self, value: f64) -> f64 {
        let scale = self.config.sensitivity / self.config.epsilon;
        let mut rng = rand::thread_rng();
        // Laplacian noise
        let u: f64 = rng.gen_range(-0.5..0.5);
        let noise = -scale * u.signum() * (1.0 - 2.0 * u.abs()).ln();
        value + noise
    }

    pub fn add_noise_vec(&self, values: &[f64]) -> Vec<f64> {
        values.iter().map(|v| self.add_noise(*v)).collect()
    }

    pub fn privacy_budget_used(&self, query_count: usize) -> f64 {
        query_count as f64 * self.config.epsilon
    }
}
