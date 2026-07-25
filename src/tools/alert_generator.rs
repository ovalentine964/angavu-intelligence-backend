//! AlertGenerator — Proactive alerts
//!
//! Generates proactive alerts based on anomaly detection, market changes,
//! goal milestones, credit score changes, and system health issues.
//! Integrates with WhatsAppSender for delivery to workers.

use anyhow::Result;
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::RwLock;
use uuid::Uuid;

use crate::db::DatabaseConnections;

/// Alert urgency levels
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, PartialOrd, Ord)]
pub enum AlertUrgency {
    Low,
    Medium,
    High,
    Critical,
}

/// Types of alerts the system can generate
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum AlertType {
    /// Transaction anomaly detected
    AnomalyDetected,
    /// Market condition change
    MarketChange,
    /// Worker goal milestone
    GoalMilestone,
    /// Credit score change
    CreditScoreChange,
    /// Inventory stockout risk
    StockoutRisk,
    /// System health issue
    SystemHealth,
    /// Privacy threshold breach
    PrivacyBreach,
    /// Federated learning round complete
    FederatedRoundComplete,
    /// Data sync issue
    SyncIssue,
    /// Custom alert from OODA cycle
    OODACycle,
}

/// An alert instance
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Alert {
    pub alert_id: Uuid,
    pub alert_type: AlertType,
    pub urgency: AlertUrgency,
    pub title: String,
    pub message: String,
    pub source: String,
    pub confidence: f64,
    pub action_required: bool,
    pub suggested_action: Option<String>,
    pub data: serde_json::Value,
    pub recipients: Vec<String>,
    pub delivery_channels: Vec<DeliveryChannel>,
    pub created_at: DateTime<Utc>,
    pub delivered_at: Option<DateTime<Utc>>,
    pub acknowledged_at: Option<DateTime<Utc>>,
}

/// Delivery channel for alerts
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum DeliveryChannel {
    WhatsApp,
    Sms,
    Email,
    PushNotification,
    WebDashboard,
    Webhook,
}

/// Alert rule for automatic triggering
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AlertRule {
    pub rule_id: Uuid,
    pub name: String,
    pub alert_type: AlertType,
    pub condition: AlertCondition,
    pub urgency: AlertUrgency,
    pub enabled: bool,
    pub cooldown_minutes: u32,
    pub last_triggered: Option<DateTime<Utc>>,
}

/// Condition that triggers an alert
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum AlertCondition {
    /// Anomaly score exceeds threshold
    AnomalyThreshold { min_score: f64 },
    /// Demand change exceeds percentage
    DemandChange { min_pct_change: f64 },
    /// Credit score drops below threshold
    CreditScoreBelow { min_score: u32 },
    /// Revenue drops below expected
    RevenueDrop { min_pct_drop: f64 },
    /// System error rate exceeds threshold
    ErrorRate { max_rate: f64 },
    /// Custom condition
    Custom { expression: String },
}

/// Alert statistics
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AlertStats {
    pub total_alerts: u64,
    pub alerts_by_type: HashMap<String, u64>,
    pub alerts_by_urgency: HashMap<String, u64>,
    pub avg_delivery_time_ms: f64,
    pub acknowledgment_rate: f64,
}

/// The AlertGenerator tool
pub struct AlertGenerator {
    db: DatabaseConnections,
    rules: Arc<RwLock<Vec<AlertRule>>>,
    recent_alerts: Arc<RwLock<Vec<Alert>>>,
    max_recent: usize,
}

impl AlertGenerator {
    pub fn new(db: DatabaseConnections) -> Self {
        let rules = vec![
            AlertRule {
                rule_id: Uuid::new_v4(),
                name: "high_anomaly".to_string(),
                alert_type: AlertType::AnomalyDetected,
                condition: AlertCondition::AnomalyThreshold { min_score: 0.8 },
                urgency: AlertUrgency::High,
                enabled: true,
                cooldown_minutes: 30,
                last_triggered: None,
            },
            AlertRule {
                rule_id: Uuid::new_v4(),
                name: "demand_surge".to_string(),
                alert_type: AlertType::MarketChange,
                condition: AlertCondition::DemandChange { min_pct_change: 25.0 },
                urgency: AlertUrgency::Medium,
                enabled: true,
                cooldown_minutes: 60,
                last_triggered: None,
            },
            AlertRule {
                rule_id: Uuid::new_v4(),
                name: "credit_drop".to_string(),
                alert_type: AlertType::CreditScoreChange,
                condition: AlertCondition::CreditScoreBelow { min_score: 400 },
                urgency: AlertUrgency::High,
                enabled: true,
                cooldown_minutes: 1440, // Daily
                last_triggered: None,
            },
            AlertRule {
                rule_id: Uuid::new_v4(),
                name: "system_errors".to_string(),
                alert_type: AlertType::SystemHealth,
                condition: AlertCondition::ErrorRate { max_rate: 0.05 },
                urgency: AlertUrgency::Critical,
                enabled: true,
                cooldown_minutes: 5,
                last_triggered: None,
            },
        ];

        Self {
            db,
            rules: Arc::new(RwLock::new(rules)),
            recent_alerts: Arc::new(RwLock::new(Vec::new())),
            max_recent: 1000,
        }
    }

    /// Generate an alert (used by OODAOrchestrator)
    pub async fn generate_alert(
        &self,
        source: &str,
        message: &str,
        confidence: f64,
    ) -> Result<Uuid> {
        self.create_alert(Alert {
            alert_id: Uuid::new_v4(),
            alert_type: AlertType::OODACycle,
            urgency: if confidence > 0.9 {
                AlertUrgency::High
            } else if confidence > 0.7 {
                AlertUrgency::Medium
            } else {
                AlertUrgency::Low
            },
            title: format!("OODA Alert from {}", source),
            message: message.to_string(),
            source: source.to_string(),
            confidence,
            action_required: confidence > 0.8,
            suggested_action: None,
            data: serde_json::json!({
                "source": source,
                "confidence": confidence,
            }),
            recipients: vec![],
            delivery_channels: vec![DeliveryChannel::WebDashboard],
            created_at: Utc::now(),
            delivered_at: None,
            acknowledged_at: None,
        })
        .await
    }

    /// Create and store an alert
    pub async fn create_alert(&self, alert: Alert) -> Result<Uuid> {
        let alert_id = alert.alert_id;

        // Store in PostgreSQL
        let _ = sqlx::query(
            "INSERT INTO alerts (id, alert_type, urgency, title, message, source, confidence, action_required, data, created_at) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)"
        )
        .bind(alert_id)
        .bind(format!("{:?}", alert.alert_type))
        .bind(format!("{:?}", alert.urgency))
        .bind(&alert.title)
        .bind(&alert.message)
        .bind(&alert.source)
        .bind(alert.confidence)
        .bind(alert.action_required)
        .bind(&alert.data)
        .bind(alert.created_at)
        .execute(&self.db.postgres)
        .await;

        // Store in ClickHouse for analytics
        #[derive(clickhouse::Row, Serialize)]
        struct AlertRow {
            alert_id: String,
            alert_type: String,
            urgency: String,
            source: String,
            confidence: f64,
            event_time: chrono::NaiveDateTime,
        }

        let row = AlertRow {
            alert_id: alert_id.to_string(),
            alert_type: format!("{:?}", alert.alert_type),
            urgency: format!("{:?}", alert.urgency),
            source: alert.source.clone(),
            confidence: alert.confidence,
            event_time: alert.created_at.naive_utc(),
        };

        if let Ok(mut insert) = self.db.clickhouse.insert("alerts") {
            let _ = insert.write(&row).await;
            let _ = insert.end().await;
        }

        // Keep in recent memory
        {
            let mut recent = self.recent_alerts.write().await;
            recent.push(alert);
            if recent.len() > self.max_recent {
                recent.remove(0);
            }
        }

        Ok(alert_id)
    }

    /// Evaluate all rules against current data
    pub async fn evaluate_rules(
        &self,
        anomaly_score: Option<f64>,
        demand_change_pct: Option<f64>,
        credit_score: Option<u32>,
        error_rate: Option<f64>,
    ) -> Result<Vec<Uuid>> {
        let mut triggered = Vec::new();
        let now = Utc::now();

        let mut rules = self.rules.write().await;
        for rule in rules.iter_mut() {
            if !rule.enabled {
                continue;
            }

            // Check cooldown
            if let Some(last) = rule.last_triggered {
                let elapsed = now.signed_duration_since(last).num_minutes() as u32;
                if elapsed < rule.cooldown_minutes {
                    continue;
                }
            }

            let should_trigger = match &rule.condition {
                AlertCondition::AnomalyThreshold { min_score } => {
                    anomaly_score.map(|s| s >= *min_score).unwrap_or(false)
                }
                AlertCondition::DemandChange { min_pct_change } => {
                    demand_change_pct
                        .map(|p| p.abs() >= *min_pct_change)
                        .unwrap_or(false)
                }
                AlertCondition::CreditScoreBelow { min_score } => {
                    credit_score.map(|s| s < *min_score).unwrap_or(false)
                }
                AlertCondition::ErrorRate { max_rate } => {
                    error_rate.map(|r| r > *max_rate).unwrap_or(false)
                }
                AlertCondition::RevenueDrop { min_pct_drop } => {
                    demand_change_pct
                        .map(|p| p <= -*min_pct_drop)
                        .unwrap_or(false)
                }
                AlertCondition::Custom { .. } => false, // Requires external evaluation
            };

            if should_trigger {
                let alert_id = self
                    .create_alert(Alert {
                        alert_id: Uuid::new_v4(),
                        alert_type: rule.alert_type.clone(),
                        urgency: rule.urgency.clone(),
                        title: format!("Rule triggered: {}", rule.name),
                        message: format!(
                            "Alert rule '{}' triggered with condition {:?}",
                            rule.name, rule.condition
                        ),
                        source: "rule_engine".to_string(),
                        confidence: 0.9,
                        action_required: rule.urgency >= AlertUrgency::High,
                        suggested_action: None,
                        data: serde_json::json!({
                            "rule_id": rule.rule_id,
                            "rule_name": rule.name,
                            "anomaly_score": anomaly_score,
                            "demand_change": demand_change_pct,
                            "credit_score": credit_score,
                            "error_rate": error_rate,
                        }),
                        recipients: vec![],
                        delivery_channels: vec![
                            DeliveryChannel::WebDashboard,
                            DeliveryChannel::PushNotification,
                        ],
                        created_at: now,
                        delivered_at: None,
                        acknowledged_at: None,
                    })
                    .await?;

                rule.last_triggered = Some(now);
                triggered.push(alert_id);
            }
        }

        Ok(triggered)
    }

    /// Get recent alerts
    pub async fn get_recent(&self, limit: usize) -> Vec<Alert> {
        let recent = self.recent_alerts.read().await;
        recent.iter().rev().take(limit).cloned().collect()
    }

    /// Get alert statistics
    pub async fn get_stats(&self) -> AlertStats {
        let recent = self.recent_alerts.read().await;
        let mut alerts_by_type: HashMap<String, u64> = HashMap::new();
        let mut alerts_by_urgency: HashMap<String, u64> = HashMap::new();

        for alert in recent.iter() {
            *alerts_by_type
                .entry(format!("{:?}", alert.alert_type))
                .or_insert(0) += 1;
            *alerts_by_urgency
                .entry(format!("{:?}", alert.urgency))
                .or_insert(0) += 1;
        }

        let acknowledged = recent.iter().filter(|a| a.acknowledged_at.is_some()).count();

        AlertStats {
            total_alerts: recent.len() as u64,
            alerts_by_type,
            alerts_by_urgency,
            avg_delivery_time_ms: 0.0, // Computed from delivery logs
            acknowledgment_rate: if recent.is_empty() {
                0.0
            } else {
                acknowledged as f64 / recent.len() as f64
            },
        }
    }

    /// Acknowledge an alert
    pub async fn acknowledge(&self, alert_id: Uuid) -> Result<bool> {
        let mut recent = self.recent_alerts.write().await;
        if let Some(alert) = recent.iter_mut().find(|a| a.alert_id == alert_id) {
            alert.acknowledged_at = Some(Utc::now());

            let _ = sqlx::query(
                "UPDATE alerts SET acknowledged_at = $1 WHERE id = $2"
            )
            .bind(Utc::now())
            .bind(alert_id)
            .execute(&self.db.postgres)
            .await;

            Ok(true)
        } else {
            Ok(false)
        }
    }
}
