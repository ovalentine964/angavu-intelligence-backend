// src/orchestrator/modules/mod.rs

pub mod credit;
pub mod distribution;
pub mod economic;
pub mod fiscal_impact; // Policy impact on informal workers
pub mod fmcg;
pub mod gender_inequality; // Gender-disaggregated Gini, Theil, wage gap
pub mod governance_quality;
pub mod health;
pub mod health_economics; // QALY/DALY calculations
pub mod inequality; // P1: Inequality tracker (Gini, Palma, Theil) for economic analysis
pub mod market;
pub mod market_concentration; // HHI, concentration ratios by sector
pub mod occupation_hazard_matrix; // Formal risk scoring per worker type
pub mod property_rights; // Informal property documentation scoring
pub mod service_price_discovery;
pub mod trade_gravity; // Gravity model for trade flow prediction // Institutional quality measurement

use super::message_bus::{ModuleId, ModuleMessage};
use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::Arc;
use tokio::sync::RwLock;
use tracing::{error, info, warn};

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
    fn queue_depth(&self) -> u64 {
        0
    }

    /// Serialize module state for periodic persistence.
    /// Returns None if the module has no state worth persisting.
    /// Default implementation returns None.
    fn snapshot_state(&self) -> Option<Vec<u8>> {
        None
    }

    /// Restore module state from a previous snapshot.
    /// Default implementation is a no-op.
    fn restore_state(&mut self, _data: &[u8]) {}
}

/// Persistent state store for module snapshots.
/// Uses a file-backed JSON store so state survives restarts.
/// In production, replace with PostgreSQL or Redis.
pub struct ModuleStateStore {
    /// Directory for state files
    state_dir: PathBuf,
    /// In-memory cache of latest snapshots (module_id → serialized bytes)
    cache: Arc<RwLock<HashMap<ModuleId, Vec<u8>>>>,
}

impl ModuleStateStore {
    /// Create a new state store backed by the given directory.
    pub fn new(state_dir: PathBuf) -> Self {
        std::fs::create_dir_all(&state_dir).ok();
        Self {
            state_dir,
            cache: Arc::new(RwLock::new(HashMap::new())),
        }
    }

    /// Save a module's snapshot to disk and cache.
    pub async fn save(&self, module_id: ModuleId, data: &[u8]) {
        // Update cache
        self.cache.write().await.insert(module_id, data.to_vec());

        // Persist to disk (async via spawn_blocking)
        let path = self.snapshot_path(module_id);
        let data_owned = data.to_vec();
        tokio::task::spawn_blocking(move || {
            if let Err(e) = std::fs::write(&path, &data_owned) {
                error!(module = ?module_id, error = %e, "Failed to persist module state");
            }
        })
        .await
        .ok();
    }

    /// Load a module's snapshot from cache or disk.
    pub async fn load(&self, module_id: ModuleId) -> Option<Vec<u8>> {
        // Check cache first
        {
            let cache = self.cache.read().await;
            if let Some(data) = cache.get(&module_id) {
                return Some(data.clone());
            }
        }

        // Fall back to disk
        let path = self.snapshot_path(module_id);
        match tokio::task::spawn_blocking(move || std::fs::read(&path)).await {
            Ok(Ok(data)) => {
                // Populate cache
                self.cache.write().await.insert(module_id, data.clone());
                Some(data)
            }
            _ => None,
        }
    }

    fn snapshot_path(&self, module_id: ModuleId) -> PathBuf {
        self.state_dir.join(format!("{:?}.snapshot.bin", module_id))
    }
}

/// Periodic state persistence task.
/// Snapshots all modules every `interval_secs` seconds.
pub async fn periodic_state_persistence(
    modules: Arc<RwLock<Vec<(ModuleId, Box<dyn CapabilityModule>)>>>,
    store: Arc<ModuleStateStore>,
    interval_secs: u64,
) {
    let mut interval = tokio::time::interval(std::time::Duration::from_secs(interval_secs));
    interval.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);

    loop {
        interval.tick().await;
        let modules_guard = modules.read().await;
        for (module_id, module) in modules_guard.iter() {
            if let Some(state) = module.snapshot_state() {
                store.save(*module_id, &state).await;
            }
        }
        drop(modules_guard);
    }
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
