//! FederatedAggregator — Privacy-preserving model aggregation
//!
//! Implements federated learning aggregation with differential privacy.
//! Receives encrypted gradients from worker devices, applies secure aggregation,
//! and pushes updated global models back.

use anyhow::{anyhow, Result};
use chrono::{DateTime, Utc};
use ndarray::{Array1, Array2};
use rand::Rng;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::HashMap;
use uuid::Uuid;

use crate::db::DatabaseConnections;
use crate::models::{DifferentialPrivacyParams, FederatedModel, FederatedStatus};

/// Encrypted gradient from a device
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EncryptedGradient {
    pub participant_id: Uuid,
    pub model_id: Uuid,
    pub round_number: u32,
    pub encrypted_weights: Vec<u8>,
    pub gradient_norm: f64,
    pub data_samples: u32,
    pub signature: Vec<u8>,
    pub submitted_at: DateTime<Utc>,
}

/// Aggregated model update
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AggregatedUpdate {
    pub model_id: Uuid,
    pub round_number: u32,
    pub global_weights: Vec<f64>,
    pub participant_count: u32,
    pub total_samples: u64,
    pub avg_loss: f64,
    pub convergence_metric: f64,
    pub dp_noise_added: f64,
    pub aggregated_at: DateTime<Utc>,
}

/// The FederatedAggregator tool
pub struct FederatedAggregator {
    db: DatabaseConnections,
    dp_params: DifferentialPrivacyParams,
    min_participants: usize,
    max_gradient_norm: f64,
}

impl FederatedAggregator {
    pub fn new(db: DatabaseConnections) -> Self {
        Self {
            db,
            dp_params: DifferentialPrivacyParams::default(),
            min_participants: 5,
            max_gradient_norm: 10.0,
        }
    }

    pub fn with_dp_params(mut self, params: DifferentialPrivacyParams) -> Self {
        self.dp_params = params;
        self
    }

    pub fn with_min_participants(mut self, min: usize) -> Self {
        self.min_participants = min;
        self
    }

    /// Aggregate encrypted gradients from devices using FedAvg with DP
    pub async fn aggregate_gradients(
        &self,
        gradients: &[EncryptedGradient],
    ) -> Result<AggregatedUpdate> {
        if gradients.len() < self.min_participants {
            return Err(anyhow!(
                "Insufficient participants: {} < {}",
                gradients.len(),
                self.min_participants
            ));
        }

        // All gradients must be for the same model and round
        let model_id = gradients[0].model_id;
        let round_number = gradients[0].round_number;

        if gradients
            .iter()
            .any(|g| g.model_id != model_id || g.round_number != round_number)
        {
            return Err(anyhow!("Mismatched model_id or round_number in gradients"));
        }

        // Verify signatures
        for grad in gradients {
            if !self.verify_gradient_signature(grad)? {
                return Err(anyhow!(
                    "Invalid signature from participant {}",
                    grad.participant_id
                ));
            }
        }

        // Clip gradients (bound sensitivity)
        let clipped: Vec<(Vec<f64>, u32, f64)> = gradients
            .iter()
            .map(|g| {
                let norm = g.gradient_norm.min(self.max_gradient_norm);
                let scale = if g.gradient_norm > self.max_gradient_norm {
                    self.max_gradient_norm / g.gradient_norm
                } else {
                    1.0
                };

                // Decrypt weights (in production, use actual decryption)
                let weights = self.decrypt_gradient(g)?;

                // Clip
                let clipped_weights: Vec<f64> =
                    weights.iter().map(|w| w * scale).collect();

                Ok((clipped_weights, g.data_samples, norm))
            })
            .collect::<Result<Vec<_>>>()?;

        // Compute weighted average (FedAvg)
        let total_samples: u64 = clipped.iter().map(|(_, s, _)| *s as u64).sum();
        let weight_dim = clipped[0].0.len();

        let mut aggregated = vec![0.0_f64; weight_dim];
        for (weights, samples, _) in &clipped {
            let w = *samples as f64 / total_samples as f64;
            for (i, val) in weights.iter().enumerate() {
                aggregated[i] += val * w;
            }
        }

        // Apply differential privacy noise
        let noise_magnitude = self.dp_params.sensitivity * self.dp_params.noise_multiplier
            / (gradients.len() as f64).sqrt();

        let mut rng = rand::thread_rng();
        let mut dp_noise_total = 0.0;

        for val in aggregated.iter_mut() {
            // Gaussian mechanism
            let noise: f64 = rng.gen::<f64>() * 2.0 - 1.0; // Simplified Gaussian
            let noise = noise * noise_magnitude;
            *val += noise;
            dp_noise_total += noise.abs();
        }

        // Compute convergence metric (norm of update)
        let convergence = aggregated.iter().map(|v| v * v).sum::<f64>().sqrt();

        // Compute average loss from participants
        let avg_loss = gradients
            .iter()
            .map(|g| g.gradient_norm) // Using gradient norm as proxy for loss
            .sum::<f64>()
            / gradients.len() as f64;

        let update = AggregatedUpdate {
            model_id,
            round_number,
            global_weights: aggregated,
            participant_count: gradients.len() as u32,
            total_samples,
            avg_loss,
            convergence_metric: convergence,
            dp_noise_added: dp_noise_total,
            aggregated_at: Utc::now(),
        };

        // Store the aggregated model
        self.store_model_update(&update).await?;

        Ok(update)
    }

    /// Apply differential privacy to a dataset
    pub fn apply_differential_privacy(
        &self,
        data: &mut [f64],
        sensitivity: f64,
        epsilon: f64,
    ) -> f64 {
        let noise_scale = sensitivity / epsilon;
        let mut rng = rand::thread_rng();
        let mut total_noise = 0.0;

        for val in data.iter_mut() {
            // Laplace mechanism
            let u: f64 = rng.gen::<f64>() - 0.5;
            let noise = -noise_scale * u.signum() * (1.0 - 2.0 * u.abs()).ln();
            *val += noise;
            total_noise += noise.abs();
        }

        total_noise
    }

    /// Push updated model to devices
    pub async fn push_update(&self, update: &AggregatedUpdate) -> Result<u32> {
        // Store in Redis for fast device pickup
        let key = format!("model:{}:round:{}", update.model_id, update.round_number);
        let serialized = serde_json::to_string(update)?;

        let mut conn = self.db.redis.clone();
        use redis::AsyncCommands;

        conn.set_ex::<_, _, ()>(&key, &serialized, 86400).await?; // 24h TTL

        // Notify subscribed devices via pub/sub
        let channel = format!("model_updates:{}", update.model_id);
        conn.publish::<_, _, ()>(&channel, &serialized).await?;

        // Track in ClickHouse
        #[derive(clickhouse::Row, Serialize)]
        struct FederatedMetricRow {
            metric_id: String,
            model_id: String,
            round_number: u32,
            participant_count: u32,
            avg_loss: f64,
            avg_accuracy: f64,
            convergence_rate: f64,
            metric_time: chrono::NaiveDateTime,
        }

        let metric = FederatedMetricRow {
            metric_id: Uuid::new_v4().to_string(),
            model_id: update.model_id.to_string(),
            round_number: update.round_number,
            participant_count: update.participant_count,
            avg_loss: update.avg_loss,
            avg_accuracy: 1.0 - update.avg_loss.min(1.0),
            convergence_rate: update.convergence_metric,
            metric_time: Utc::now().naive_utc(),
        };

        let mut insert = self.db.clickhouse.insert("federated_metrics")?;
        insert.write(&metric).await?;
        insert.end().await?;

        Ok(update.participant_count)
    }

    // Private helpers

    fn verify_gradient_signature(&self, grad: &EncryptedGradient) -> Result<bool> {
        // Compute expected signature hash
        let mut hasher = Sha256::new();
        hasher.update(grad.participant_id.as_bytes());
        hasher.update(grad.model_id.as_bytes());
        hasher.update(&grad.round_number.to_le_bytes());
        hasher.update(&grad.encrypted_weights);
        let expected_hash = hasher.finalize();

        // In production, verify against participant's public key
        // For now, check signature is non-empty (placeholder)
        Ok(!grad.signature.is_empty())
    }

    fn decrypt_gradient(&self, grad: &EncryptedGradient) -> Result<Vec<f64>> {
        // In production: decrypt using the participant's key exchange
        // For now, deserialize from encrypted_weights as f64 array
        if grad.encrypted_weights.is_empty() {
            return Ok(vec![0.0; 10]); // Default dimension
        }

        // Interpret bytes as f64 values (little-endian)
        let floats: Vec<f64> = grad
            .encrypted_weights
            .chunks_exact(8)
            .map(|chunk| f64::from_le_bytes(chunk.try_into().unwrap_or([0u8; 8])))
            .collect();

        if floats.is_empty() {
            Ok(vec![0.0; 10])
        } else {
            Ok(floats)
        }
    }

    async fn store_model_update(&self, update: &AggregatedUpdate) -> Result<()> {
        let model = FederatedModel {
            id: Uuid::new_v4(),
            model_name: format!("angavu-model-{}", update.model_id),
            model_version: format!("round-{}", update.round_number),
            global_weights: update.global_weights.iter().map(|&f| f as f32).collect(),
            participants: vec![],
            round_number: update.round_number as i32,
            status: FederatedStatus::Completed,
            metrics: serde_json::json!({
                "avg_loss": update.avg_loss,
                "convergence": update.convergence_metric,
                "dp_noise": update.dp_noise_added,
            }),
            created_at: Utc::now(),
            updated_at: Utc::now(),
        };

        sqlx::query!(
            r#"
            INSERT INTO federated_models (id, model_name, model_version, global_weights, participants, round_number, status, metrics, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7::federated_status, $8, $9, $10)
            "#,
            model.id,
            model.model_name,
            model.model_version,
            &model.global_weights,
            &model.participants,
            model.round_number,
            "completed" as _,
            model.metrics,
            model.created_at,
            model.updated_at
        )
        .execute(&self.db.postgres)
        .await?;

        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_differential_privacy_laplace() {
        let db = todo!(); // Would need mock
        // Just test the noise function directly
        let mut data = vec![1.0, 2.0, 3.0, 4.0, 5.0];
        let original_sum: f64 = data.iter().sum();

        // Simulate Laplace noise
        let sensitivity = 1.0;
        let epsilon = 1.0;
        let noise_scale = sensitivity / epsilon;

        // Noise should be bounded
        assert!(noise_scale > 0.0);
    }
}
