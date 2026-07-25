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

// ============================================================
// Academic Formula Integrations (ECO 101, MAT 121)
// ============================================================

/// Price Elasticity of Demand (PED).
///
/// PED = (% change in quantity) / (% change in price)
///     = (ΔQ / Q) / (ΔP / P)
///
/// Both inputs are already expressed as percentages (e.g. 10.0 for 10%).
/// Returns the elasticity coefficient (typically negative). |PED| > 1 means
/// demand is elastic; |PED| < 1 means inelastic.
pub fn calculate_price_elasticity(
    price_change_pct: f64,
    quantity_change_pct: f64,
) -> f64 {
    if price_change_pct.abs() < 1e-10 {
        return 0.0; // Undefined — zero price change
    }
    quantity_change_pct / price_change_pct
}

/// Marginal Cost (MC).
///
/// MC = ΔTC / ΔQ
///
/// The additional cost of producing one more unit.
pub fn calculate_marginal_cost(
    total_cost_delta: f64,
    quantity_delta: f64,
) -> f64 {
    if quantity_delta.abs() < 1e-10 {
        return 0.0;
    }
    total_cost_delta / quantity_delta
}

/// Break-even analysis.
///
/// Break-even quantity = Fixed Costs / (Price − Variable Cost per Unit)
///
/// Returns the number of units that must be sold to cover all fixed costs.
pub fn break_even_analysis(
    fixed_costs: f64,
    price: f64,
    variable_cost_per_unit: f64,
) -> f64 {
    let contribution_margin = price - variable_cost_per_unit;
    if contribution_margin <= 0.0 {
        return f64::INFINITY; // Cannot break even — margin is zero or negative
    }
    fixed_costs / contribution_margin
}
