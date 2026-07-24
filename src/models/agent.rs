use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

/// Agent types
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum AgentType {
    Orchestrator,
    Analyst,
    Forecaster,
    Monitor,
    Advisor,
    Aggregator,
}

/// Agent status
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum AgentStatus {
    Idle,
    Processing,
    Waiting,
    Error,
    Shutdown,
}

/// Agent instance
#[derive(Debug, Clone, Serialize, Deserialize, sqlx::FromRow)]
pub struct Agent {
    pub id: Uuid,
    pub agent_type: AgentType,
    pub name: String,
    pub description: String,
    pub status: AgentStatus,
    pub capabilities: Vec<String>,
    pub config: serde_json::Value,
    pub last_heartbeat: DateTime<Utc>,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
    pub metadata: serde_json::Value,
}

/// Agent task
#[derive(Debug, Clone, Serialize, Deserialize, sqlx::FromRow)]
pub struct AgentTask {
    pub id: Uuid,
    pub agent_id: Uuid,
    pub task_type: String,
    pub priority: i32,
    pub status: TaskStatus,
    pub input: serde_json::Value,
    pub output: Option<serde_json::Value>,
    pub error: Option<String>,
    pub retry_count: i32,
    pub max_retries: i32,
    pub started_at: Option<DateTime<Utc>>,
    pub completed_at: Option<DateTime<Utc>>,
    pub created_at: DateTime<Utc>,
    pub created_by: Uuid,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum TaskStatus {
    Queued,
    Running,
    Completed,
    Failed,
    Cancelled,
    Retrying,
}

/// Agent message
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentMessage {
    pub id: Uuid,
    pub from_agent: Uuid,
    pub to_agent: Option<Uuid>,
    pub message_type: MessageType,
    pub content: serde_json::Value,
    pub priority: i32,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum MessageType {
    Task,
    Result,
    Query,
    Response,
    Alert,
    Heartbeat,
}

/// Agent metrics
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentMetrics {
    pub agent_id: Uuid,
    pub tasks_completed: i64,
    pub tasks_failed: i64,
    pub avg_processing_time_ms: f64,
    pub uptime_seconds: i64,
    pub memory_usage_mb: f64,
    pub cpu_usage_percent: f64,
    pub last_updated: DateTime<Utc>,
}

/// OODA cycle result
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OODACycleResult {
    pub cycle_id: Uuid,
    pub phase: OODAPhase,
    pub observations: Vec<Observation>,
    pub orientation: Option<Orientation>,
    pub decision: Option<Decision>,
    pub action: Option<Action>,
    pub duration_ms: u64,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum OODAPhase {
    Observe,
    Orient,
    Decide,
    Act,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Observation {
    pub source: String,
    pub data_type: String,
    pub value: serde_json::Value,
    pub confidence: f64,
    pub timestamp: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Orientation {
    pub context: serde_json::Value,
    pub patterns: Vec<Pattern>,
    pub anomalies: Vec<Anomaly>,
    pub confidence: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Pattern {
    pub pattern_type: String,
    pub description: String,
    pub strength: f64,
    pub supporting_data: serde_json::Value,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Anomaly {
    pub anomaly_type: String,
    pub description: String,
    pub severity: f64,
    pub detected_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Decision {
    pub decision_type: String,
    pub rationale: String,
    pub options: Vec<DecisionOption>,
    pub selected_option: String,
    pub confidence: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DecisionOption {
    pub option_id: String,
    pub description: String,
    pub expected_outcome: String,
    pub risk_score: f64,
    pub confidence: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Action {
    pub action_type: String,
    pub parameters: serde_json::Value,
    pub expected_impact: String,
    pub executed_at: DateTime<Utc>,
    pub result: Option<serde_json::Value>,
}
