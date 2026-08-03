// Observability module for Angavu Intelligence Backend
// Provides Prometheus metrics, OpenTelemetry tracing, and SLO tracking

pub mod agent_traces;
pub mod agi_training_data;
pub mod metrics;
pub mod slo;

pub use agent_traces::AgentTraceLogger;
pub use metrics::MetricsLayer;
pub use slo::SloTracker;
