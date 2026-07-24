use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

/// Device sync status
#[derive(Debug, Clone, Serialize, Deserialize, sqlx::FromRow)]
pub struct DeviceSync {
    pub id: Uuid,
    pub user_id: Uuid,
    pub device_id: String,
    pub device_type: String,
    pub device_name: String,
    pub last_sync: DateTime<Utc>,
    pub sync_version: i64,
    pub status: SyncStatus,
    pub metadata: serde_json::Value,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum SyncStatus {
    Synced,
    Pending,
    Conflict,
    Error,
}

/// Sync payload
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SyncPayload {
    pub device_id: String,
    pub last_sync_version: i64,
    pub changes: Vec<SyncChange>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SyncChange {
    pub entity_type: String,
    pub entity_id: Uuid,
    pub operation: SyncOperation,
    pub data: serde_json::Value,
    pub version: i64,
    pub timestamp: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum SyncOperation {
    Create,
    Update,
    Delete,
}

/// Sync response
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SyncResponse {
    pub current_version: i64,
    pub changes: Vec<SyncChange>,
    pub conflicts: Vec<SyncConflict>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SyncConflict {
    pub entity_type: String,
    pub entity_id: Uuid,
    pub local_version: serde_json::Value,
    pub remote_version: serde_json::Value,
    pub resolution: ConflictResolution,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum ConflictResolution {
    LocalWins,
    RemoteWins,
    Merge,
    Manual,
}

/// Federated learning
#[derive(Debug, Clone, Serialize, Deserialize, sqlx::FromRow)]
pub struct FederatedModel {
    pub id: Uuid,
    pub model_name: String,
    pub model_version: String,
    pub global_weights: Vec<f32>,
    pub participants: Vec<Uuid>,
    pub round_number: i32,
    pub status: FederatedStatus,
    pub metrics: serde_json::Value,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum FederatedStatus {
    Collecting,
    Aggregating,
    Distributing,
    Completed,
    Failed,
}

/// Federated learning participant
#[derive(Debug, Clone, Serialize, Deserialize, sqlx::FromRow)]
pub struct FederatedParticipant {
    pub id: Uuid,
    pub model_id: Uuid,
    pub user_id: Uuid,
    pub device_id: String,
    pub local_weights: Option<Vec<f32>>,
    pub gradient_norm: Option<f64>,
    pub data_samples: i32,
    pub status: ParticipantStatus,
    pub submitted_at: Option<DateTime<Utc>>,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum ParticipantStatus {
    Invited,
    Training,
    Submitted,
    Aggregated,
    Dropped,
}

/// Differential privacy parameters
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DifferentialPrivacyParams {
    pub epsilon: f64,
    pub delta: f64,
    pub sensitivity: f64,
    pub noise_multiplier: f64,
    pub clip_norm: f64,
}

impl Default for DifferentialPrivacyParams {
    fn default() -> Self {
        Self {
            epsilon: 1.0,
            delta: 1e-5,
            sensitivity: 1.0,
            noise_multiplier: 1.1,
            clip_norm: 1.0,
        }
    }
}

/// Federated learning round
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FederatedRound {
    pub round_id: Uuid,
    pub model_id: Uuid,
    pub round_number: i32,
    pub participants: Vec<Uuid>,
    pub aggregated_weights: Vec<f32>,
    pub metrics: FederatedMetrics,
    pub dp_params: DifferentialPrivacyParams,
    pub started_at: DateTime<Utc>,
    pub completed_at: Option<DateTime<Utc>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FederatedMetrics {
    pub avg_loss: f64,
    pub avg_accuracy: f64,
    pub convergence_rate: f64,
    pub participant_count: i32,
    pub total_samples: i64,
}
