// =============================================================================
// Angavu Intelligence — Fiscal Impact Analyzer
// Measure policy impact on informal workers' income and welfare.
//
// Simulates the effect of fiscal policies (taxes, subsidies, minimum wage)
// on informal sector workers using microsimulation techniques.
// =============================================================================

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Types of fiscal policy interventions
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum FiscalPolicy {
    /// VAT rate change (percentage point change)
    VatChange { rate_change_pct: f64 },
    /// Minimum wage change (KES per day)
    MinimumWageChange { new_wage_daily: f64 },
    /// Digital services tax
    DigitalServicesTax { rate_pct: f64, threshold_daily: f64 },
    /// Market fee change (daily stall fee)
    MarketFeeChange { new_fee_daily: f64 },
    /// M-Pesa transaction tax
    MpesaTransactionTax { rate_pct: f64 },
    /// Fuel subsidy removal
    FuelSubsidyRemoval { price_increase_pct: f64 },
    /// Health insurance subsidy
    HealthInsuranceSubsidy { subsidy_pct: f64 },
}

/// Impact of a fiscal policy on a worker segment
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FiscalImpact {
    pub policy: String,
    pub worker_segment: String,
    pub affected_workers: u64,
    pub income_change_pct: f64,
    pub income_change_kes: f64,
    pub welfare_change_kes: f64,
    pub revenue_impact_kes: f64, // Government revenue change
    pub compliance_rate: f64,    // Expected compliance (0.0-1.0)
    pub distributional_effect: DistributionalEffect,
}

/// Whether policy is progressive, neutral, or regressive
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum DistributionalEffect {
    Progressive, // Benefits lower income more
    Neutral,     // Proportional impact
    Regressive,  // Burdens lower income more
}

/// Fiscal impact analyzer
pub struct FiscalImpactAnalyzer {
    /// Worker income distributions by segment
    segment_incomes: HashMap<String, Vec<f64>>,
    /// Current policy parameters
    current_policies: HashMap<String, f64>,
}

impl FiscalImpactAnalyzer {
    pub fn new() -> Self {
        Self {
            segment_incomes: HashMap::new(),
            current_policies: HashMap::new(),
        }
    }

    /// Set income distribution for a worker segment
    pub fn set_segment_incomes(&mut self, segment: &str, incomes: Vec<f64>) {
        self.segment_incomes.insert(segment.to_string(), incomes);
    }

    /// Simulate the impact of a fiscal policy change
    pub fn simulate_impact(&self, policy: &FiscalPolicy) -> Vec<FiscalImpact> {
        let mut impacts = Vec::new();

        for (segment, incomes) in &self.segment_incomes {
            let n = incomes.len() as u64;
            if n == 0 {
                continue;
            }

            let mean_income = incomes.iter().sum::<f64>() / n as f64;
            let median = {
                let mut sorted = incomes.clone();
                sorted.sort_by(|a, b| a.partial_cmp(b).unwrap());
                sorted[sorted.len() / 2]
            };
            let p10 = {
                let mut sorted = incomes.clone();
                sorted.sort_by(|a, b| a.partial_cmp(b).unwrap());
                sorted[(sorted.len() as f64 * 0.1) as usize]
            };
            let p90 = {
                let mut sorted = incomes.clone();
                sorted.sort_by(|a, b| a.partial_cmp(b).unwrap());
                sorted[(sorted.len() as f64 * 0.9) as usize]
            };

            let impact = match policy {
                FiscalPolicy::VatChange { rate_change_pct } => {
                    // VAT is regressive: lower income spends higher % on VAT-liable goods
                    let spend_ratio_lower = 0.9; // Bottom 40% spend 90% of income
                    let spend_ratio_upper = 0.6; // Top 20% spend 60% of income

                    let lower_impact = p10 * spend_ratio_lower * (rate_change_pct / 100.0);
                    let upper_impact = p90 * spend_ratio_upper * (rate_change_pct / 100.0);

                    let income_change = mean_income * 0.8 * (rate_change_pct / 100.0);

                    FiscalImpact {
                        policy: format!(
                            "VAT {}{}",
                            if *rate_change_pct > 0.0 { "+" } else { "" },
                            rate_change_pct
                        ),
                        worker_segment: segment.clone(),
                        affected_workers: n,
                        income_change_pct: -(rate_change_pct * 0.8),
                        income_change_kes: -income_change * 30.0, // Monthly
                        welfare_change_kes: -income_change * 30.0 * 0.8,
                        revenue_impact_kes: income_change * 30.0 * n as f64,
                        compliance_rate: 0.7, // Informal sector compliance
                        distributional_effect: if lower_impact / p10 > upper_impact / p90 {
                            DistributionalEffect::Regressive
                        } else {
                            DistributionalEffect::Progressive
                        },
                    }
                }

                FiscalPolicy::MinimumWageChange { new_wage_daily } => {
                    let current_min_wage = 350.0; // KES per day (Kenya 2026 estimate)
                    let wage_increase = new_wage_daily - current_min_wage;
                    let affected = incomes.iter().filter(|&&i| i < *new_wage_daily).count() as u64;

                    FiscalImpact {
                        policy: format!("Minimum Wage → KES {}/day", new_wage_daily),
                        worker_segment: segment.clone(),
                        affected_workers: affected,
                        income_change_pct: if mean_income > 0.0 {
                            (wage_increase / mean_income) * 100.0
                        } else {
                            0.0
                        },
                        income_change_kes: wage_increase * 30.0,
                        welfare_change_kes: wage_increase * 30.0 * 0.9,
                        revenue_impact_kes: wage_increase * 30.0 * affected as f64 * 0.15, // Tax revenue
                        compliance_rate: 0.4, // Low compliance in informal sector
                        distributional_effect: DistributionalEffect::Progressive,
                    }
                }

                FiscalPolicy::MpesaTransactionTax { rate_pct } => {
                    // M-Pesa tax hits everyone but proportionally more for small transactions
                    let monthly_tx_volume = mean_income * 30.0 * 2.0; // ~2x monthly income in transactions
                    let tax_cost = monthly_tx_volume * (rate_pct / 100.0);

                    FiscalImpact {
                        policy: format!("M-Pesa Tax {}%", rate_pct),
                        worker_segment: segment.clone(),
                        affected_workers: n,
                        income_change_pct: -(rate_pct * 2.0), // Amplified by transaction frequency
                        income_change_kes: -tax_cost,
                        welfare_change_kes: -tax_cost * 0.85,
                        revenue_impact_kes: tax_cost * n as f64 * 0.9,
                        compliance_rate: 0.95, // Automatic deduction
                        distributional_effect: DistributionalEffect::Regressive,
                    }
                }

                FiscalPolicy::MarketFeeChange { new_fee_daily } => {
                    let current_fee = 50.0; // KES per day average
                    let fee_change = new_fee_daily - current_fee;

                    FiscalImpact {
                        policy: format!("Market Fee → KES {}/day", new_fee_daily),
                        worker_segment: segment.clone(),
                        affected_workers: n,
                        income_change_pct: if mean_income > 0.0 {
                            -(fee_change / mean_income) * 100.0
                        } else {
                            0.0
                        },
                        income_change_kes: -fee_change * 30.0,
                        welfare_change_kes: -fee_change * 30.0 * 0.9,
                        revenue_impact_kes: fee_change * 30.0 * n as f64,
                        compliance_rate: 0.85,
                        distributional_effect: if fee_change > 0.0 {
                            DistributionalEffect::Regressive
                        } else {
                            DistributionalEffect::Progressive
                        },
                    }
                }

                FiscalPolicy::FuelSubsidyRemoval { price_increase_pct } => {
                    // Fuel price increase affects transport costs → higher prices for all goods
                    let transport_cost_share = 0.15; // 15% of informal worker costs
                    let cost_increase =
                        mean_income * transport_cost_share * (price_increase_pct / 100.0);

                    FiscalImpact {
                        policy: format!("Fuel Subsidy Removal (+{}%)", price_increase_pct),
                        worker_segment: segment.clone(),
                        affected_workers: n,
                        income_change_pct: -(price_increase_pct * transport_cost_share),
                        income_change_kes: -cost_increase * 30.0,
                        welfare_change_kes: -cost_increase * 30.0 * 1.2, // Multiplier effect
                        revenue_impact_kes: cost_increase * 30.0 * n as f64 * 0.5,
                        compliance_rate: 1.0, // Automatic
                        distributional_effect: DistributionalEffect::Regressive,
                    }
                }

                FiscalPolicy::HealthInsuranceSubsidy { subsidy_pct } => {
                    let premium_monthly = 500.0; // NHIF approximate
                    let subsidy_amount = premium_monthly * (subsidy_pct / 100.0);

                    FiscalImpact {
                        policy: format!("Health Insurance Subsidy {}%", subsidy_pct),
                        worker_segment: segment.clone(),
                        affected_workers: n,
                        income_change_pct: (subsidy_amount / mean_income) * 100.0 / 30.0,
                        income_change_kes: subsidy_amount,
                        welfare_change_kes: subsidy_amount * 1.5, // Health has multiplier effect
                        revenue_impact_kes: -subsidy_amount * n as f64,
                        compliance_rate: 0.6,
                        distributional_effect: DistributionalEffect::Progressive,
                    }
                }

                FiscalPolicy::DigitalServicesTax {
                    rate_pct,
                    threshold_daily,
                } => {
                    let affected =
                        incomes.iter().filter(|&&i| i >= *threshold_daily).count() as u64;
                    let mean_affected = if affected > 0 {
                        incomes
                            .iter()
                            .filter(|&&i| i >= *threshold_daily)
                            .sum::<f64>()
                            / affected as f64
                    } else {
                        0.0
                    };
                    let tax_per_worker = mean_affected * 30.0 * (rate_pct / 100.0);

                    FiscalImpact {
                        policy: format!("Digital Services Tax {}%", rate_pct),
                        worker_segment: segment.clone(),
                        affected_workers: affected,
                        income_change_pct: -(rate_pct),
                        income_change_kes: -tax_per_worker,
                        welfare_change_kes: -tax_per_worker * 0.8,
                        revenue_impact_kes: tax_per_worker * affected as f64,
                        compliance_rate: 0.5,
                        distributional_effect: DistributionalEffect::Progressive, // Only above threshold
                    }
                }
            };

            impacts.push(impact);
        }

        impacts
    }

    /// Compute total welfare impact across all segments
    pub fn total_welfare_impact(&self, impacts: &[FiscalImpact]) -> f64 {
        impacts
            .iter()
            .map(|i| i.welfare_change_kes * i.affected_workers as f64)
            .sum()
    }

    /// Compute total revenue impact
    pub fn total_revenue_impact(&self, impacts: &[FiscalImpact]) -> f64 {
        impacts.iter().map(|i| i.revenue_impact_kes).sum()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn setup_analyzer() -> FiscalImpactAnalyzer {
        let mut analyzer = FiscalImpactAnalyzer::new();
        // Mama mboga: low income, high variance
        analyzer.set_segment_incomes(
            "mama_mboga",
            vec![
                200.0, 300.0, 400.0, 500.0, 600.0, 800.0, 1000.0, 1500.0, 2000.0, 3000.0,
            ],
        );
        // Boda boda: medium income
        analyzer.set_segment_incomes(
            "boda_boda",
            vec![
                500.0, 700.0, 800.0, 1000.0, 1200.0, 1500.0, 1800.0, 2000.0, 2500.0, 3000.0,
            ],
        );
        // Duka owner: higher income
        analyzer.set_segment_incomes(
            "duka_owner",
            vec![
                1000.0, 1500.0, 2000.0, 2500.0, 3000.0, 4000.0, 5000.0, 6000.0, 8000.0, 10000.0,
            ],
        );
        analyzer
    }

    #[test]
    fn test_vat_is_regressive() {
        let analyzer = setup_analyzer();
        let impacts = analyzer.simulate_impact(&FiscalPolicy::VatChange {
            rate_change_pct: 2.0,
        });
        // Lower income segments should bear proportionally more
        let mama = impacts
            .iter()
            .find(|i| i.worker_segment == "mama_mboga")
            .unwrap();
        let duka = impacts
            .iter()
            .find(|i| i.worker_segment == "duka_owner")
            .unwrap();
        assert!(
            mama.income_change_pct.abs() > duka.income_change_pct.abs(),
            "VAT should be regressive: mama={}% vs duka={}%",
            mama.income_change_pct,
            duka.income_change_pct
        );
    }

    #[test]
    fn test_minimum_wage_is_progressive() {
        let analyzer = setup_analyzer();
        let impacts = analyzer.simulate_impact(&FiscalPolicy::MinimumWageChange {
            new_wage_daily: 500.0,
        });
        let mama = impacts
            .iter()
            .find(|i| i.worker_segment == "mama_mboga")
            .unwrap();
        let duka = impacts
            .iter()
            .find(|i| i.worker_segment == "duka_owner")
            .unwrap();
        assert!(matches!(
            mama.distributional_effect,
            DistributionalEffect::Progressive
        ));
        assert!(mama.affected_workers > duka.affected_workers);
    }

    #[test]
    fn test_total_impacts() {
        let analyzer = setup_analyzer();
        let impacts =
            analyzer.simulate_impact(&FiscalPolicy::MpesaTransactionTax { rate_pct: 1.0 });
        let total_welfare = analyzer.total_welfare_impact(&impacts);
        assert!(
            total_welfare < 0.0,
            "M-Pesa tax should reduce total welfare"
        );
    }
}
