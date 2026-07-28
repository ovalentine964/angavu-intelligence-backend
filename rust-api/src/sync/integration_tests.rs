// Angavu Intelligence Backend — Cross-Repo Sync Integration Tests
// Tests the full bidirectional sync flow end-to-end.
//
// Covers all 5 fixes:
// FIX 1: Bidirectional sync (push + pull)
// FIX 2: Sync boundary verification
// FIX 3: Offline queue draining (simulated)
// FIX 4: Model version compatibility
// FIX 5: Data freshness checks

use crate::sync::*;
use crate::sync::receiver::{SyncState, DeviceState};
use crate::sync::verification::SyncVerifier;
use crate::sync::version_compat::VersionCompatibilityChecker;
use crate::sync::freshness::FreshnessChecker;
use chrono::Utc;

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
        model_version: Some("2.1.0".to_string()),
        last_server_timestamp: None,
    }
}

// ── FIX 1: Bidirectional Sync Tests ──

#[tokio::test]
async fn test_bidirectional_sync_returns_alama_score() {
    let state = SyncState::new();
    let request = sample_sync_request();
    let response = state.process_sync(request).await;

    assert_eq!(response.status, "ok");
    assert!(response.alama_score_update.is_some());

    let score = response.alama_score_update.unwrap();
    assert!(score.score >= 300 && score.score <= 850);
    assert!(score.confidence > 0.0);
    assert!(!score.factors.is_empty());
}

#[tokio::test]
async fn test_bidirectional_sync_returns_market_intelligence() {
    let state = SyncState::new();
    let request = sample_sync_request();
    let response = state.process_sync(request).await;

    assert!(response.market_intelligence.is_some());
    let market = response.market_intelligence.unwrap();
    assert_eq!(market.ward, "Nairobi Central");
}

#[tokio::test]
async fn test_bidirectional_sync_returns_freshness_metadata() {
    let state = SyncState::new();
    let request = sample_sync_request();
    let response = state.process_sync(request).await;

    assert!(response.freshness.server_timestamp > 0);
    assert!(!response.freshness.staleness.is_empty());
}

// ── FIX 2: Boundary Verification Tests ──

#[tokio::test]
async fn test_invalid_category_rejected_at_boundary() {
    let state = SyncState::new();
    let mut request = sample_sync_request();
    request.transactions.push(AnonymizedTransaction {
        amount_bucket: "100-500".to_string(),
        category: "INVALID_CATEGORY".to_string(),
        payment_method: "cash".to_string(),
        hour_of_day: 12,
        day_of_week: 3,
        is_service: false,
        dedup_key: Some("tx-invalid".to_string()),
    });

    let response = state.process_sync(request).await;
    assert_eq!(response.status, "partial");
    assert_eq!(response.verification.rejected_count, 1);
    assert_eq!(response.verification.accepted_count, 2);
}

#[tokio::test]
async fn test_duplicate_detection_at_boundary() {
    let state = SyncState::new();
    let request = sample_sync_request();

    // First sync
    let resp1 = state.process_sync(request.clone()).await;
    assert_eq!(resp1.verification.duplicate_count, 0);

    // Second sync with same dedup keys
    let resp2 = state.process_sync(request).await;
    assert_eq!(resp2.verification.duplicate_count, 2);
    assert_eq!(resp2.synced_count, 0);
}

#[tokio::test]
async fn test_invalid_payment_method_rejected() {
    let state = SyncState::new();
    let mut request = sample_sync_request();
    request.transactions[0].payment_method = "bitcoin".to_string();

    let response = state.process_sync(request).await;
    assert_eq!(response.verification.rejected_count, 1);
}

#[tokio::test]
async fn test_invalid_hour_rejected() {
    let state = SyncState::new();
    let mut request = sample_sync_request();
    request.transactions[0].hour_of_day = 25;

    let response = state.process_sync(request).await;
    assert_eq!(response.verification.rejected_count, 1);
}

#[tokio::test]
async fn test_oversized_payload_rejected() {
    let state = SyncState::new();
    let mut request = sample_sync_request();
    request.transactions = (0..600).map(|i| AnonymizedTransaction {
        amount_bucket: "100-500".to_string(),
        category: "sale".to_string(),
        payment_method: "cash".to_string(),
        hour_of_day: 12,
        day_of_week: 3,
        is_service: false,
        dedup_key: Some(format!("key-{}", i)),
    }).collect();

    let response = state.process_sync(request).await;
    assert_eq!(response.verification.accepted_count, 0);
}

// ── FIX 3: Offline Queue Draining Tests ──

#[tokio::test]
async fn test_sync_with_queued_transactions() {
    // Simulate: device had 5 transactions queued offline, then syncs them all
    let state = SyncState::new();
    let mut request = sample_sync_request();
    request.transactions = (0..5).map(|i| AnonymizedTransaction {
        amount_bucket: "100-500".to_string(),
        category: "sale".to_string(),
        payment_method: "cash".to_string(),
        hour_of_day: 10 + i as u8,
        day_of_week: 3,
        is_service: false,
        dedup_key: Some(format!("queued-tx-{}", i)),
    }).collect();

    let response = state.process_sync(request).await;
    assert_eq!(response.synced_count, 5);
    assert_eq!(response.verification.accepted_count, 5);
}

#[tokio::test]
async fn test_sync_preserves_dedup_across_drains() {
    let state = SyncState::new();

    // First drain: 3 transactions
    let mut request1 = sample_sync_request();
    request1.transactions = (0..3).map(|i| AnonymizedTransaction {
        amount_bucket: "100-500".to_string(),
        category: "sale".to_string(),
        payment_method: "cash".to_string(),
        hour_of_day: 10,
        day_of_week: 3,
        is_service: false,
        dedup_key: Some(format!("drain1-{}", i)),
    }).collect();

    let resp1 = state.process_sync(request1).await;
    assert_eq!(resp1.synced_count, 3);

    // Second drain: 2 new + 1 duplicate from first drain
    let mut request2 = sample_sync_request();
    request2.transactions = vec![
        AnonymizedTransaction {
            amount_bucket: "100-500".to_string(),
            category: "sale".to_string(),
            payment_method: "cash".to_string(),
            hour_of_day: 10,
            day_of_week: 3,
            is_service: false,
            dedup_key: Some("drain2-new-1".to_string()),
        },
        AnonymizedTransaction {
            amount_bucket: "500-1000".to_string(),
            category: "sale".to_string(),
            payment_method: "mpesa".to_string(),
            hour_of_day: 11,
            day_of_week: 3,
            is_service: false,
            dedup_key: Some("drain2-new-2".to_string()),
        },
        AnonymizedTransaction {
            amount_bucket: "100-500".to_string(),
            category: "sale".to_string(),
            payment_method: "cash".to_string(),
            hour_of_day: 10,
            day_of_week: 3,
            is_service: false,
            dedup_key: Some("drain1-0".to_string()), // duplicate!
        },
    ];

    let resp2 = state.process_sync(request2).await;
    assert_eq!(resp2.verification.accepted_count, 2);
    assert_eq!(resp2.verification.duplicate_count, 1);
}

// ── FIX 4: Model Version Compatibility Tests ──

#[tokio::test]
async fn test_model_version_included_in_request() {
    let state = SyncState::new();
    let request = sample_sync_request();
    assert_eq!(request.model_version, Some("2.1.0".to_string()));

    let response = state.process_sync(request).await;
    // Current version should not get a model delta
    assert!(response.model_delta.is_none());
}

#[tokio::test]
async fn test_old_model_version_gets_delta() {
    let state = SyncState::new();
    let mut request = sample_sync_request();
    request.model_version = Some("2.0.0".to_string());

    let response = state.process_sync(request).await;
    assert!(response.model_delta.is_some());

    let delta = response.model_delta.unwrap();
    assert_eq!(delta.target_version, "2.1.0");
    assert!(!delta.is_full_model); // Should be a delta, not full
}

#[tokio::test]
async fn test_very_old_model_gets_full_update() {
    let state = SyncState::new();
    let mut request = sample_sync_request();
    request.model_version = Some("1.0.0".to_string());

    let response = state.process_sync(request).await;
    assert!(response.model_delta.is_some());

    let delta = response.model_delta.unwrap();
    assert!(delta.is_full_model);
}

#[tokio::test]
async fn test_no_model_version_no_update() {
    let state = SyncState::new();
    let mut request = sample_sync_request();
    request.model_version = None;

    let response = state.process_sync(request).await;
    assert!(response.model_delta.is_none());
}

#[test]
fn test_version_compatibility_checker() {
    let checker = VersionCompatibilityChecker::new();
    assert!(checker.is_compatible("1.5.0"));
    assert!(checker.is_compatible("2.0.0"));
    assert!(checker.is_compatible("2.1.0"));
    assert!(!checker.is_compatible("1.0.0"));
    assert!(!checker.is_compatible("invalid"));
}

// ── FIX 5: Data Freshness Tests ──

#[tokio::test]
async fn test_freshness_in_response() {
    let state = SyncState::new();
    let request = sample_sync_request();
    let response = state.process_sync(request).await;

    assert!(response.freshness.server_timestamp > 0);
}

#[tokio::test]
async fn test_stale_triggers_pull_indicator() {
    let checker = FreshnessChecker::new();
    let now = Utc::now().timestamp_millis();

    // 2 hours old market data
    let market = MarketIntelligence {
        ward: "Test".to_string(),
        price_trends: std::collections::HashMap::new(),
        demand_signals: vec![],
        data_timestamp: now - 2 * 60 * 60 * 1000,
        ttl_seconds: 3600,
    };

    let freshness = tokio_test::block_on(checker.check_freshness(None, Some(&market), None));
    assert!(!freshness.market_data_fresh);
    assert_eq!(freshness.staleness, "unknown"); // No last_server_timestamp
}

#[test]
fn test_freshness_thresholds() {
    let now = Utc::now().timestamp_millis();

    // Market data: 30 minutes old → fresh
    assert!(!FreshnessChecker::needs_market_refresh(now - 30 * 60 * 1000));

    // Market data: 2 hours old → stale
    assert!(FreshnessChecker::needs_market_refresh(now - 2 * 60 * 60 * 1000));

    // Score: 12 hours old → fresh
    assert!(!FreshnessChecker::needs_score_refresh(now - 12 * 60 * 60 * 1000));

    // Score: 25 hours old → stale
    assert!(FreshnessChecker::needs_score_refresh(now - 25 * 60 * 60 * 1000));
}

#[test]
fn test_staleness_alert_generation() {
    let alert = FreshnessChecker::generate_staleness_alert("very_stale", None);
    assert!(alert.is_some());
    assert_eq!(alert.unwrap().severity, "warning");

    let alert = FreshnessChecker::generate_staleness_alert("stale", None);
    assert!(alert.is_some());
    assert_eq!(alert.unwrap().severity, "info");

    let alert = FreshnessChecker::generate_staleness_alert("fresh", None);
    assert!(alert.is_none());
}

// ── Protocol Version Tests ──

#[tokio::test]
async fn test_old_protocol_rejected() {
    let state = SyncState::new();
    let mut request = sample_sync_request();
    request.sync_protocol_version = 0;

    let response = state.process_sync(request).await;
    assert_eq!(response.status, "error");
    assert!(response.message.unwrap().contains("too old"));
    assert!(!response.alerts.is_empty());
    assert_eq!(response.alerts[0].severity, "critical");
}

// ── Device State Tracking ──

#[tokio::test]
async fn test_device_state_updated_after_sync() {
    let state = SyncState::new();
    let request = sample_sync_request();

    state.process_sync(request).await;

    let device_states = state.device_states.read().await;
    let device = device_states.get("test-device-001").unwrap();

    assert_eq!(device.total_syncs, 1);
    assert_eq!(device.total_transactions_synced, 2);
    assert_eq!(device.model_version, Some("2.1.0".to_string()));
    assert!(device.last_sync_timestamp > 0);
}

#[tokio::test]
async fn test_device_state_accumulates_across_syncs() {
    let state = SyncState::new();

    // First sync
    let request1 = sample_sync_request();
    state.process_sync(request1).await;

    // Second sync
    let mut request2 = sample_sync_request();
    request2.transactions = vec![AnonymizedTransaction {
        amount_bucket: "1000-5000".to_string(),
        category: "purchase".to_string(),
        payment_method: "bank".to_string(),
        hour_of_day: 16,
        day_of_week: 4,
        is_service: false,
        dedup_key: Some("tx-003".to_string()),
    }];

    state.process_sync(request2).await;

    let device_states = state.device_states.read().await;
    let device = device_states.get("test-device-001").unwrap();

    assert_eq!(device.total_syncs, 2);
    assert_eq!(device.total_transactions_synced, 3); // 2 + 1
}
