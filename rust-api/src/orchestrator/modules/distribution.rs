// src/orchestrator/modules/distribution.rs

use super::*;
use crate::orchestrator::message_bus::*;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// DistributionAnalyzer: FMCG distribution gap analysis
///
/// Identifies regions where product supply doesn't meet demand.
/// Consumes MarketSignal outputs to detect supply-demand mismatches.
///
/// ⚠️  LIMITATION: All state is held in-memory HashMaps. Supply/demand indices
/// are lost on process restart. For production, wire to PostgreSQL.
/// See: TODO(DistributionAnalyzer-Persistence)
pub struct DistributionAnalyzer {
    /// Supply index per (region, product) — from transaction volume
    supply_index: HashMap<String, f64>,
    /// Demand index per (region, product) — from MarketAnalyzer signals
    demand_index: HashMap<String, f64>,
    /// Gap history for trend detection
    gap_history: HashMap<String, Vec<f64>>,
}

impl DistributionAnalyzer {
    pub fn new() -> Self {
        Self {
            supply_index: HashMap::new(),
            demand_index: HashMap::new(),
            gap_history: HashMap::new(),
        }
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
                // Update supply index from actual transaction volumes
                let mut by_category: HashMap<String, f64> = HashMap::new();
                for tx in &transactions {
                    *by_category.entry(tx.product_category.clone())
                        .or_insert(0.0) += tx.quantity.unwrap_or(1.0);
                }

                for (category, volume) in by_category {
                    let key = format!("{}:{}", region, category);
                    // EMA update
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

                // Compute gap
                let supply = self.supply_index.get(&key).copied().unwrap_or(1.0);
                let demand = demand_index;

                // Gap = demand / supply (1.0 = balanced, >1.0 = undersupply)
                let gap_ratio = if supply > 0.0 { demand / supply } else { 2.0 };

                // Track history
                let history = self.gap_history.entry(key.clone())
                    .or_insert_with(Vec::new);
                history.push(gap_ratio);
                if history.len() > 168 { // Keep 7 days of hourly data
                    history.remove(0);
                }

                // Only report significant gaps (demand > 30% above supply)
                if gap_ratio > 1.3 && sample_size >= 10 {
                    // Estimate opportunity size
                    // In production: use actual price data
                    let opportunity_size_usd = (gap_ratio - 1.0) * supply * 2.0; // rough estimate

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
            tracing::info!(keys = self.supply_index.len(), "DistributionAnalyzer state restored");
        }
    }
}
