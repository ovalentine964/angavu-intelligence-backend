// src/orchestrator/modules/mod.rs

pub mod market;
pub mod credit;
pub mod distribution;
pub mod fmcg;
pub mod health;
pub mod economic;

use super::message_bus::{ModuleMessage, ModuleId};

/// Trait that all capability modules implement
#[async_trait::async_trait]
pub trait CapabilityModule: Send + Sync {
    /// Process an incoming message, optionally producing an output message
    async fn process(
        &mut self,
        message: ModuleMessage,
    ) -> Result<Option<ModuleMessage>, ModuleError>;

    /// Module identifier
    fn id(&self) -> ModuleId;

    /// Graceful shutdown hook
    async fn shutdown(&self) {}

    /// Current queue depth (for health reporting)
    fn queue_depth(&self) -> u64 { 0 }
}

#[derive(Debug, thiserror::Error)]
pub enum ModuleError {
    #[error("Processing error: {0}")]
    Processing(String),
    #[error("Data insufficient: {0}")]
    InsufficientData(String),
    #[error("Model error: {0}")]
   ModelError(String),
}
