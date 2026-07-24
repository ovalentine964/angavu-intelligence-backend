use serde::{Deserialize, Serialize};
use anyhow::Result;

#[derive(Debug, Serialize, Deserialize)]
pub struct EconomicIndicator {
    pub region: String,
    pub gdp_estimate: f64,
    pub inflation_rate: f64,
    pub employment_index: f64,
    pub confidence: f64,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct TransactionAggregate {
    pub region: String,
    pub total_volume: u64,
    pub total_value: f64,
    pub avg_transaction: f64,
    pub worker_count: u64,
}

pub struct EconomicAnalyzer;

impl EconomicAnalyzer {
    pub fn new() -> Self { Self }

    pub fn estimate_gdp(&self, aggregates: &[TransactionAggregate]) -> Vec<EconomicIndicator> {
        aggregates.iter().map(|agg| {
            let gdp_proxy = agg.total_value * 4.0; // Annualize quarterly data
            let employment = agg.worker_count as f64 / 1_000_000.0; // Per million workers
            EconomicIndicator {
                region: agg.region.clone(),
                gdp_estimate: gdp_proxy,
                inflation_rate: self.estimate_inflation(agg),
                employment_index: employment,
                confidence: (agg.worker_count as f64 / 10_000.0).min(1.0),
            }
        }).collect()
    }

    fn estimate_inflation(&self, agg: &TransactionAggregate) -> f64 {
        // Compare avg transaction size with historical baseline
        let baseline = 500.0; // KES baseline
        ((agg.avg_transaction - baseline) / baseline * 100.0).max(-10.0).min(50.0)
    }
}
