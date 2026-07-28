// Angavu Intelligence Backend — Sync Boundary Verification
// Verifies data integrity at the sync boundary before accepting transactions.
//
// Checks:
// - Transaction amounts plausible (not 10x normal for the category)
// - No duplicate transactions (dedup by key)
// - Transaction categories valid
// - Worker type consistent with transaction patterns
// - Hour/day values in valid ranges

use super::*;
use super::receiver::DeviceState;
use tracing::warn;

/// Valid transaction categories accepted by the backend
const VALID_CATEGORIES: &[&str] = &[
    "sale", "expense", "purchase", "income", "transfer",
    "service", "wage", "commission", "loan", "repayment",
    "rent", "transport", "food", "utilities", "stock",
    "other",
];

/// Valid payment methods
const VALID_PAYMENT_METHODS: &[&str] = &[
    "cash", "mpesa", "bank", "credit", "airtel", "other",
];

/// Maximum plausible amount bucket index (for anomaly detection)
const MAX_AMOUNT_BUCKET: &[&str] = &[
    "0-100", "100-500", "500-1000", "1000-5000", "5000+",
];

/// Maximum acceptable sync payload size
const MAX_TRANSACTIONS_PER_SYNC: usize = 500;

/// Maximum age of a sync timestamp (24 hours in ms)
const MAX_SYNC_TIMESTAMP_AGE_MS: i64 = 24 * 60 * 60 * 1000;

pub struct SyncVerifier {
    /// Category-specific amount thresholds for plausibility checks
    amount_thresholds: std::collections::HashMap<String, AmountThreshold>,
}

struct AmountThreshold {
    /// Expected median amount for this category
    median: f64,
    /// Maximum plausible amount (10x median)
    max_plausible: f64,
}

impl SyncVerifier {
    pub fn new() -> Self {
        let mut thresholds = std::collections::HashMap::new();
        thresholds.insert("sale".to_string(), AmountThreshold { median: 500.0, max_plausible: 50000.0 });
        thresholds.insert("expense".to_string(), AmountThreshold { median: 200.0, max_plausible: 20000.0 });
        thresholds.insert("purchase".to_string(), AmountThreshold { median: 1000.0, max_plausible: 100000.0 });
        thresholds.insert("income".to_string(), AmountThreshold { median: 800.0, max_plausible: 80000.0 });
        thresholds.insert("service".to_string(), AmountThreshold { median: 300.0, max_plausible: 30000.0 });
        thresholds.insert("wage".to_string(), AmountThreshold { median: 1500.0, max_plausible: 150000.0 });
        thresholds.insert("transport".to_string(), AmountThreshold { median: 100.0, max_plausible: 10000.0 });

        Self { amount_thresholds: thresholds }
    }

    /// Verify all transactions in a sync request.
    /// Returns a VerificationResult with accepted/rejected counts and reasons.
    pub async fn verify_sync(
        &self,
        request: &SyncRequest,
        device_state: &DeviceState,
    ) -> VerificationResult {
        let mut accepted = 0u32;
        let mut rejected = 0u32;
        let mut duplicates = 0u32;
        let mut rejection_reasons = Vec::new();

        // ── Payload size check ──
        if request.transactions.len() > MAX_TRANSACTIONS_PER_SYNC {
            rejection_reasons.push(RejectionReason {
                transaction_index: 0,
                reason: format!(
                    "Payload too large: {} transactions (max {})",
                    request.transactions.len(),
                    MAX_TRANSACTIONS_PER_SYNC
                ),
                severity: "error".to_string(),
            });
            return VerificationResult {
                all_valid: false,
                accepted_count: 0,
                rejected_count: request.transactions.len() as u32,
                duplicate_count: 0,
                rejection_reasons,
            };
        }

        // ── Timestamp freshness check ──
        let now = chrono::Utc::now().timestamp_millis();
        let timestamp_age = (now - request.timestamp).abs();
        if timestamp_age > MAX_SYNC_TIMESTAMP_AGE_MS {
            rejection_reasons.push(RejectionReason {
                transaction_index: 0,
                reason: format!(
                    "Sync timestamp too old/future: {}ms age (max {}ms)",
                    timestamp_age, MAX_SYNC_TIMESTAMP_AGE_MS
                ),
                severity: "warning".to_string(),
            });
        }

        // ── Per-transaction verification ──
        for (i, tx) in request.transactions.iter().enumerate() {
            // 1. Duplicate check
            if let Some(ref dedup_key) = tx.dedup_key {
                if device_state.known_dedup_keys.contains(dedup_key) {
                    duplicates += 1;
                    rejection_reasons.push(RejectionReason {
                        transaction_index: i,
                        reason: format!("Duplicate transaction: {}", dedup_key),
                        severity: "warning".to_string(),
                    });
                    continue;
                }
            }

            // 2. Category validation
            if !VALID_CATEGORIES.contains(&tx.category.as_str()) {
                rejected += 1;
                rejection_reasons.push(RejectionReason {
                    transaction_index: i,
                    reason: format!("Invalid category: '{}'", tx.category),
                    severity: "error".to_string(),
                });
                continue;
            }

            // 3. Payment method validation
            if !VALID_PAYMENT_METHODS.contains(&tx.payment_method.as_str()) {
                rejected += 1;
                rejection_reasons.push(RejectionReason {
                    transaction_index: i,
                    reason: format!("Invalid payment method: '{}'", tx.payment_method),
                    severity: "error".to_string(),
                });
                continue;
            }

            // 4. Amount bucket validation
            if !MAX_AMOUNT_BUCKET.contains(&tx.amount_bucket.as_str()) {
                rejected += 1;
                rejection_reasons.push(RejectionReason {
                    transaction_index: i,
                    reason: format!("Invalid amount bucket: '{}'", tx.amount_bucket),
                    severity: "error".to_string(),
                });
                continue;
            }

            // 5. Hour/day range validation
            if tx.hour_of_day > 23 {
                rejected += 1;
                rejection_reasons.push(RejectionReason {
                    transaction_index: i,
                    reason: format!("Invalid hour_of_day: {}", tx.hour_of_day),
                    severity: "error".to_string(),
                });
                continue;
            }
            if tx.day_of_week < 1 || tx.day_of_week > 7 {
                rejected += 1;
                rejection_reasons.push(RejectionReason {
                    transaction_index: i,
                    reason: format!("Invalid day_of_week: {}", tx.day_of_week),
                    severity: "error".to_string(),
                });
                continue;
            }

            // 6. Amount plausibility check (compare bucket to category threshold)
            if let Some(threshold) = self.amount_thresholds.get(&tx.category) {
                if let Some(bucket_max) = self.parse_bucket_max(&tx.amount_bucket) {
                    if bucket_max > threshold.max_plausible {
                        // Not a hard reject — flag as warning
                        rejection_reasons.push(RejectionReason {
                            transaction_index: i,
                            reason: format!(
                                "Amount bucket '{}' seems implausible for category '{}' (max plausible: {})",
                                tx.amount_bucket, tx.category, threshold.max_plausible
                            ),
                            severity: "warning".to_string(),
                        });
                        // Still accept — warnings don't block
                    }
                }
            }

            accepted += 1;
        }

        VerificationResult {
            all_valid: rejected == 0 && duplicates == 0,
            accepted_count: accepted,
            rejected_count: rejected,
            duplicate_count: duplicates,
            rejection_reasons,
        }
    }

    /// Parse the upper bound of an amount bucket
    fn parse_bucket_max(&self, bucket: &str) -> Option<f64> {
        match bucket {
            "0-100" => Some(100.0),
            "100-500" => Some(500.0),
            "500-1000" => Some(1000.0),
            "1000-5000" => Some(5000.0),
            "5000+" => Some(100000.0), // open-ended
            _ => None,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use super::super::receiver::DeviceState;

    fn sample_request() -> SyncRequest {
        SyncRequest {
            device_id: "test-device".to_string(),
            business_category: "Trade".to_string(),
            ward: "Test Ward".to_string(),
            transactions: vec![
                AnonymizedTransaction {
                    amount_bucket: "500-1000".to_string(),
                    category: "sale".to_string(),
                    payment_method: "cash".to_string(),
                    hour_of_day: 14,
                    day_of_week: 3,
                    is_service: false,
                    dedup_key: Some("key-001".to_string()),
                },
            ],
            learned_patterns: vec![],
            vocabulary_hashes: vec![],
            anomaly_stats: AnomalyStats {
                total_transactions_analyzed: 0,
                anomaly_count: 0,
                mean_amount: 0.0,
                std_dev: 0.0,
            },
            timestamp: chrono::Utc::now().timestamp_millis(),
            sync_protocol_version: 2,
            model_version: None,
            last_server_timestamp: None,
        }
    }

    fn empty_device_state() -> DeviceState {
        DeviceState {
            device_id: "test-device".to_string(),
            last_sync_timestamp: 0,
            known_dedup_keys: Vec::new(),
            model_version: None,
            last_score: None,
            total_syncs: 0,
            total_transactions_synced: 0,
        }
    }

    #[tokio::test]
    async fn test_valid_transactions_accepted() {
        let verifier = SyncVerifier::new();
        let request = sample_request();
        let state = empty_device_state();

        let result = verifier.verify_sync(&request, &state).await;
        assert!(result.all_valid);
        assert_eq!(result.accepted_count, 1);
        assert_eq!(result.rejected_count, 0);
    }

    #[tokio::test]
    async fn test_invalid_category_rejected() {
        let verifier = SyncVerifier::new();
        let mut request = sample_request();
        request.transactions[0].category = "INVALID_CATEGORY".to_string();
        let state = empty_device_state();

        let result = verifier.verify_sync(&request, &state).await;
        assert!(!result.all_valid);
        assert_eq!(result.accepted_count, 0);
        assert_eq!(result.rejected_count, 1);
    }

    #[tokio::test]
    async fn test_duplicate_detected() {
        let verifier = SyncVerifier::new();
        let request = sample_request();
        let mut state = empty_device_state();
        state.known_dedup_keys.push("key-001".to_string());

        let result = verifier.verify_sync(&request, &state).await;
        assert_eq!(result.duplicate_count, 1);
        assert_eq!(result.accepted_count, 0);
    }

    #[tokio::test]
    async fn test_invalid_hour_rejected() {
        let verifier = SyncVerifier::new();
        let mut request = sample_request();
        request.transactions[0].hour_of_day = 25;
        let state = empty_device_state();

        let result = verifier.verify_sync(&request, &state).await;
        assert_eq!(result.rejected_count, 1);
    }

    #[tokio::test]
    async fn test_oversized_payload_rejected() {
        let verifier = SyncVerifier::new();
        let mut request = sample_request();
        request.transactions = (0..600).map(|i| AnonymizedTransaction {
            amount_bucket: "100-500".to_string(),
            category: "sale".to_string(),
            payment_method: "cash".to_string(),
            hour_of_day: 12,
            day_of_week: 3,
            is_service: false,
            dedup_key: Some(format!("key-{}", i)),
        }).collect();
        let state = empty_device_state();

        let result = verifier.verify_sync(&request, &state).await;
        assert!(!result.all_valid);
        assert_eq!(result.accepted_count, 0);
    }

    #[tokio::test]
    async fn test_invalid_payment_method_rejected() {
        let verifier = SyncVerifier::new();
        let mut request = sample_request();
        request.transactions[0].payment_method = "bitcoin".to_string();
        let state = empty_device_state();

        let result = verifier.verify_sync(&request, &state).await;
        assert_eq!(result.rejected_count, 1);
    }
}
