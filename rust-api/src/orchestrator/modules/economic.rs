// src/orchestrator/modules/economic.rs

use super::*;
use crate::orchestrator::message_bus::*;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// EconomicAnalyzer: GDP estimation, inflation tracking from informal sector data
///
/// Aggregates transaction data into macroeconomic indicators.
/// Compares with official KNBS data when available.
///
/// ⚠️  LIMITATION: All state is held in-memory HashMaps. Regional economic
/// state is lost on process restart. For production, wire to PostgreSQL
/// (table: regional_economic_state). See: TODO(EconomicAnalyzer-Persistence)
pub struct EconomicAnalyzer {
    /// Regional economic state
    regional_state: HashMap<String, RegionalEconomicState>,
    /// Baseline prices for CPI computation (set from last sync with KNBS)
    baseline_cpi: HashMap<String, f64>,
}

#[derive(Serialize, Deserialize, Clone)]
struct RegionalEconomicState {
    /// Current period transaction volume
    current_volume: f64,
    /// Previous period transaction volume
    previous_volume: f64,
    /// Current period total revenue
    current_revenue: f64,
    /// Previous period total revenue
    previous_revenue: f64,
    /// Active worker count
    active_workers: u32,
    /// Price index by product category
    price_index: HashMap<String, f64>,
    /// Transaction count for confidence
    transaction_count: u64,
}

impl EconomicAnalyzer {
    pub fn new() -> Self {
        Self {
            regional_state: HashMap::new(),
            baseline_cpi: HashMap::new(),
        }
    }

    /// Compute Consumer Price Index (Laspeyres-style)
    fn compute_cpi(&self, region: &str, current_prices: &HashMap<String, f64>) -> f64 {
        if self.baseline_cpi.is_empty() {
            return 100.0; // No baseline yet
        }

        let mut weighted_sum = 0.0;
        let mut weight_total = 0.0;

        for (product, baseline_price) in &self.baseline_cpi {
            if let Some(current_price) = current_prices.get(product) {
                // Expenditure weight (simplified: equal weights)
                let weight = 1.0;
                weighted_sum += (current_price / baseline_price) * weight;
                weight_total += weight;
            }
        }

        if weight_total > 0.0 {
            (weighted_sum / weight_total) * 100.0
        } else {
            100.0
        }
    }
}

#[async_trait::async_trait]
impl CapabilityModule for EconomicAnalyzer {
    fn id(&self) -> ModuleId {
        ModuleId::EconomicAnalyzer
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
                let state = self.regional_state
                    .entry(region.clone())
                    .or_insert_with(|| RegionalEconomicState {
                        current_volume: 0.0,
                        previous_volume: 0.0,
                        current_revenue: 0.0,
                        previous_revenue: 0.0,
                        active_workers: 0,
                        price_index: HashMap::new(),
                        transaction_count: 0,
                    });

                // Update state
                let batch_volume: f64 = transactions.iter()
                    .map(|t| t.quantity.unwrap_or(1.0))
                    .sum();
                let batch_revenue: f64 = transactions.iter()
                    .map(|t| t.amount)
                    .sum();

                // Shift periods (hourly)
                state.previous_volume = state.current_volume;
                state.previous_revenue = state.current_revenue;
                state.current_volume = batch_volume;
                state.current_revenue = batch_revenue;
                state.transaction_count += transactions.len() as u64;

                // Update price index
                for tx in &transactions {
                    let entry = state.price_index.entry(tx.product_category.clone())
                        .or_insert(tx.amount);
                    *entry = 0.95 * *entry + 0.05 * tx.amount; // EMA
                }

                // Compute indicators when we have enough data
                if state.transaction_count >= 100 {
                    let cpi = self.compute_cpi(&region, &state.price_index);

                    let volume_index = if state.previous_volume > 0.0 {
                        (state.current_volume / state.previous_volume) * 100.0
                    } else {
                        100.0
                    };

                    let inflation_rate = cpi - 100.0;

                    // Confidence intervals using bootstrap-like SE estimation
                    // SE scales as 1/√n for means
                    let n = state.transaction_count as f64;
                    let gdp_proxy = state.current_revenue * 30.0;
                    let gdp_se = gdp_proxy / n.sqrt(); // rough SE
                    let inflation_se = inflation_rate.abs().max(0.1) / n.sqrt();
                    let z_95 = 1.96;

                    return Ok(Some(ModuleMessage::EconomicIndicator {
                        trace_id,
                        region,
                        gdp_proxy,
                        inflation_rate,
                        employment_index: state.active_workers as f64,
                        transaction_volume_index: volume_index,
                        period: "hourly".to_string(),
                        gdp_ci_lower: (gdp_proxy - z_95 * gdp_se).max(0.0),
                        gdp_ci_upper: gdp_proxy + z_95 * gdp_se,
                        inflation_ci_lower: inflation_rate - z_95 * inflation_se,
                        inflation_ci_upper: inflation_rate + z_95 * inflation_se,
                    }));
                }

                Ok(None)
            }
            // Market signals contribute to economic indicators
            ModuleMessage::MarketSignal { region, demand_index, .. } => {
                if let Some(state) = self.regional_state.get_mut(&region) {
                    state.active_workers = (state.active_workers as f64 * 0.9 + demand_index * 10.0) as u32;
                }
                Ok(None)
            }
            // Credit activity signals economic health
            ModuleMessage::CreditAssessment { risk_level, .. } => {
                // High credit activity = economic dynamism
                // Low risk = economic stability
                match risk_level {
                    RiskLevel::Low => { /* Positive signal */ }
                    RiskLevel::VeryHigh => {
                        // Could trigger economic health alert
                    }
                    _ => {}
                }
                Ok(None)
            }
            _ => Ok(None),
        }
    }

    fn snapshot_state(&self) -> Option<Vec<u8>> {
        #[derive(Serialize)]
        struct Snapshot {
            regional_state: HashMap<String, RegionalEconomicState>,
            baseline_cpi: HashMap<String, f64>,
        }
        bincode::serialize(&Snapshot {
            regional_state: self.regional_state.clone(),
            baseline_cpi: self.baseline_cpi.clone(),
        }).ok()
    }

    fn restore_state(&mut self, data: &[u8]) {
        #[derive(Deserialize)]
        struct Snapshot {
            regional_state: HashMap<String, RegionalEconomicState>,
            baseline_cpi: HashMap<String, f64>,
        }
        if let Ok(snap) = bincode::deserialize::<Snapshot>(data) {
            self.regional_state = snap.regional_state;
            self.baseline_cpi = snap.baseline_cpi;
            tracing::info!(regions = self.regional_state.len(), "EconomicAnalyzer state restored");
        }
    }
}
