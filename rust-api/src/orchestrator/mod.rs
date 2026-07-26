// src/orchestrator/mod.rs

pub mod message_bus;
pub mod collective_intelligence;
pub mod modules;
pub mod supervisor;

use message_bus::*;
use std::sync::Arc;
use tokio::sync::{mpsc, RwLock};
use tracing::{error, info, warn};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

/// The OODA loop phase
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum OODAPhase {
    Observe,
    Orient,
    Decide,
    Act,
    Learn,
}

/// System-wide state the orchestrator maintains
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OrchestratorState {
    /// Current OODA phase
    pub phase: OODAPhase,
    /// Cycle counter
    pub cycle_count: u64,
    /// Timestamp of current cycle start
    pub cycle_start: DateTime<Utc>,
    /// Active module health statuses
    pub module_health: std::collections::HashMap<ModuleId, ModuleHealth>,
    /// Pending anomalies requiring attention
    pub active_anomalies: Vec<AnomalyRecord>,
    /// Recent cross-module patterns detected
    pub recent_patterns: Vec<PatternRecord>,
    /// System-wide throughput (messages/sec)
    pub throughput: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModuleHealth {
    pub status: HealthStatus,
    pub queue_depth: u64,
    pub processing_rate: f64,
    pub last_heartbeat: DateTime<Utc>,
    pub restart_count: u32,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum HealthStatus {
    Healthy,
    Degraded,
    Unhealthy,
    Restarting,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AnomalyRecord {
    pub trace_id: TraceId,
    pub detected_at: DateTime<Utc>,
    pub anomaly_type: AnomalyType,
    pub severity: f64,
    pub resolved: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PatternRecord {
    pub detected_at: DateTime<Utc>,
    pub pattern_type: PatternType,
    pub modules: Vec<ModuleId>,
    pub strength: f64,
}

/// The trait defining the orchestrator's capabilities
#[async_trait::async_trait]
pub trait Orchestrator: Send + Sync {
    /// Run one complete OODA cycle
    async fn run_cycle(&self) -> Result<CycleResult, OrchestratorError>;

    /// Route an incoming message to the appropriate module(s)
    async fn route_message(&self, message: ModuleMessage) -> Result<(), OrchestratorError>;

    /// Get current orchestrator state
    async fn state(&self) -> OrchestratorState;

    /// Handle a module failure — restart if needed
    async fn handle_module_failure(
        &self,
        module_id: ModuleId,
        error: String,
    ) -> Result<(), OrchestratorError>;

    /// Graceful shutdown
    async fn shutdown(&self) -> Result<(), OrchestratorError>;
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CycleResult {
    pub phase: OODAPhase,
    pub cycle_number: u64,
    pub messages_processed: u64,
    pub anomalies_detected: u32,
    pub patterns_found: u32,
    pub duration_ms: u64,
    pub actions_taken: Vec<String>,
}

#[derive(Debug, thiserror::Error)]
pub enum OrchestratorError {
    #[error("Module not available: {0:?}")]
    ModuleUnavailable(ModuleId),
    #[error("Cycle timeout: phase {0:?} exceeded deadline")]
    CycleTimeout(OODAPhase),
    #[error("Bus error: {0}")]
    BusError(#[from] BusError),
    #[error("Internal error: {0}")]
    Internal(String),
}

/// Configuration for the OODA orchestrator
#[derive(Debug, Clone)]
pub struct OrchestratorConfig {
    /// How often to run a full OODA cycle (medium loop)
    pub cycle_interval_ms: u64,
    /// Timeout per OODA phase
    pub phase_timeout_ms: u64,
    /// How many cycles before deep analysis
    pub deep_analysis_interval: u64,
    /// Maximum anomalies before escalation
    pub anomaly_escalation_threshold: u32,
    /// Module restart cooldown (don't restart more often than this)
    pub restart_cooldown_secs: u64,
}

impl Default for OrchestratorConfig {
    fn default() -> Self {
        Self {
            cycle_interval_ms: 60_000,       // 1 minute medium loop
            phase_timeout_ms: 10_000,         // 10 seconds per phase
            deep_analysis_interval: 60,       // Deep analysis every 60 cycles (~1 hour)
            anomaly_escalation_threshold: 5,  // Escalate after 5 concurrent anomalies
            restart_cooldown_secs: 30,        // Wait 30s between restarts
        }
    }
}
