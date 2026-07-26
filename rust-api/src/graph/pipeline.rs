//! Intelligence Pipeline DAG — Models the data processing pipeline as a
//! directed acyclic graph with circuit breakers and parallel execution.
//!
//! Pipeline: Sync → Anonymize → Aggregate → Analyze → Generate → Distribute
//!
//! Each step can fail independently (circuit breaker per node).
//! Steps with no dependencies execute in parallel.

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet, VecDeque};
use uuid::Uuid;

use super::ooda::{CircuitBreaker, CircuitState};

/// A node in the pipeline DAG.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PipelineNode {
    pub id: Uuid,
    pub name: String,
    pub node_type: PipelineNodeType,
    pub status: PipelineNodeStatus,
    pub depends_on: Vec<String>,        // names of nodes this depends on
    pub circuit_breaker: CircuitBreaker,
    pub max_retries: u32,
    pub retry_count: u32,
    pub timeout_ms: u64,
    pub started_at: Option<DateTime<Utc>>,
    pub completed_at: Option<DateTime<Utc>>,
    pub duration_ms: Option<u64>,
    pub input_data: serde_json::Value,
    pub output_data: serde_json::Value,
    pub error: Option<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum PipelineNodeType {
    /// Sync data from devices
    Sync,
    /// Anonymize data (strip PII, add DP noise)
    Anonymize,
    /// Aggregate across cohorts and regions
    Aggregate,
    /// Run analysis (ML models, pattern detection)
    Analyze,
    /// Generate intelligence outputs (reports, signals)
    Generate,
    /// Distribute results to consumers
    Distribute,
    /// Custom node type for extensibility
    Custom(String),
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum PipelineNodeStatus {
    Pending,
    Running,
    Completed,
    Failed,
    Skipped,
    Retrying,
    CircuitOpen,
}

/// The complete pipeline DAG.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PipelineDag {
    pub id: Uuid,
    pub name: String,
    pub nodes: HashMap<String, PipelineNode>,
    pub execution_order: Vec<Vec<String>>,  // topological levels (parallel groups)
    pub created_at: DateTime<Utc>,
}

impl PipelineDag {
    /// Create the standard intelligence pipeline DAG.
    ///
    /// Topology:
    ///
