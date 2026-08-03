//! OODA Loop Graph — Models the Observe-Orient-Decide-Act intelligence cycle
//! as a directed graph with conditional transitions.
//!
//! The OODA loop runs at four speeds:
//! - Fast: every sync event (real-time)
//! - Hourly: market aggregation
//! - Daily: intelligence reports, model checks
//! - Weekly: federated learning, full retrain evaluation

use chrono::{DateTime, Utc};

// Re-export the canonical CircuitBreaker from loops module to avoid duplication.
// This consolidates the 3 duplicate implementations into 1 canonical source.
pub use crate::loops::circuit_breaker::CircuitBreaker;
pub use crate::loops::circuit_breaker::CircuitBreakerConfig;
pub use crate::loops::circuit_breaker::CircuitState;
pub use crate::loops::circuit_breaker::FallbackStrategy;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use uuid::Uuid;

/// The four phases of the OODA loop.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum OodaPhase {
    Observe,
    Orient,
    Decide,
    Act,
}

/// Speed at which an OODA cycle runs.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum CycleSpeed {
    /// Every sync event — real-time signal processing
    Fast,
    /// Every hour — market aggregation, hourly signals
    Hourly,
    /// Daily at 00:00 UTC — intelligence reports, drift detection
    Daily,
    /// Weekly Sunday 02:00 UTC — federated learning, deep analysis
    Weekly,
}

/// Circuit breaker state for fault tolerance.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum CircuitState {
    /// Normal operation — requests pass through
    Closed,
    /// Too many failures — requests are rejected
    Open,
    /// Testing if service recovered — limited requests pass
    HalfOpen,
}

/// A node in the OODA graph representing one phase execution.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OodaNode {
    pub id: Uuid,
    pub phase: OodaPhase,
    pub cycle_id: Uuid,
    pub status: OodaNodeStatus,
    pub started_at: Option<DateTime<Utc>>,
    pub completed_at: Option<DateTime<Utc>>,
    pub duration_ms: Option<u64>,
    pub input_data: serde_json::Value,
    pub output_data: serde_json::Value,
    pub error_message: Option<String>,
    pub retry_count: u32,
    pub circuit_breaker: CircuitBreaker,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum OodaNodeStatus {
    Pending,
    Running,
    Completed,
    Failed,
    Skipped,
    CircuitOpen,
}

/// A directed edge in the OODA graph representing data flow between phases.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OodaEdge {
    pub id: Uuid,
    pub source_phase: OodaPhase,
    pub target_phase: OodaPhase,
    pub condition: Option<TransitionCondition>,
    pub data_schema: serde_json::Value, // JSON schema of data flowing through
}

/// Condition that must be true for a transition to fire.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum TransitionCondition {
    /// Always transition (default)
    Always,
    /// Transition only if threshold met
    Threshold {
        metric: String,
        operator: ComparisonOp,
        value: f64,
    },
    /// Transition based on classification result
    Classification {
        classifier: String,
        expected_class: String,
    },
    /// Transition if anomaly detected
    AnomalyDetected { sensitivity: f64 },
    /// Transition if model drift detected
    ModelDrift { drift_threshold: f64 },
    /// Human escalation required
    RequiresHumanApproval,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum ComparisonOp {
    GreaterThan,
    LessThan,
    Equal,
    GreaterThanOrEqual,
    LessThanOrEqual,
}

/// Helper: Create a simple per-node circuit breaker with default config.
/// Delegates to the canonical CircuitBreaker from the loops module.
pub fn make_node_circuit_breaker(
    service_name: &str,
    failure_threshold: u32,
    open_timeout_secs: u64,
) -> CircuitBreaker {
    CircuitBreaker::new(
        service_name.to_string(),
        CircuitBreakerConfig {
            failure_threshold,
            open_timeout: std::time::Duration::from_secs(open_timeout_secs),
            ..Default::default()
        },
        FallbackStrategy::FailFast {
            error: "Circuit breaker open".to_string(),
        },
    )
}

/// A complete OODA cycle instance.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OodaCycle {
    pub id: Uuid,
    pub speed: CycleSpeed,
    pub cycle_number: u64,
    pub started_at: DateTime<Utc>,
    pub completed_at: Option<DateTime<Utc>>,
    pub status: CycleStatus,
    pub phases: HashMap<OodaPhase, OodaNode>,
    pub edges: Vec<OodaEdge>,
    pub trigger_source: String,
    pub metadata: serde_json::Value,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum CycleStatus {
    Running,
    Completed,
    Failed,
    Cancelled,
}

/// The OODA graph structure — defines the topology of phase transitions.
///
/// Standard topology:
///   Observe → Orient → Decide → Act → (loop back to Observe)
///
/// With conditional branches:
///   Decide → Act (normal path)
///   Decide → Observe (re-observe if insufficient data)
///   Orient → Act (emergency fast-path if critical anomaly)
///   Any phase → Act (human override)
pub struct OodaGraph {
    pub nodes: Vec<OodaPhase>,
    pub edges: Vec<OodaEdge>,
    pub cycle_speed: CycleSpeed,
}

impl OodaGraph {
    /// Standard OODA topology for all cycle speeds.
    pub fn standard(speed: CycleSpeed) -> Self {
        let nodes = vec![
            OodaPhase::Observe,
            OodaPhase::Orient,
            OodaPhase::Decide,
            OodaPhase::Act,
        ];

        let edges = vec![
            // Primary flow: Observe → Orient → Decide → Act
            OodaEdge {
                id: Uuid::new_v4(),
                source_phase: OodaPhase::Observe,
                target_phase: OodaPhase::Orient,
                condition: Some(TransitionCondition::Always),
                data_schema: serde_json::json!({
                    "type": "observe_output",
                    "fields": ["signals", "anomalies", "time_context"]
                }),
            },
            OodaEdge {
                id: Uuid::new_v4(),
                source_phase: OodaPhase::Orient,
                target_phase: OodaPhase::Decide,
                condition: Some(TransitionCondition::Always),
                data_schema: serde_json::json!({
                    "type": "orient_output",
                    "fields": ["context", "trends", "risks", "opportunities"]
                }),
            },
            OodaEdge {
                id: Uuid::new_v4(),
                source_phase: OodaPhase::Decide,
                target_phase: OodaPhase::Act,
                condition: Some(TransitionCondition::Always),
                data_schema: serde_json::json!({
                    "type": "decide_output",
                    "fields": ["selected_action", "confidence", "reasoning"]
                }),
            },
            // Loop back: Act → Observe (next cycle)
            OodaEdge {
                id: Uuid::new_v4(),
                source_phase: OodaPhase::Act,
                target_phase: OodaPhase::Observe,
                condition: Some(TransitionCondition::Always),
                data_schema: serde_json::json!({
                    "type": "act_output",
                    "fields": ["action_result", "side_effects", "feedback"]
                }),
            },
            // Conditional: Decide → Observe (re-observe if data insufficient)
            OodaEdge {
                id: Uuid::new_v4(),
                source_phase: OodaPhase::Decide,
                target_phase: OodaPhase::Observe,
                condition: Some(TransitionCondition::Threshold {
                    metric: "data_confidence".to_string(),
                    operator: ComparisonOp::LessThan,
                    value: 0.5,
                }),
                data_schema: serde_json::json!({
                    "type": "reobserve_request",
                    "fields": ["missing_signals", "confidence_gap"]
                }),
            },
            // Emergency: Orient → Act (critical anomaly bypass)
            OodaEdge {
                id: Uuid::new_v4(),
                source_phase: OodaPhase::Orient,
                target_phase: OodaPhase::Act,
                condition: Some(TransitionCondition::AnomalyDetected { sensitivity: 0.95 }),
                data_schema: serde_json::json!({
                    "type": "emergency_action",
                    "fields": ["anomaly_type", "severity", "recommended_action"]
                }),
            },
        ];

        Self {
            nodes,
            edges,
            cycle_speed: speed,
        }
    }

    /// Get all valid transitions from a given phase.
    pub fn transitions_from(&self, phase: OodaPhase) -> Vec<&OodaEdge> {
        self.edges
            .iter()
            .filter(|e| e.source_phase == phase)
            .collect()
    }

    /// Get the default (always) transition from a phase.
    pub fn default_transition(&self, phase: OodaPhase) -> Option<&OodaEdge> {
        self.edges.iter().find(|e| {
            e.source_phase == phase
                && matches!(e.condition, Some(TransitionCondition::Always))
                && e.target_phase != OodaPhase::Observe // Exclude loop-back
        })
    }

    /// Check if a phase has a circuit breaker in open state.
    pub fn is_phase_available(&self, _phase: OodaPhase) -> bool {
        // In production, check the circuit breaker state from the database
        // This is a placeholder for the trait implementation
        true
    }
}

/// Observe phase: ingests all signals.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ObserveInput {
    /// Transaction syncs from devices
    pub sync_events: Vec<SyncEvent>,
    /// Market price movements
    pub market_signals: Vec<MarketSignal>,
    /// Buyer queries and requests
    pub buyer_queries: Vec<BuyerQuery>,
    /// Model drift signals
    pub drift_signals: Vec<DriftSignal>,
    /// Time context (hour, day, season, paydays)
    pub time_context: TimeContext,
    /// External data (weather, events, news)
    pub external_signals: Vec<ExternalSignal>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SyncEvent {
    pub device_id_hash: String,
    pub cohort_hash: String,
    pub transaction_count: u32,
    pub total_revenue: f64,
    pub top_categories: Vec<(String, f64)>,
    pub timestamp: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MarketSignal {
    pub product_category: String,
    pub region: String,
    pub price_current: f64,
    pub price_change_pct: f64,
    pub volume_change_pct: f64,
    pub signal_strength: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BuyerQuery {
    pub query_type: String,
    pub product_interest: String,
    pub region: String,
    pub timestamp: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DriftSignal {
    pub model_name: String,
    pub metric_name: String,
    pub current_value: f64,
    pub baseline_value: f64,
    pub drift_magnitude: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TimeContext {
    pub hour: u8,
    pub day_of_week: u8,
    pub is_payday: bool,
    pub is_month_end: bool,
    pub season: String,
    pub is_holiday: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExternalSignal {
    pub source: String,
    pub signal_type: String,
    pub data: serde_json::Value,
}

/// Orient phase output: synthesized context.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OrientOutput {
    /// Identified trends
    pub trends: Vec<Trend>,
    /// Detected anomalies
    pub anomalies: Vec<Anomaly>,
    /// Market opportunities
    pub opportunities: Vec<Opportunity>,
    /// Risk assessments
    pub risks: Vec<Risk>,
    /// Historical comparison context
    pub historical_context: HistoricalContext,
    /// Confidence in the orientation
    pub confidence: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Trend {
    pub dimension: String, // "price:tomatoes:nairobi"
    pub direction: TrendDirection,
    pub magnitude_pct: f64,
    pub duration: String, // "3 days", "2 weeks"
    pub confidence: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum TrendDirection {
    Rising,
    Falling,
    Stable,
    Volatile,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Anomaly {
    pub anomaly_type: String,
    pub severity: AnomalySeverity,
    pub affected_scope: String,
    pub description: String,
    pub detected_value: f64,
    pub expected_range: (f64, f64),
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum AnomalySeverity {
    Low,
    Medium,
    High,
    Critical,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Opportunity {
    pub opportunity_type: String,
    pub description: String,
    pub estimated_impact: f64,
    pub confidence: f64,
    pub time_window: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Risk {
    pub risk_type: String,
    pub description: String,
    pub probability: f64,
    pub impact: f64,
    pub mitigation: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HistoricalContext {
    pub similar_conditions_date: Option<DateTime<Utc>>,
    pub outcome_then: String,
    pub relevance_score: f64,
}

/// Decide phase: action selection.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DecideOutput {
    pub selected_action: Action,
    pub decision_source: DecisionSource,
    pub confidence: f64,
    pub alternatives_rejected: Vec<(Action, String)>, // (action, rejection_reason)
    pub requires_human_approval: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Action {
    pub action_type: ActionType,
    pub parameters: serde_json::Value,
    pub target: String,
    pub priority: ActionPriority,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum ActionType {
    GenerateIntelligenceReport,
    PushMarketSignal,
    TriggerModelRetrain,
    SendPartnerAlert,
    UpdateEconomicIndicator,
    AdjustCreditScore,
    GenerateRecommendation,
    NoAction,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum DecisionSource {
    RuleEngine,
    MLModel,
    LLMReasoning,
    HumanOverride,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
pub enum ActionPriority {
    Low,
    Medium,
    High,
    Critical,
}
