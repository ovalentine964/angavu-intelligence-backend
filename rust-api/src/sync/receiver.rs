// Angavu Intelligence Backend — Sync Receiver
// Handles incoming sync requests from devices and returns bidirectional response.
//
// This is the main entry point for cross-repo sync:
// - Receives anonymized transaction data from devices
// - Verifies data at the sync boundary
// - Computes and returns Alama Score updates
// - Distributes model deltas, market intelligence, and alerts
// - Handles version compatibility and freshness checks

use super::freshness::FreshnessChecker;
use super::verification::SyncVerifier;
use super::version_compat::VersionCompatibilityChecker;
use super::*;
use chrono::Utc;
use std::sync::Arc;
use tokio::sync::RwLock;
use tracing::{error, info, warn};

/// State shared across sync operations
#[derive(Clone)]
pub struct SyncState {
    /// Known device states (for dedup tracking)
    pub device_states: Arc<RwLock<HashMap<String, DeviceState>>>,
    /// Verification config
    pub verifier: Arc<SyncVerifier>,
    /// Version compatibility checker
    pub version_checker: Arc<VersionCompatibilityChecker>,
    /// Freshness checker
    pub freshness_checker: Arc<FreshnessChecker>,
    /// Market data cache
    pub market_cache: Arc<RwLock<HashMap<String, MarketIntelligence>>>,
    /// Pending alerts per device
    pub pending_alerts: Arc<RwLock<HashMap<String, Vec<SyncAlert>>>>,
}

/// Per-device state for dedup and tracking
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeviceState {
    pub device_id: String,
    pub last_sync_timestamp: i64,
    pub known_dedup_keys: Vec<String>,
    pub model_version: Option<String>,
    pub last_score: Option<u16>,
    pub total_syncs: u64,
    pub total_transactions_synced: u64,
}

impl SyncState {
    pub fn new() -> Self {
        Self {
            device_states: Arc::new(RwLock::new(HashMap::new())),
            verifier: Arc::new(SyncVerifier::new()),
            version_checker: Arc::new(VersionCompatibilityChecker::new()),
            freshness_checker: Arc::new(FreshnessChecker::new()),
            market_cache: Arc::new(RwLock::new(HashMap::new())),
            pending_alerts: Arc::new(RwLock::new(HashMap::new())),
        }
    }

    /// Process a sync request — the main bidirectional sync handler.
    ///
    /// 1. Verify protocol version compatibility
    /// 2. Verify and filter incoming transactions (boundary verification)
    /// 3. Update device state (dedup tracking)
    /// 4. Compute Alama Score update for device
    /// 5. Check model version and prepare delta if needed
    /// 6. Attach market intelligence for device's ward
    /// 7. Attach any pending alerts
    /// 8. Build freshness metadata
    #[tracing::instrument(skip(self, request), fields(device_id = %request.device_id, protocol_version = request.sync_protocol_version))]
    pub async fn process_sync(&self, request: SyncRequest) -> SyncResponse {
        let now = Utc::now().timestamp_millis();

        // ── Step 1: Protocol version check ──
        if request.sync_protocol_version < MIN_SUPPORTED_PROTOCOL_VERSION {
            return SyncResponse {
                status: "error".to_string(),
                synced_count: 0,
                server_timestamp: now,
                conflicts_resolved: 0,
                message: Some(format!(
                    "Protocol version {} is too old. Minimum supported: {}",
                    request.sync_protocol_version, MIN_SUPPORTED_PROTOCOL_VERSION
                )),
                protocol_version: SYNC_PROTOCOL_VERSION,
                alama_score_update: None,
                model_delta: None,
                market_intelligence: None,
                alerts: vec![SyncAlert {
                    alert_type: "protocol_outdated".to_string(),
                    severity: "critical".to_string(),
                    title: "App update required".to_string(),
                    body: "Your app version is too old. Please update to continue syncing."
                        .to_string(),
                    timestamp: now,
                    action_url: Some(
                        "https://play.google.com/store/apps/details?id=com.msaidizi.app"
                            .to_string(),
                    ),
                }],
                freshness: FreshnessMetadata {
                    server_timestamp: now,
                    market_data_fresh: false,
                    score_data_fresh: false,
                    staleness: "unknown".to_string(),
                },
                verification: VerificationResult {
                    all_valid: false,
                    accepted_count: 0,
                    rejected_count: 0,
                    duplicate_count: 0,
                    rejection_reasons: vec![RejectionReason {
                        transaction_index: 0,
                        reason: "Protocol version too old".to_string(),
                        severity: "error".to_string(),
                    }],
                },
            };
        }

        // ── Step 2: Get or create device state ──
        let mut device_states = self.device_states.write().await;
        let device_state = device_states
            .entry(request.device_id.clone())
            .or_insert_with(|| DeviceState {
                device_id: request.device_id.clone(),
                last_sync_timestamp: 0,
                known_dedup_keys: Vec::new(),
                model_version: None,
                last_score: None,
                total_syncs: 0,
                total_transactions_synced: 0,
            });

        // ── Step 3: Boundary verification ──
        let verification = self.verifier.verify_sync(&request, device_state).await;

        // Update dedup keys with accepted transactions
        for tx in &request.transactions {
            if let Some(ref key) = tx.dedup_key {
                if !device_state.known_dedup_keys.contains(key) {
                    device_state.known_dedup_keys.push(key.clone());
                }
            }
        }
        // Keep dedup window to last 1000 keys
        if device_state.known_dedup_keys.len() > 1000 {
            let drain_count = device_state.known_dedup_keys.len() - 1000;
            device_state.known_dedup_keys.drain(..drain_count);
        }

        // Update device state
        device_state.last_sync_timestamp = now;
        device_state.total_syncs += 1;
        device_state.total_transactions_synced += verification.accepted_count as u64;
        device_state.model_version = request.model_version.clone();

        // ── Step 4: Alama Score update ──
        let alama_score_update = self.compute_score_update(&request, device_state).await;

        // ── Step 5: Model version compatibility ──
        let model_delta = self
            .version_checker
            .check_and_prepare_delta(request.model_version.as_deref())
            .await;

        // ── Step 6: Market intelligence ──
        let market_intelligence = self
            .get_market_intelligence(&request.ward, &request.business_category)
            .await;

        // ── Step 7: Pending alerts ──
        let mut alerts_cache = self.pending_alerts.write().await;
        let alerts = alerts_cache.remove(&request.device_id).unwrap_or_default();

        // ── Step 8: Freshness metadata ──
        let freshness = self
            .freshness_checker
            .check_freshness(
                request.last_server_timestamp,
                market_intelligence.as_ref(),
                alama_score_update.as_ref(),
            )
            .await;

        // Build response
        let accepted = verification.accepted_count;
        let status = if verification.rejected_count == 0 {
            "ok"
        } else if accepted > 0 {
            "partial"
        } else {
            "error"
        };

        info!(
            device_id = %request.device_id,
            accepted = accepted,
            rejected = verification.rejected_count,
            duplicates = verification.duplicate_count,
            "Sync processed"
        );

        SyncResponse {
            status: status.to_string(),
            synced_count: accepted,
            server_timestamp: now,
            conflicts_resolved: verification.duplicate_count,
            message: if verification.rejected_count > 0 {
                Some(format!(
                    "{} accepted, {} rejected, {} duplicates",
                    accepted, verification.rejected_count, verification.duplicate_count
                ))
            } else {
                None
            },
            protocol_version: SYNC_PROTOCOL_VERSION,
            alama_score_update,
            model_delta,
            market_intelligence,
            alerts,
            freshness,
            verification,
        }
    }

    /// Compute Alama Score update for a device based on their synced data
    async fn compute_score_update(
        &self,
        request: &SyncRequest,
        device_state: &DeviceState,
    ) -> Option<AlamaScoreUpdate> {
        // Only compute score if we have enough data
        if request.transactions.is_empty() && device_state.total_transactions_synced < 10 {
            return None;
        }

        let now = Utc::now().timestamp_millis();

        // Simple score estimation based on available signals
        let transaction_volume = (device_state.total_transactions_synced as f64 / 300.0).min(1.0);
        let pattern_confidence = request
            .learned_patterns
            .iter()
            .map(|p| p.confidence)
            .max_by(|a, b| a.partial_cmp(b).unwrap())
            .unwrap_or(0.0);
        let anomaly_ratio = if request.anomaly_stats.total_transactions_analyzed > 0 {
            request.anomaly_stats.anomaly_count as f64
                / request.anomaly_stats.total_transactions_analyzed as f64
        } else {
            0.0
        };

        // Score components
        let volume_score = transaction_volume * 0.3;
        let pattern_score = pattern_confidence * 0.4;
        let anomaly_penalty = anomaly_ratio * 0.3;
        let raw_score = (volume_score + pattern_score - anomaly_penalty).clamp(0.0, 1.0);

        // Map to 300-850 range
        let alama_score = (300.0 + raw_score * 550.0).round() as u16;
        let alama_score = alama_score.clamp(300, 850);

        let factors = vec![
            ScoreFactorUpdate {
                name: "transaction_volume".to_string(),
                impact: volume_score - 0.15,
                weight: 0.3,
                description: format!(
                    "{} total transactions synced",
                    device_state.total_transactions_synced
                ),
            },
            ScoreFactorUpdate {
                name: "pattern_consistency".to_string(),
                impact: pattern_score - 0.2,
                weight: 0.4,
                description: format!(
                    "Best pattern confidence: {:.0}%",
                    pattern_confidence * 100.0
                ),
            },
            ScoreFactorUpdate {
                name: "anomaly_rate".to_string(),
                impact: -anomaly_penalty,
                weight: 0.3,
                description: format!(
                    "{:.1}% anomaly rate ({} / {})",
                    anomaly_ratio * 100.0,
                    request.anomaly_stats.anomaly_count,
                    request.anomaly_stats.total_transactions_analyzed
                ),
            },
        ];

        Some(AlamaScoreUpdate {
            score: alama_score,
            factors,
            confidence: (0.5 + device_state.total_syncs as f64 * 0.05).min(0.95),
            computed_at: now,
        })
    }

    /// Get market intelligence for a ward/category
    async fn get_market_intelligence(
        &self,
        ward: &str,
        business_category: &str,
    ) -> Option<MarketIntelligence> {
        let cache = self.market_cache.read().await;
        cache.get(ward).cloned().or_else(|| {
            // Generate synthetic market data if not cached
            let now = Utc::now().timestamp_millis();
            let mut price_trends = HashMap::new();
            price_trends.insert(
                business_category.to_string(),
                PriceTrend {
                    category: business_category.to_string(),
                    current_avg_price: 0.0,
                    week_over_week_change: 0.0,
                    direction: "stable".to_string(),
                },
            );
            Some(MarketIntelligence {
                ward: ward.to_string(),
                price_trends,
                demand_signals: vec![],
                data_timestamp: now,
                ttl_seconds: 3600,
            })
        })
    }
}

/// Axum handler for POST /api/v1/sync/anonymized
/// Extracts SyncState from GatewayState
#[tracing::instrument(skip(gateway, request), fields(device_id = %request.device_id))]
pub async fn handle_sync(
    axum::extract::State(gateway): axum::extract::State<super::super::GatewayState>,
    axum::extract::Json(request): axum::extract::Json<SyncRequest>,
) -> axum::response::Json<SyncResponse> {
    let response = gateway.sync_state.process_sync(request).await;
    axum::response::Json(response)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample_sync_request() -> SyncRequest {
        SyncRequest {
            device_id: "test-device-001".to_string(),
            business_category: "Trade".to_string(),
            ward: "Nairobi Central".to_string(),
            transactions: vec![
                AnonymizedTransaction {
                    amount_bucket: "500-1000".to_string(),
                    category: "sale".to_string(),
                    payment_method: "cash".to_string(),
                    hour_of_day: 14,
                    day_of_week: 3,
                    is_service: false,
                    dedup_key: Some("tx-001".to_string()),
                },
                AnonymizedTransaction {
                    amount_bucket: "100-500".to_string(),
                    category: "expense".to_string(),
                    payment_method: "mpesa".to_string(),
                    hour_of_day: 10,
                    day_of_week: 3,
                    is_service: false,
                    dedup_key: Some("tx-002".to_string()),
                },
            ],
            learned_patterns: vec![AnonymizedPattern {
                pattern_type: "consistent_sales".to_string(),
                confidence: 0.8,
                occurrence_count: 15,
            }],
            vocabulary_hashes: vec!["abc123".to_string()],
            anomaly_stats: AnomalyStats {
                total_transactions_analyzed: 100,
                anomaly_count: 5,
                mean_amount: 500.0,
                std_dev: 200.0,
            },
            timestamp: Utc::now().timestamp_millis(),
            sync_protocol_version: SYNC_PROTOCOL_VERSION,
            model_version: Some("2.0.0".to_string()),
            last_server_timestamp: None,
        }
    }

    #[tokio::test]
    async fn test_basic_sync_returns_bidirectional_data() {
        let state = SyncState::new();
        let request = sample_sync_request();
        let response = state.process_sync(request).await;

        assert_eq!(response.status, "ok");
        assert_eq!(response.synced_count, 2);
        assert!(response.alama_score_update.is_some());
        assert!(response.market_intelligence.is_some());
        assert_eq!(response.protocol_version, SYNC_PROTOCOL_VERSION);
    }

    #[tokio::test]
    async fn test_duplicate_detection() {
        let state = SyncState::new();
        let request = sample_sync_request();

        // First sync
        let resp1 = state.process_sync(request.clone()).await;
        assert_eq!(resp1.synced_count, 2);
        assert_eq!(resp1.verification.duplicate_count, 0);

        // Second sync with same dedup keys
        let resp2 = state.process_sync(request).await;
        assert_eq!(resp2.synced_count, 0);
        assert_eq!(resp2.verification.duplicate_count, 2);
    }

    #[tokio::test]
    async fn test_old_protocol_rejected() {
        let state = SyncState::new();
        let mut request = sample_sync_request();
        request.sync_protocol_version = 0;

        let response = state.process_sync(request).await;
        assert_eq!(response.status, "error");
        assert!(response.message.unwrap().contains("too old"));
    }

    #[tokio::test]
    async fn test_score_computed_after_sync() {
        let state = SyncState::new();
        let request = sample_sync_request();
        let response = state.process_sync(request).await;

        let score = response.alama_score_update.unwrap();
        assert!(score.score >= 300 && score.score <= 850);
        assert!(score.confidence > 0.0);
        assert!(!score.factors.is_empty());
    }

    #[tokio::test]
    async fn test_freshness_metadata_present() {
        let state = SyncState::new();
        let request = sample_sync_request();
        let response = state.process_sync(request).await;

        assert!(response.freshness.server_timestamp > 0);
        assert!(!response.freshness.staleness.is_empty());
    }
}
