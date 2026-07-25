//! Superagent module — bridges the tools subsystem into the application.
//!
//! Contains the five superagent capability modules (flywheel, guardrails,
//! intelligence, memory, sync) and re-exports the OODAOrchestrator.
//!
//! The Axum router delegates to the orchestrator's own router for all
//! superagent control-plane endpoints.

pub mod flywheel;
pub mod guardrails;
pub mod intelligence;
pub mod memory;
pub mod sync;

pub use crate::tools::OODAOrchestrator;

// Re-export superagent engine types for convenience
pub use flywheel::FlywheelEngine;
pub use guardrails::GuardrailsEngine;
pub use intelligence::IntelligenceEngine;
pub use memory::MemoryEngine;
pub use sync::SyncEngine;

/// Build the superagent control-plane router.
///
/// Delegates to the full router defined in `crate::tools::ooda_orchestrator`,
/// which includes `/status`, `/cycle`, `/invoke`, `/alert/respond`, `/alerts`,
/// and `/history` endpoints.
pub fn router() -> axum::Router<std::sync::Arc<crate::db::AppState>> {
    crate::tools::ooda_orchestrator::router()
}
