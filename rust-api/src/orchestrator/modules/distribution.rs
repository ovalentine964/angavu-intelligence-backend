// src/orchestrator/modules/distribution.rs
//
// DistributionAnalyzer: FMCG distribution gap analysis
// State persisted to PostgreSQL (table: distribution_gaps).

use super::*;
use crate::orchestrator::message_bus::*;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// DistributionAnalyzer: FMCG distribution gap analysis
///
/// Identifies regions where product supply doesn't meet demand.
/// Consumes MarketSignal outputs to detect supply-demand mismatches.
///
/// State is persisted to PostgreSQL (table: distribution_gaps) for
/// survival across process restarts.
pub struct DistributionAnalyzer {
    /// Supply index per (region, product) — from transaction volume
    supply_index: HashMap<String, f64>,
    /// Demand index per (region, product) — from MarketAnalyzer signals
    demand_index: HashMap<String, f64>,
    /// Gap history for trend detection
    gap_history: HashMap<String, Vec<f64>>,
    /// Database pool for state persistence
    pool: Option<sqlx::PgPool>,
}

impl DistributionAnalyzer {
    pub fn new() -> Self {
        Self {
            supply_index: HashMap::new(),
            demand_index: HashMap::new(),
            gap_history: HashMap::new(),
            pool: None,
        }
    }

    /// Create with database pool for state persistence.
    pub fn with_pool(pool: sqlx::PgPool) -> Self {
        Self {
            supply_index: HashMap::new(),
            demand_index: HashMap::new(),
            gap_history: HashMap::new(),
            pool: Some(pool),
        }
    }

    /// Load persisted state from PostgreSQL on startup.
    pub async fn load_state(&mut self) -> Result<(), String> {
        let pool = match &self.pool {
            Some(p) => p,
            None => return Ok(()),
        };

        let rows = sqlx::query!(
            "SELECT region, product_category, supply_index, demand_index,
                    gap_history::text as \"gap_history!\"
             FROM distribution_gaps"
        )
        .fetch_all(pool)
        .await
        .map_err(|e| format!("Failed to load distribution_gaps: {}", e))?;

        let mut count = 0;
        for row in rows {
            let key = format!("{}:{}", row.region, row.product_category);
            self.supply_index.insert(key.clone(), row.supply_index);
            self.demand_index.insert(key.clone(), row.demand_index);

            let history: Vec<f64> = serde_json::from_str(&row.gap_history).unwrap_or_default();
            if !history.is_empty() {
                self.gap_history.insert(key, history);
            }
            count += 1;
        }

        tracing::info!(gaps = count, "DistributionAnalyzer state loaded from PostgreSQL");
        Ok(())
    }

    /// Persist current state to PostgreSQL.
    pub async fn persist_state(&self) -> Result<(), String> {
        let pool = match &self.pool {
            Some(p) => p,
            None => return Ok(()),
        };

        // Collect all keys from all maps
        let mut keys: std::collections::HashSet<String> = std::collections::HashSet::new();
        keys.extend(self.supply_index.keys().cloned());
        keys.extend(self.demand_index.keys().cloned());
        keys.extend(self.gap_history.keys().cloned());

        for key in keys {
            let parts: Vec<&str> = key.splitn(2, ':').collect();
            if parts.len() != 2 { continue; }
            let (region, category) = (parts[0], parts[1]);

            let supply = self.supply_index.get(&key).copied().unwrap_or(0.0);
            let demand = self.demand_index.get(&key).copied().unwrap_or(0.0);
            let history_json = self.gap_history.get(&key)
                .map(|h| serde_json::to_string(h).unwrap_or_default())
                .unwrap_or_else(|| "[]".to_string());

            sqlx::query!(
                "INSERT INTO distribution_gaps
                    (region, product_category, supply_index, demand_index, gap_history, last_updated)
                 VALUES ($1, $2, $3, $4, $5::jsonb, NOW())
                 ON CONFLICT (region, product_category) DO UPDATE SET
                    supply_index = EXCLUDED.supply_index,
                    demand_index = EXCLUDED.demand_index,
                    gap_history = EXCLUDED.gap_history,
                    last_updated = NOW()",
                region,
                category,
                supply,
                demand,
                history_json,
            )
            .execute(pool)
            .await
            .map_err(|e| format!("Failed to persist distribution_gaps: {}", e))?;
        }

        tracing::info!(gaps = keys.len(), "DistributionAnalyzer state persisted to PostgreSQL");
        Ok(())
    }
}

#[async_trait::async_trait]
impl CapabilityModule for DistributionAnalyzer {
    fn id(&self) -> ModuleId {
        ModuleId::DistributionAnalyzer
    }

    async fn process(
        &mut self,
        message: ModuleMessage,
    ) -> Result<Option<ModuleMessage>, ModuleError> {
        match message {
            ModuleMessage::TransactionBatch {
                trace_id,
                transactions,
                region,
                ..
            } => {
                let mut by_category: HashMap<String, f64> = HashMap::new();
                for tx in &transactions {
                    *by_category.entry(tx.product_category.clone())
                        .or_insert(0.0) += tx.quantity.unwrap_or(1.0);
                }

                for (category, volume) in by_category {
                    let key = format!("{}:{}", region, category);
                    let current = self.supply_index.get(&key).copied().unwrap_or(0.0);
                    self.supply_index.insert(key, 0.9 * current + 0.1 * volume);
                }

                Ok(None)
            }
            ModuleMessage::MarketSignal {
                trace_id,
                region,
                product_category,
                demand_index,
                sample_size,
                ..
            } => {
                let key = format!("{}:{}", region, product_category);
                self.demand_index.insert(key.clone(), demand_index);

                let supply = self.supply_index.get(&key).copied().unwrap_or(1.0);
                let demand = demand_index;

                let gap_ratio = if supply > 0.0 { demand / supply } else { 2.0 };

                let history = self.gap_history.entry(key.clone())
                    .or_insert_with(Vec::new);
                history.push(gap_ratio);
                if history.len() > 168 {
                    history.remove(0);
                }

                if gap_ratio > 1.3 && sample_size >= 10 {
                    let opportunity_size_usd = (gap_ratio - 1.0) * supply * 2.0;

                    return Ok(Some(ModuleMessage::DistributionGap {
                        trace_id,
                        region,
                        product_category,
                        gap_severity: (gap_ratio - 1.0).min(1.0),
                        opportunity_size_usd,
                        affected_workers: sample_size,
                    }));
                }

                Ok(None)
            }
            _ => Ok(None),
        }
    }

    async fn shutdown(&self) {
        tracing::info!("DistributionAnalyzer shutting down");
        if let Err(e) = self.persist_state().await {
            tracing::error!("Failed to persist DistributionAnalyzer state on shutdown: {}", e);
        }
    }

    fn snapshot_state(&self) -> Option<Vec<u8>> {
        #[derive(Serialize)]
        struct Snapshot {
            supply_index: HashMap<String, f64>,
            demand_index: HashMap<String, f64>,
            gap_history: HashMap<String, Vec<f64>>,
        }
        bincode::serialize(&Snapshot {
            supply_index: self.supply_index.clone(),
            demand_index: self.demand_index.clone(),
            gap_history: self.gap_history.clone(),
        }).ok()
    }

    fn restore_state(&mut self, data: &[u8]) {
        #[derive(Deserialize)]
        struct Snapshot {
            supply_index: HashMap<String, f64>,
            demand_index: HashMap<String, f64>,
            gap_history: HashMap<String, Vec<f64>>,
        }
        if let Ok(snap) = bincode::deserialize::<Snapshot>(data) {
            self.supply_index = snap.supply_index;
            self.demand_index = snap.demand_index;
            self.gap_history = snap.gap_history;
            tracing::info!(keys = self.supply_index.len(), "DistributionAnalyzer state restored (fallback bincode)");
        }
    }
}
