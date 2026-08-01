// Angavu Intelligence Backend — Cross-Repo Sync Module
// Handles bidirectional sync between msaidizi-app and angavu-intelligence-backend
//
// Features:
// - Bidirectional sync (push + pull)
// - Sync boundary verification (dedup, plausibility, validation)
// - Model version compatibility checks
// - Data freshness checks
// - Alama Score distribution back to devices

pub mod receiver;
pub mod verification;
pub mod version_compat;
pub mod freshness;
pub mod integration_tests;

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Current sync protocol version
pub const SYNC_PROTOCOL_VERSION: u32 = 2;

/// Minimum supported protocol version
pub const MIN_SUPPORTED_PROTOCOL_VERSION: u32 = 1;

/// Maximum model version the backend can serve
pub const CURRENT_MODEL_VERSION: &str = "2.1.0";

/// Minimum model version compatible with current backend
pub const MIN_MODEL_VERSION: &str = "1.5.0";

// ─── Incoming Sync Payload (from device) ───
// Kotlin serialization uses camelCase by default, so we rename all fields
// to match the app's JSON format.

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SyncRequest {
    /// Anonymous device fingerprint
    pub device_id: String,
    /// Business category
    pub business_category: String,
    /// Ward-level location
    pub ward: String,
    /// Anonymized transactions
    pub transactions: Vec<AnonymizedTransaction>,
    /// Learned patterns
    pub learned_patterns: Vec<AnonymizedPattern>,
    /// Vocabulary hashes
    pub vocabulary_hashes: Vec<String>,
    /// Aggregated anomaly stats
    pub anomaly_stats: AnomalyStats,
    /// Client timestamp (ms since epoch)
    pub timestamp: i64,
    /// Sync protocol version
    pub sync_protocol_version: u32,
    /// Device's current model version
    pub model_version: Option<String>,
    /// Last known server timestamp (for freshness)
    pub last_server_timestamp: Option<i64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AnonymizedTransaction {
    pub amount_bucket: String,
    pub category: String,
    pub payment_method: String,
    pub hour_of_day: u8,
    pub day_of_week: u8,
    pub is_service: bool,
    /// Unique dedup key (hash of timestamp + amount + category)
    #[serde(default)]
    pub dedup_key: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AnonymizedPattern {
    pub pattern_type: String,
    pub confidence: f64,
    pub occurrence_count: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AnomalyStats {
    pub total_transactions_analyzed: u32,
    pub anomaly_count: u32,
    pub mean_amount: f64,
    pub std_dev: f64,
}

// ─── Sync Response (returned to device) ───

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SyncResponse {
    /// Overall status: "ok", "partial", "error"
    pub status: String,
    /// Number of transactions accepted
    pub synced_count: u32,
    /// Server timestamp
    pub server_timestamp: i64,
    /// Conflicts resolved
    pub conflicts_resolved: u32,
    /// Optional message
    pub message: Option<String>,
    /// Protocol version used
    pub protocol_version: u32,

    // ── Bidirectional: data flowing back to device ──
    /// Alama Score update for this device (if available)
    pub alama_score_update: Option<AlamaScoreUpdate>,
    /// Model delta/patch (if device model is outdated)
    pub model_delta: Option<ModelDelta>,
    /// Market intelligence for the device's ward/category
    pub market_intelligence: Option<MarketIntelligence>,
    /// Alerts for this device
    pub alerts: Vec<SyncAlert>,
    /// Freshness metadata
    pub freshness: FreshnessMetadata,
    /// Verification results
    pub verification: VerificationResult,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AlamaScoreUpdate {
    /// Updated Alama Score (300-850)
    pub score: u16,
    /// Score factors for explainability
    pub factors: Vec<ScoreFactorUpdate>,
    /// Confidence level
    pub confidence: f64,
    /// Timestamp of the score computation
    pub computed_at: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ScoreFactorUpdate {
    pub name: String,
    pub impact: f64,
    pub weight: f64,
    pub description: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ModelDelta {
    /// Target model version
    pub target_version: String,
    /// Whether this is a full model or a delta patch
    pub is_full_model: bool,
    /// URL to download the model/delta
    pub download_url: String,
    /// SHA-256 checksum
    pub checksum: String,
    /// Size in bytes
    pub size_bytes: u64,
    /// Minimum protocol version required
    pub min_protocol_version: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct MarketIntelligence {
    /// Ward-specific data
    pub ward: String,
    /// Price trends by category
    pub price_trends: HashMap<String, PriceTrend>,
    /// Demand signals
    pub demand_signals: Vec<DemandSignal>,
    /// Data timestamp
    pub data_timestamp: i64,
    /// TTL in seconds
    pub ttl_seconds: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PriceTrend {
    pub category: String,
    pub current_avg_price: f64,
    pub week_over_week_change: f64,
    pub direction: String, // "rising", "falling", "stable"
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct DemandSignal {
    pub category: String,
    pub demand_level: String, // "high", "medium", "low"
    pub confidence: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SyncAlert {
    pub alert_type: String, // "score_change", "market_shift", "model_update", "verification_issue"
    pub severity: String,   // "info", "warning", "critical"
    pub title: String,
    pub body: String,
    pub timestamp: i64,
    pub action_url: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct FreshnessMetadata {
    /// Server timestamp when data was last updated
    pub server_timestamp: i64,
    /// Whether market data is fresh (< 1 hour old)
    pub market_data_fresh: bool,
    /// Whether score data is fresh (< 24 hours old)
    pub score_data_fresh: bool,
    /// Staleness indicator: "fresh", "stale", "very_stale"
    pub staleness: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct VerificationResult {
    /// Whether all transactions passed verification
    pub all_valid: bool,
    /// Number of transactions accepted
    pub accepted_count: u32,
    /// Number of transactions rejected
    pub rejected_count: u32,
    /// Number of duplicates detected
    pub duplicate_count: u32,
    /// Rejection reasons (if any)
    pub rejection_reasons: Vec<RejectionReason>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct RejectionReason {
    pub transaction_index: usize,
    pub reason: String,
    pub severity: String, // "warning", "error"
}
