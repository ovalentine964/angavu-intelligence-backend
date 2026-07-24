//! AuditLogger — Compliance logging
//!
//! Logs all operations for compliance, data access tracking, and regulatory
//! requirements. Every tool action, data query, and API call is recorded
//! with actor, timestamp, action type, and affected data.

use anyhow::Result;
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

use crate::db::DatabaseConnections;

/// Severity levels for audit entries
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum AuditSeverity {
    Info,
    Warning,
    Critical,
    Security,
}

/// Categories of auditable actions
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum AuditCategory {
    DataAccess,
    DataModification,
    Authentication,
    Authorization,
    Configuration,
    ModelOperation,
    PrivacyOperation,
    ApiCall,
    SystemEvent,
}

/// An individual audit log entry
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AuditEntry {
    pub entry_id: Uuid,
    pub action: String,
    pub actor: String,
    pub category: AuditCategory,
    pub severity: AuditSeverity,
    pub resource_type: Option<String>,
    pub resource_id: Option<String>,
    pub data: serde_json::Value,
    pub ip_address: Option<String>,
    pub user_agent: Option<String>,
    pub session_id: Option<Uuid>,
    pub correlation_id: Option<Uuid>,
    pub timestamp: DateTime<Utc>,
}

/// Compliance report summary
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ComplianceReport {
    pub report_id: Uuid,
    pub period_start: DateTime<Utc>,
    pub period_end: DateTime<Utc>,
    pub total_actions: u64,
    pub actions_by_category: std::collections::HashMap<String, u64>,
    pub actions_by_severity: std::collections::HashMap<String, u64>,
    pub security_events: u64,
    pub data_access_events: u64,
    pub privacy_operations: u64,
    pub anomalies_detected: u64,
    pub generated_at: DateTime<Utc>,
}

/// Configuration for audit retention
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AuditConfig {
    /// Days to retain audit logs in hot storage (PostgreSQL)
    pub hot_retention_days: u32,
    /// Days to retain in cold storage (ClickHouse)
    pub cold_retention_days: u32,
    /// Enable real-time alerting on critical events
    pub alert_on_critical: bool,
    /// Minimum severity to log
    pub min_severity: AuditSeverity,
}

impl Default for AuditConfig {
    fn default() -> Self {
        Self {
            hot_retention_days: 90,
            cold_retention_days: 2555, // ~7 years for compliance
            alert_on_critical: true,
            min_severity: AuditSeverity::Info,
        }
    }
}

/// The AuditLogger tool
pub struct AuditLogger {
    db: DatabaseConnections,
    config: AuditConfig,
    buffer: tokio::sync::Mutex<Vec<AuditEntry>>,
    buffer_size: usize,
}

impl AuditLogger {
    pub fn new(db: DatabaseConnections) -> Self {
        Self {
            db,
            config: AuditConfig::default(),
            buffer: tokio::sync::Mutex::new(Vec::new()),
            buffer_size: 100,
        }
    }

    pub fn with_config(mut self, config: AuditConfig) -> Self {
        self.config = config;
        self
    }

    /// Log an action (used by OODAOrchestrator and other tools)
    pub async fn log_action(
        &self,
        action: &str,
        actor: &str,
        data: serde_json::Value,
    ) -> Result<Uuid> {
        self.log(AuditEntry {
            entry_id: Uuid::new_v4(),
            action: action.to_string(),
            actor: actor.to_string(),
            category: AuditCategory::SystemEvent,
            severity: AuditSeverity::Info,
            resource_type: None,
            resource_id: None,
            data,
            ip_address: None,
            user_agent: None,
            session_id: None,
            correlation_id: None,
            timestamp: Utc::now(),
        })
        .await
    }

    /// Log a data access event
    pub async fn log_data_access(
        &self,
        actor: &str,
        resource_type: &str,
        resource_id: &str,
        data: serde_json::Value,
    ) -> Result<Uuid> {
        self.log(AuditEntry {
            entry_id: Uuid::new_v4(),
            action: "data_access".to_string(),
            actor: actor.to_string(),
            category: AuditCategory::DataAccess,
            severity: AuditSeverity::Info,
            resource_type: Some(resource_type.to_string()),
            resource_id: Some(resource_id.to_string()),
            data,
            ip_address: None,
            user_agent: None,
            session_id: None,
            correlation_id: None,
            timestamp: Utc::now(),
        })
        .await
    }

    /// Log a security event
    pub async fn log_security_event(
        &self,
        action: &str,
        actor: &str,
        severity: AuditSeverity,
        data: serde_json::Value,
    ) -> Result<Uuid> {
        let entry = AuditEntry {
            entry_id: Uuid::new_v4(),
            action: action.to_string(),
            actor: actor.to_string(),
            category: AuditCategory::Security,
            severity: severity.clone(),
            resource_type: None,
            resource_id: None,
            data: data.clone(),
            ip_address: None,
            user_agent: None,
            session_id: None,
            correlation_id: None,
            timestamp: Utc::now(),
        };

        let id = self.log(entry).await?;

        // Alert on critical security events
        if self.config.alert_on_critical && severity == AuditSeverity::Critical {
            self.trigger_security_alert(action, actor, &data).await;
        }

        Ok(id)
    }

    /// Log a privacy operation (differential privacy, k-anonymity)
    pub async fn log_privacy_operation(
        &self,
        operation: &str,
        actor: &str,
        epsilon: Option<f64>,
        k_value: Option<u32>,
        records_affected: u64,
    ) -> Result<Uuid> {
        self.log(AuditEntry {
            entry_id: Uuid::new_v4(),
            action: operation.to_string(),
            actor: actor.to_string(),
            category: AuditCategory::PrivacyOperation,
            severity: AuditSeverity::Info,
            resource_type: Some("privacy".to_string()),
            resource_id: None,
            data: serde_json::json!({
                "epsilon": epsilon,
                "k_value": k_value,
                "records_affected": records_affected,
            }),
            ip_address: None,
            user_agent: None,
            session_id: None,
            correlation_id: None,
            timestamp: Utc::now(),
        })
        .await
    }

    /// Core logging function
    async fn log(&self, entry: AuditEntry) -> Result<Uuid> {
        let entry_id = entry.entry_id;

        // Write to ClickHouse for long-term storage
        self.write_to_clickhouse(&entry).await?;

        // Buffer for batch PostgreSQL insert
        {
            let mut buffer = self.buffer.lock().await;
            buffer.push(entry);
            if buffer.len() >= self.buffer_size {
                let batch: Vec<AuditEntry> = buffer.drain(..).collect();
                drop(buffer);
                self.flush_to_postgres(&batch).await?;
            }
        }

        Ok(entry_id)
    }

    /// Write audit entry to ClickHouse
    async fn write_to_clickhouse(&self, entry: &AuditEntry) -> Result<()> {
        #[derive(clickhouse::Row, Serialize)]
        struct AuditRow {
            entry_id: String,
            action: String,
            actor: String,
            category: String,
            severity: String,
            resource_type: String,
            resource_id: String,
            data: String,
            ip_address: String,
            event_time: chrono::NaiveDateTime,
        }

        let row = AuditRow {
            entry_id: entry.entry_id.to_string(),
            action: entry.action.clone(),
            actor: entry.actor.clone(),
            category: format!("{:?}", entry.category),
            severity: format!("{:?}", entry.severity),
            resource_type: entry.resource_type.clone().unwrap_or_default(),
            resource_id: entry.resource_id.clone().unwrap_or_default(),
            data: serde_json::to_string(&entry.data).unwrap_or_default(),
            ip_address: entry.ip_address.clone().unwrap_or_default(),
            event_time: entry.timestamp.naive_utc(),
        };

        if let Ok(mut insert) = self.db.clickhouse.insert("audit_log") {
            let _ = insert.write(&row).await;
            let _ = insert.end().await;
        }

        Ok(())
    }

    /// Flush buffered entries to PostgreSQL
    async fn flush_to_postgres(&self, entries: &[AuditEntry]) -> Result<()> {
        for entry in entries {
            let _ = sqlx::query!(
                r#"
                INSERT INTO audit_log (id, action, actor, category, severity, resource_type, resource_id, data, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                "#,
                entry.entry_id,
                entry.action,
                entry.actor,
                format!("{:?}", entry.category),
                format!("{:?}", entry.severity),
                entry.resource_type,
                entry.resource_id,
                entry.data,
                entry.timestamp
            )
            .execute(&self.db.postgres)
            .await;
        }
        Ok(())
    }

    /// Trigger a security alert (placeholder for integration with AlertGenerator)
    async fn trigger_security_alert(
        &self,
        action: &str,
        actor: &str,
        data: &serde_json::Value,
    ) {
        tracing::error!(
            action = %action,
            actor = %actor,
            data = %data,
            "CRITICAL SECURITY EVENT — alert triggered"
        );
    }

    /// Generate a compliance report for a time period
    pub async fn generate_compliance_report(
        &self,
        period_start: DateTime<Utc>,
        period_end: DateTime<Utc>,
    ) -> Result<ComplianceReport> {
        #[derive(clickhouse::Row, Deserialize)]
        struct CategoryCount {
            category: String,
            cnt: u64,
        }

        #[derive(clickhouse::Row, Deserialize)]
        struct SeverityCount {
            severity: String,
            cnt: u64,
        }

        // Total actions
        let total: u64 = self
            .db
            .clickhouse
            .query(&format!(
                "SELECT count() as cnt FROM audit_log WHERE event_time >= '{}' AND event_time < '{}'",
                period_start.format("%Y-%m-%d %H:%M:%S"),
                period_end.format("%Y-%m-%d %H:%M:%S")
            ))
            .fetch_one::<u64>()
            .await
            .unwrap_or(0);

        // By category
        let cat_rows = self
            .db
            .clickhouse
            .query(&format!(
                "SELECT category, count() as cnt FROM audit_log WHERE event_time >= '{}' AND event_time < '{}' GROUP BY category",
                period_start.format("%Y-%m-%d %H:%M:%S"),
                period_end.format("%Y-%m-%d %H:%M:%S")
            ))
            .fetch_all::<CategoryCount>()
            .await
            .unwrap_or_default();

        let mut actions_by_category = std::collections::HashMap::new();
        for row in &cat_rows {
            actions_by_category.insert(row.category.clone(), row.cnt);
        }

        // By severity
        let sev_rows = self
            .db
            .clickhouse
            .query(&format!(
                "SELECT severity, count() as cnt FROM audit_log WHERE event_time >= '{}' AND event_time < '{}' GROUP BY severity",
                period_start.format("%Y-%m-%d %H:%M:%S"),
                period_end.format("%Y-%m-%d %H:%M:%S")
            ))
            .fetch_all::<SeverityCount>()
            .await
            .unwrap_or_default();

        let mut actions_by_severity = std::collections::HashMap::new();
        for row in &sev_rows {
            actions_by_severity.insert(row.severity.clone(), row.cnt);
        }

        Ok(ComplianceReport {
            report_id: Uuid::new_v4(),
            period_start,
            period_end,
            total_actions: total,
            actions_by_category,
            actions_by_severity,
            security_events: *actions_by_category.get("Security").unwrap_or(&0),
            data_access_events: *actions_by_category.get("DataAccess").unwrap_or(&0),
            privacy_operations: *actions_by_category.get("PrivacyOperation").unwrap_or(&0),
            anomalies_detected: 0, // Computed separately
            generated_at: Utc::now(),
        })
    }

    /// Flush any remaining buffered entries
    pub async fn flush(&self) -> Result<()> {
        let mut buffer = self.buffer.lock().await;
        if !buffer.is_empty() {
            let batch: Vec<AuditEntry> = buffer.drain(..).collect();
            drop(buffer);
            self.flush_to_postgres(&batch).await?;
        }
        Ok(())
    }
}
