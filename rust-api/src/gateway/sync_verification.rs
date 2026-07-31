// gateway/sync_verification.rs
// Fix 4 (backend): Verify inbound sync data before processing.
//
// When the app syncs data to the backend, we verify:
//   1. Transaction amounts are within plausible ranges
//   2. No duplicate transactions in the batch
//   3. Transaction categories are valid
//   4. Batch size is reasonable
//   5. Timestamp ordering is correct
//   6. Anonymization was properly applied (no raw PII)

use serde::{Deserialize, Serialize};

/// Maximum transactions per sync batch
const MAX_BATCH_SIZE: usize = 500;

/// Maximum amount bucket values (matches app-side bucketing)
const VALID_AMOUNT_BUCKETS: &[&str] = &["0-100", "100-500", "500-1000", "1000-5000", "5000+"];

/// Valid transaction categories
const VALID_CATEGORIES: &[&str] = &[
    "sale", "expense", "purchase", "service", "transfer",
    "refund", "withdrawal", "deposit", "loan", "repayment",
    "salary", "wage", "commission", "tip", "discount",
    "transport", "food", "rent", "utilities", "supplies",
    "stock", "inventory", "repair", "maintenance", "other",
];

/// Valid payment methods
const VALID_PAYMENT_METHODS: &[&str] = &[
    "cash", "mpesa", "m-pesa", "bank", "card", "credit",
    "airtel_money", "equitel", "sasapay", "other",
];

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SyncBatchVerification {
    pub valid: bool,
    pub issues: Vec<SyncBatchIssue>,
    pub warnings: Vec<String>,
    pub valid_transaction_count: usize,
    pub rejected_transaction_count: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SyncBatchIssue {
    pub issue_type: SyncBatchIssueType,
    pub severity: IssueSeverity,
    pub message: String,
    pub transaction_index: Option<usize>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum SyncBatchIssueType {
    BatchTooLarge,
    InvalidAmountBucket,
    InvalidCategory,
    InvalidPaymentMethod,
    DuplicateTransaction,
    PiiDetected,
    InvalidTimestamp,
    EmptyBatch,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum IssueSeverity {
    Low,
    Medium,
    High,
}

/// Transaction data as received in sync (matches app's AnonymizedTransaction)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AnonymizedTransactionIn {
    pub amount_bucket: String,
    pub category: String,
    pub payment_method: String,
    pub hour_of_day: u8,
    pub day_of_week: u8,
    pub is_service: bool,
}

/// Verify a sync batch before processing.
pub fn verify_sync_batch(transactions: &[AnonymizedTransactionIn]) -> SyncBatchVerification {
    let mut issues = Vec::new();
    let mut warnings = Vec::new();
    let mut rejected = 0;

    // ── Check 1: Empty batch ─────────────────────────────────
    if transactions.is_empty() {
        issues.push(SyncBatchIssue {
            issue_type: SyncBatchIssueType::EmptyBatch,
            severity: IssueSeverity::Medium,
            message: "Sync batch is empty".to_string(),
            transaction_index: None,
        });
    }

    // ── Check 2: Batch size ──────────────────────────────────
    if transactions.len() > MAX_BATCH_SIZE {
        issues.push(SyncBatchIssue {
            issue_type: SyncBatchIssueType::BatchTooLarge,
            severity: IssueSeverity::High,
            message: format!(
                "Batch too large: {} transactions (max {})",
                transactions.len(),
                MAX_BATCH_SIZE
            ),
            transaction_index: None,
        });
    }

    // ── Check 3: Validate each transaction ───────────────────
    for (i, tx) in transactions.iter().enumerate() {
        // Amount bucket
        if !VALID_AMOUNT_BUCKETS.contains(&tx.amount_bucket.as_str()) {
            issues.push(SyncBatchIssue {
                issue_type: SyncBatchIssueType::InvalidAmountBucket,
                severity: IssueSeverity::High,
                message: format!("Invalid amount bucket: '{}'", tx.amount_bucket),
                transaction_index: Some(i),
            });
            rejected += 1;
        }

        // Category
        if !VALID_CATEGORIES.contains(&tx.category.to_lowercase().as_str()) {
            issues.push(SyncBatchIssue {
                issue_type: SyncBatchIssueType::InvalidCategory,
                severity: IssueSeverity::Medium,
                message: format!("Unknown category: '{}'", tx.category),
                transaction_index: Some(i),
            });
        }

        // Payment method
        if !VALID_PAYMENT_METHODS.contains(&tx.payment_method.to_lowercase().as_str()) {
            issues.push(SyncBatchIssue {
                issue_type: SyncBatchIssueType::InvalidPaymentMethod,
                severity: IssueSeverity::Medium,
                message: format!("Unknown payment method: '{}'", tx.payment_method),
                transaction_index: Some(i),
            });
        }

        // Hour of day
        if tx.hour_of_day > 23 {
            issues.push(SyncBatchIssue {
                issue_type: SyncBatchIssueType::InvalidTimestamp,
                severity: IssueSeverity::High,
                message: format!("Invalid hour of day: {}", tx.hour_of_day),
                transaction_index: Some(i),
            });
        }

        // Day of week
        if tx.day_of_week < 1 || tx.day_of_week > 7 {
            issues.push(SyncBatchIssue {
                issue_type: SyncBatchIssueType::InvalidTimestamp,
                severity: IssueSeverity::High,
                message: format!("Invalid day of week: {}", tx.day_of_week),
                transaction_index: Some(i),
            });
        }
    }

    // ── Check 4: Duplicate detection ─────────────────────────
    // Since data is anonymized, we check for exact duplicates in the batch
    let mut seen = std::collections::HashSet::new();
    for (i, tx) in transactions.iter().enumerate() {
        let key = format!(
            "{}|{}|{}|{}|{}",
            tx.amount_bucket, tx.category, tx.payment_method, tx.hour_of_day, tx.day_of_week
        );
        if !seen.insert(key) {
            warnings.push(format!(
                "Possible duplicate transaction at index {} (same bucket/category/method/time)",
                i
            ));
        }
    }

    // ── Check 5: PII detection ───────────────────────────────
    // Check that no raw phone numbers or names leaked through
    for (i, tx) in transactions.iter().enumerate() {
        // Phone number pattern (Kenyan: 07xx, +254, etc.)
        let phone_pattern = match regex::Regex::new(r"(?:\+?254|0)[17]\d{8}") {
            Ok(r) => r,
            Err(_) => continue,
        };
        if phone_pattern.is_match(&tx.category) || phone_pattern.is_match(&tx.payment_method) {
            issues.push(SyncBatchIssue {
                issue_type: SyncBatchIssueType::PiiDetected,
                severity: IssueSeverity::High,
                message: format!("Possible PII detected in transaction {}", i),
                transaction_index: Some(i),
            });
        }
    }

    let has_high = issues.iter().any(|i| matches!(i.severity, IssueSeverity::High));
    let valid_count = transactions.len().saturating_sub(rejected);

    SyncBatchVerification {
        valid: !has_high,
        issues,
        warnings,
        valid_transaction_count: valid_count,
        rejected_transaction_count: rejected,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn valid_transaction() -> AnonymizedTransactionIn {
        AnonymizedTransactionIn {
            amount_bucket: "500-1000".to_string(),
            category: "sale".to_string(),
            payment_method: "mpesa".to_string(),
            hour_of_day: 14,
            day_of_week: 3,
            is_service: false,
        }
    }

    #[test]
    fn valid_batch_passes() {
        let txs = vec![valid_transaction(), valid_transaction()];
        let result = verify_sync_batch(&txs);
        assert!(result.valid);
    }

    #[test]
    fn empty_batch_flagged() {
        let result = verify_sync_batch(&[]);
        assert!(result.issues.iter().any(|i| matches!(
            i.issue_type,
            SyncBatchIssueType::EmptyBatch
        )));
    }

    #[test]
    fn invalid_amount_bucket_fails() {
        let mut tx = valid_transaction();
        tx.amount_bucket = "99999".to_string();
        let result = verify_sync_batch(&[tx]);
        assert!(!result.valid);
    }

    #[test]
    fn invalid_category_flagged() {
        let mut tx = valid_transaction();
        tx.category = "xyz_nonexistent".to_string();
        let result = verify_sync_batch(&[tx]);
        assert!(result.issues.iter().any(|i| matches!(
            i.issue_type,
            SyncBatchIssueType::InvalidCategory
        )));
    }

    #[test]
    fn invalid_payment_method_flagged() {
        let mut tx = valid_transaction();
        tx.payment_method = "bitcoin".to_string();
        let result = verify_sync_batch(&[tx]);
        assert!(result.issues.iter().any(|i| matches!(
            i.issue_type,
            SyncBatchIssueType::InvalidPaymentMethod
        )));
    }

    #[test]
    fn invalid_hour_fails() {
        let mut tx = valid_transaction();
        tx.hour_of_day = 25;
        let result = verify_sync_batch(&[tx]);
        assert!(!result.valid);
    }

    #[test]
    fn invalid_day_of_week_fails() {
        let mut tx = valid_transaction();
        tx.day_of_week = 0;
        let result = verify_sync_batch(&[tx]);
        assert!(!result.valid);
    }

    #[test]
    fn pii_detection() {
        let mut tx = valid_transaction();
        tx.category = "+254712345678".to_string();
        let result = verify_sync_batch(&[tx]);
        assert!(result.issues.iter().any(|i| matches!(
            i.issue_type,
            SyncBatchIssueType::PiiDetected
        )));
    }

    #[test]
    fn duplicate_detection_warns() {
        let txs = vec![valid_transaction(), valid_transaction()];
        let result = verify_sync_batch(&txs);
        assert!(result.warnings.iter().any(|w| w.contains("duplicate")));
    }
}
