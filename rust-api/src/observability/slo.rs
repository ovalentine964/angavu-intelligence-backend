// SLO (Service Level Objective) definitions and tracking
// Defines and monitors SLOs for Angavu Intelligence Backend

use chrono::{DateTime, Utc};
use parking_lot::RwLock;
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use tracing::warn;

/// SLO definitions for Angavu Intelligence Backend
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SloDefinition {
    pub name: String,
    pub description: String,
    pub target_percent: f64,
    pub window_days: u32,
    pub metric_query: String,
    pub severity: SloSeverity,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum SloSeverity {
    Critical,
    Warning,
}

/// Current SLO status
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SloStatus {
    pub definition: SloDefinition,
    pub current_value: f64,
    pub is_met: bool,
    pub error_budget_remaining_percent: f64,
    pub last_checked: DateTime<Utc>,
}

/// SLO tracker — monitors SLO compliance
pub struct SloTracker {
    slos: Vec<SloDefinition>,
    statuses: Arc<RwLock<Vec<SloStatus>>>,
}

impl SloTracker {
    /// Create a new SLO tracker with default Angavu SLOs.
    pub fn new() -> Self {
        let slos = vec![
            SloDefinition {
                name: "api_availability".to_string(),
                description: "API availability (non-5xx responses)".to_string(),
                target_percent: 99.9,
                window_days: 30,
                metric_query: "(1 - rate(http_requests_total{status=~\"5..\"}[30d]) / rate(http_requests_total[30d])) * 100".to_string(),
                severity: SloSeverity::Critical,
            },
            SloDefinition {
                name: "sync_success_rate".to_string(),
                description: "Sync pipeline success rate".to_string(),
                target_percent: 99.0,
                window_days: 7,
                metric_query: "rate(sync_operations_total{status=\"success\"}[7d]) / rate(sync_operations_total[7d]) * 100".to_string(),
                severity: SloSeverity::Critical,
            },
            SloDefinition {
                name: "intent_classification_accuracy".to_string(),
                description: "Agent intent classification accuracy".to_string(),
                target_percent: 90.0,
                window_days: 7,
                metric_query: "avg(intent_classification_accuracy) * 100".to_string(),
                severity: SloSeverity::Warning,
            },
            SloDefinition {
                name: "credit_scoring_accuracy".to_string(),
                description: "Credit scoring model accuracy".to_string(),
                target_percent: 80.0,
                window_days: 30,
                metric_query: "avg(credit_score_accuracy) * 100".to_string(),
                severity: SloSeverity::Warning,
            },
        ];

        Self {
            slos,
            statuses: Arc::new(RwLock::new(Vec::new())),
        }
    }

    /// Get all SLO definitions.
    pub fn definitions(&self) -> &[SloDefinition] {
        &self.slos
    }

    /// Update SLO status (called by metrics collector).
    pub fn update_status(&self, name: &str, current_value: f64) {
        let mut statuses = self.statuses.write();
        if let Some(def) = self.slos.iter().find(|s| s.name == name) {
            let is_met = current_value >= def.target_percent;
            let error_budget_total = 100.0 - def.target_percent;
            let error_budget_used = 100.0 - current_value;
            let error_budget_remaining =
                ((error_budget_total - error_budget_used) / error_budget_total * 100.0).max(0.0);

            if !is_met {
                warn!(
                    slo = name,
                    current = current_value,
                    target = def.target_percent,
                    "SLO BREACH detected"
                );
            }

            let status = SloStatus {
                definition: def.clone(),
                current_value,
                is_met,
                error_budget_remaining_percent: error_budget_remaining,
                last_checked: Utc::now(),
            };

            if let Some(existing) = statuses.iter_mut().find(|s| s.definition.name == name) {
                *existing = status;
            } else {
                statuses.push(status);
            }
        }
    }

    /// Get current SLO statuses.
    pub fn statuses(&self) -> Vec<SloStatus> {
        self.statuses.read().clone()
    }

    /// Get SLOs that are currently breached.
    pub fn breached_slos(&self) -> Vec<SloStatus> {
        self.statuses
            .read()
            .iter()
            .filter(|s| !s.is_met)
            .cloned()
            .collect()
    }

    /// Export SLO statuses as JSON (for API endpoint).
    pub fn to_json(&self) -> String {
        serde_json::to_string_pretty(&self.statuses()).unwrap_or_default()
    }
}
