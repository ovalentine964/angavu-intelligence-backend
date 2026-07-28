// Agent reasoning trace logging for Angavu Intelligence Backend
// Stores structured traces of agent runs for debugging and analysis

use serde::{Deserialize, Serialize};
use chrono::{DateTime, Utc};
use uuid::Uuid;
use sqlx::PgPool;
use tracing::{info, debug};

/// A single agent reasoning trace
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentTrace {
    pub trace_id: String,
    pub session_id: String,
    pub agent_type: String,
    pub started_at: DateTime<Utc>,
    pub completed_at: Option<DateTime<Utc>>,
    pub steps: Vec<TraceStep>,
    pub outcome: Option<TraceOutcome>,
    pub metadata: TraceMetadata,
}

/// A single step in the agent reasoning chain
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TraceStep {
    pub step_id: String,
    pub step_type: TraceStepType,
    pub timestamp: DateTime<Utc>,
    pub duration_ms: u64,
    pub input_summary: String,
    pub output_summary: String,
    pub success: bool,
    pub error: Option<String>,
}

/// Types of trace steps
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum TraceStepType {
    IntentClassification,
    ToolSelection,
    ToolExecution,
    LlmInference,
    ResponseGeneration,
    CreditScoring,
    SyncOperation,
}

/// Outcome of an agent trace
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TraceOutcome {
    pub success: bool,
    pub response_type: String,
    pub confidence: f64,
    pub tokens_used: u64,
}

/// Anonymized metadata (safe for cloud sync)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TraceMetadata {
    pub device_type: String,
    pub app_version: String,
    pub region: Option<String>,
    pub worker_type: Option<String>,
}

/// Agent trace logger — stores traces locally and syncs to backend
pub struct AgentTraceLogger {
    db: PgPool,
}

impl AgentTraceLogger {
    pub fn new(db: PgPool) -> Self {
        Self { db }
    }

    /// Store a completed agent trace in PostgreSQL.
    pub async fn store_trace(&self, trace: &AgentTrace) -> anyhow::Result<()> {
        sqlx::query(
            r#"
            INSERT INTO agent_traces (
                trace_id, session_id, agent_type, started_at, completed_at,
                steps, outcome, metadata, created_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
            ON CONFLICT (trace_id) DO NOTHING
            "#,
        )
        .bind(&trace.trace_id)
        .bind(&trace.session_id)
        .bind(&trace.agent_type)
        .bind(&trace.started_at)
        .bind(&trace.completed_at)
        .bind(serde_json::to_value(&trace.steps)?)
        .bind(serde_json::to_value(&trace.outcome)?)
        .bind(serde_json::to_value(&trace.metadata)?)
        .execute(&self.db)
        .await?;

        debug!(trace_id = %trace.trace_id, "Agent trace stored");
        Ok(())
    }

    /// Retrieve recent traces for a session.
    pub async fn get_session_traces(
        &self,
        session_id: &str,
        limit: i64,
    ) -> anyhow::Result<Vec<AgentTrace>> {
        let rows: Vec<(String, String, String, DateTime<Utc>, Option<DateTime<Utc>>, serde_json::Value, Option<serde_json::Value>, serde_json::Value)> = sqlx::query_as(
            r#"
            SELECT trace_id, session_id, agent_type, started_at, completed_at,
                   steps, outcome, metadata
            FROM agent_traces
            WHERE session_id = $1
            ORDER BY started_at DESC
            LIMIT $2
            "#,
        )
        .bind(session_id)
        .bind(limit)
        .fetch_all(&self.db)
        .await?;

        let traces = rows
            .into_iter()
            .map(|(trace_id, session_id, agent_type, started_at, completed_at, steps, outcome, metadata)| {
                AgentTrace {
                    trace_id,
                    session_id,
                    agent_type,
                    started_at,
                    completed_at,
                    steps: serde_json::from_value(steps).unwrap_or_default(),
                    outcome: outcome.and_then(|o| serde_json::from_value(o).ok()),
                    metadata: serde_json::from_value(metadata).unwrap_or(TraceMetadata {
                        device_type: "unknown".to_string(),
                        app_version: "unknown".to_string(),
                        region: None,
                        worker_type: None,
                    }),
                }
            })
            .collect();

        Ok(traces)
    }

    /// Get trace statistics for dashboard.
    pub async fn get_trace_stats(&self, hours: i64) -> anyhow::Result<TraceStats> {
        let stats: (i64, i64, Option<f64>, Option<f64>) = sqlx::query_as(
            r#"
            SELECT
                COUNT(*) as total_traces,
                COUNT(*) FILTER (WHERE (outcome->>'success')::boolean = true) as successful,
                AVG((outcome->>'confidence')::float) as avg_confidence,
                AVG((outcome->>'tokens_used')::bigint) as avg_tokens
            FROM agent_traces
            WHERE started_at > NOW() - make_interval(hours => $1)
            "#,
        )
        .bind(hours)
        .fetch_one(&self.db)
        .await?;

        Ok(TraceStats {
            total_traces: stats.0,
            successful_traces: stats.1,
            avg_confidence: stats.2.unwrap_or(0.0),
            avg_tokens_used: stats.3.unwrap_or(0.0) as u64,
            time_range_hours: hours,
        })
    }
}

/// Aggregated trace statistics
#[derive(Debug, Serialize)]
pub struct TraceStats {
    pub total_traces: i64,
    pub successful_traces: i64,
    pub avg_confidence: f64,
    pub avg_tokens_used: u64,
    pub time_range_hours: i64,
}

/// Create the agent_traces table migration.
pub const CREATE_TABLE_MIGRATION: &str = r#"
CREATE TABLE IF NOT EXISTS agent_traces (
    trace_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    agent_type TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    steps JSONB NOT NULL DEFAULT '[]',
    outcome JSONB,
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_traces_session ON agent_traces(session_id);
CREATE INDEX IF NOT EXISTS idx_agent_traces_started ON agent_traces(started_at);
CREATE INDEX IF NOT EXISTS idx_agent_traces_type ON agent_traces(agent_type);
"#;
