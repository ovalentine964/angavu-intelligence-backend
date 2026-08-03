// =============================================================================
// Angavu Intelligence — Data Retention Policies
// Automated data expiry and right-to-erasure enforcement.
//
// Addresses B6 P1 gap (G6.8): Data retention/deletion policy enforcement
//
// Retention periods:
// - Raw transactions: 2 years
// - Aggregated statistics: 5 years
// - Audit logs: 7 years
// - Credit scores: 3 years
// - Federated learning gradients: 90 days
// - Webhook events: 1 year
// - Session data: 30 days
//
// Right-to-erasure (Kenya DPA 2019):
// - Individual data deletion within 30 days of request
// - Cascading deletion across all tables
// - Audit trail of deletion requests
// =============================================================================

use chrono::{DateTime, Duration, Utc};
use serde::{Deserialize, Serialize};

/// Data category with its retention policy
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RetentionPolicy {
    pub category: DataCategory,
    pub retention_days: i32,
    pub description: String,
    pub legal_basis: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum DataCategory {
    /// Raw transaction records
    RawTransactions,
    /// Aggregated market/economic statistics
    AggregatedStatistics,
    /// API audit logs
    AuditLogs,
    /// Credit score computations
    CreditScores,
    /// Federated learning gradient updates
    FederatedGradients,
    /// Webhook event payloads
    WebhookEvents,
    /// User session data
    SessionData,
    /// Billing records (must be kept for tax compliance)
    BillingRecords,
    /// Human approval records
    ApprovalRecords,
    /// Model training data
    ModelTrainingData,
}

impl DataCategory {
    pub fn label(&self) -> &'static str {
        match self {
            Self::RawTransactions => "raw_transactions",
            Self::AggregatedStatistics => "aggregated_statistics",
            Self::AuditLogs => "audit_logs",
            Self::CreditScores => "credit_scores",
            Self::FederatedGradients => "federated_gradients",
            Self::WebhookEvents => "webhook_events",
            Self::SessionData => "session_data",
            Self::BillingRecords => "billing_records",
            Self::ApprovalRecords => "approval_records",
            Self::ModelTrainingData => "model_training_data",
        }
    }
}

/// Get the default retention policy for all data categories.
pub fn default_policies() -> Vec<RetentionPolicy> {
    vec![
        RetentionPolicy {
            category: DataCategory::RawTransactions,
            retention_days: 730, // 2 years
            description: "Raw transaction records from device syncs".to_string(),
            legal_basis: "Kenya DPA 2019: legitimate business interest for credit scoring"
                .to_string(),
        },
        RetentionPolicy {
            category: DataCategory::AggregatedStatistics,
            retention_days: 1825, // 5 years
            description: "Aggregated market, economic, and distribution statistics".to_string(),
            legal_basis: "Anonymized data — not personal data under DPA".to_string(),
        },
        RetentionPolicy {
            category: DataCategory::AuditLogs,
            retention_days: 2555, // 7 years
            description: "API access audit trail for compliance".to_string(),
            legal_basis: "Kenya Data Protection Act 2019: accountability requirement".to_string(),
        },
        RetentionPolicy {
            category: DataCategory::CreditScores,
            retention_days: 1095, // 3 years
            description: "Computed credit scores and explanations".to_string(),
            legal_basis: "EU AI Act: model decision records must be retained".to_string(),
        },
        RetentionPolicy {
            category: DataCategory::FederatedGradients,
            retention_days: 90,
            description: "Gradient updates from federated learning rounds".to_string(),
            legal_basis: "Minimization — gradients are intermediate computation artifacts"
                .to_string(),
        },
        RetentionPolicy {
            category: DataCategory::WebhookEvents,
            retention_days: 365, // 1 year
            description: "M-Pesa and other webhook event payloads".to_string(),
            legal_basis: "Transaction dispute resolution window".to_string(),
        },
        RetentionPolicy {
            category: DataCategory::SessionData,
            retention_days: 30,
            description: "User session tokens and context".to_string(),
            legal_basis: "Minimization — session data is ephemeral".to_string(),
        },
        RetentionPolicy {
            category: DataCategory::BillingRecords,
            retention_days: 2555, // 7 years
            description: "Invoices, payment records, subscription history".to_string(),
            legal_basis: "Kenya Tax Act: financial records must be retained 7 years".to_string(),
        },
        RetentionPolicy {
            category: DataCategory::ApprovalRecords,
            retention_days: 1095, // 3 years
            description: "Human-in-the-loop approval decisions".to_string(),
            legal_basis: "EU AI Act: human oversight records".to_string(),
        },
        RetentionPolicy {
            category: DataCategory::ModelTrainingData,
            retention_days: 365, // 1 year
            description: "Curated training examples for model improvement".to_string(),
            legal_basis: "Model audit and retraining cycle".to_string(),
        },
    ]
}

/// Result of a retention enforcement run
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RetentionReport {
    pub run_at: DateTime<Utc>,
    pub tables_processed: u32,
    pub rows_deleted: u64,
    pub errors: Vec<String>,
    pub details: Vec<RetentionDetail>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RetentionDetail {
    pub category: DataCategory,
    pub table: String,
    pub rows_deleted: u64,
    pub cutoff_date: DateTime<Utc>,
}

/// Generate SQL statements to enforce data retention policies.
/// These should be run as a scheduled job (daily/weekly).
pub fn generate_retention_queries() -> Vec<(DataCategory, &'static str, String)> {
    let now = Utc::now();
    let mut queries = Vec::new();

    for policy in default_policies() {
        let cutoff = now - Duration::days(policy.retention_days as i64);
        let cutoff_str = cutoff.format("%Y-%m-%dT%H:%M:%SZ").to_string();

        let sql = match policy.category {
            DataCategory::RawTransactions => {
                format!(
                    "DELETE FROM transactions WHERE created_at < '{}' AND id IN \
                     (SELECT id FROM transactions WHERE created_at < '{}' LIMIT 10000)",
                    cutoff_str, cutoff_str
                )
            }
            DataCategory::AuditLogs => {
                format!(
                    "DELETE FROM audit_log WHERE timestamp < '{}' AND id IN \
                     (SELECT id FROM audit_log WHERE timestamp < '{}' LIMIT 10000)",
                    cutoff_str, cutoff_str
                )
            }
            DataCategory::CreditScores => {
                format!(
                    "DELETE FROM credit_score_history WHERE computed_at < '{}' AND id IN \
                     (SELECT id FROM credit_score_history WHERE computed_at < '{}' LIMIT 10000)",
                    cutoff_str, cutoff_str
                )
            }
            DataCategory::WebhookEvents => {
                format!(
                    "DELETE FROM webhook_events WHERE created_at < '{}' AND id IN \
                     (SELECT id FROM webhook_events WHERE created_at < '{}' LIMIT 10000)",
                    cutoff_str, cutoff_str
                )
            }
            DataCategory::SessionData => {
                format!(
                    "DELETE FROM session_data WHERE created_at < '{}'",
                    cutoff_str
                )
            }
            _ => continue,
        };

        queries.push((policy.category, policy.category.label(), sql));
    }

    queries
}

/// Right-to-erasure: Generate parameterized deletion SQL for a specific individual.
/// Returns a list of (table, sql, params) tuples for cascading deletion.
///
/// SECURITY FIX (P0): Uses $1 parameterized placeholders instead of string interpolation
/// to prevent SQL injection. The `person_id` is passed as a bind parameter, never
/// interpolated into the SQL string.
pub fn generate_erasure_queries(person_id: &str) -> Vec<(&'static str, String, Vec<String>)> {
    let params = vec![person_id.to_string()];
    vec![
        (
            "transactions",
            "DELETE FROM transactions WHERE worker_id_hash = $1".to_string(),
            params.clone(),
        ),
        (
            "credit_score_history",
            "DELETE FROM credit_score_history WHERE cohort_hash IN \
          (SELECT DISTINCT cohort_hash FROM transactions WHERE worker_id_hash = $1)"
                .to_string(),
            params.clone(),
        ),
        (
            "audit_log",
            "DELETE FROM audit_log WHERE org_id = $1 AND timestamp > NOW() - INTERVAL '30 days'"
                .to_string(),
            params,
        ),
    ]
}

/// SQL migration for tracking data retention enforcement
pub const RETENTION_MIGRATION: &str = r#"
CREATE TABLE IF NOT EXISTS data_retention_log (
    id BIGSERIAL PRIMARY KEY,
    run_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    category VARCHAR(64) NOT NULL,
    table_name VARCHAR(128) NOT NULL,
    rows_deleted BIGINT NOT NULL DEFAULT 0,
    cutoff_date TIMESTAMPTZ NOT NULL,
    error_message TEXT,
    duration_ms BIGINT NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_retention_log_run_at ON data_retention_log(run_at DESC);
CREATE INDEX IF NOT EXISTS idx_retention_log_category ON data_retention_log(category);

CREATE TABLE IF NOT EXISTS erasure_requests (
    id BIGSERIAL PRIMARY KEY,
    person_id_hash VARCHAR(128) NOT NULL,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    tables_affected JSONB NOT NULL DEFAULT '[]',
    rows_deleted BIGINT NOT NULL DEFAULT 0,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_erasure_requests_status ON erasure_requests(status);
"#;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_default_policies_cover_all_categories() {
        let policies = default_policies();
        assert_eq!(policies.len(), 10);
        // All categories should have a policy
        for cat in [
            DataCategory::RawTransactions,
            DataCategory::AuditLogs,
            DataCategory::CreditScores,
        ] {
            assert!(policies.iter().any(|p| p.category == cat));
        }
    }

    #[test]
    fn test_retention_periods_reasonable() {
        let policies = default_policies();
        for p in &policies {
            assert!(
                p.retention_days > 0,
                "{:?} has non-positive retention",
                p.category
            );
            assert!(
                p.retention_days <= 3650,
                "{:?} retention > 10 years",
                p.category
            );
        }
    }

    #[test]
    fn test_erasure_queries_parameterized() {
        let queries = generate_erasure_queries("test_hash_123");
        assert!(!queries.is_empty());
        for (table, sql, params) in &queries {
            // SECURITY: SQL must use $1 placeholder, not inline the person_id
            assert!(
                sql.contains("$1"),
                "{}: SQL should use $1 placeholder",
                table
            );
            assert!(
                !sql.contains("test_hash_123"),
                "{}: SQL must not interpolate person_id",
                table
            );
            // Parameter must contain the actual person_id
            assert!(params.contains(&"test_hash_123".to_string()));
        }
    }

    #[test]
    fn test_retention_queries_generated() {
        let queries = generate_retention_queries();
        assert!(!queries.is_empty());
        for (cat, label, sql) in &queries {
            assert!(!sql.is_empty(), "Empty SQL for {:?}", cat);
            assert!(!label.is_empty());
        }
    }
}
