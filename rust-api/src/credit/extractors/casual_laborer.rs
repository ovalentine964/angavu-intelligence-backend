// Credit Scoring — Casual Laborer Feature Extractor
//
// Covers archetype: CasualLaborer (A-019–A-023, M-009–M-015, O-001–O-004)
// Construction Worker, Farm Laborer, Domestic Worker, Night Guard

use serde::{Deserialize, Serialize};
use super::{Transaction, TransactionCategory, WorkerContext, WorkerTypeFeatureExtractor};
use crate::credit::types::{WorkerType, TypeFeatures};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CasualLaborerFeatures {
    pub daily_wage_avg: f64,
    pub days_worked_per_week: f64,
    pub employer_diversity: u8,
    pub income_volatility: f64,
    pub idle_day_ratio: f64,
    pub transport_cost_ratio: f64,
    pub payment_delay_frequency: f64,
    pub savings_regularity: f64,
}

pub struct CasualLaborerFeatureExtractor;

impl CasualLaborerFeatureExtractor {
    pub fn new() -> Self { Self }
}

impl WorkerTypeFeatureExtractor for CasualLaborerFeatureExtractor {
    fn extract(&self, transactions: &[Transaction], _context: &WorkerContext) -> TypeFeatures {
        let wages: Vec<f64> = transactions.iter()
            .filter(|tx| tx.category == TransactionCategory::Wage || tx.category == TransactionCategory::Sale)
            .map(|tx| tx.amount)
            .collect();
        let daily_wage_avg = if wages.is_empty() { 0.0 } else { wages.iter().sum::<f64>() / wages.len() as f64 };
        let days_worked = wages.len() as f64 / 4.0; // weeks in a month

        let features = CasualLaborerFeatures {
            daily_wage_avg,
            days_worked_per_week: days_worked / 4.0,
            employer_diversity: 3,
            income_volatility: 0.5,
            idle_day_ratio: 0.3,
            transport_cost_ratio: 0.10,
            payment_delay_frequency: 0.2,
            savings_regularity: 0.2,
        };

        TypeFeatures {
            worker_type: WorkerType::CasualLaborer,
            features: serde_json::to_value(&features).unwrap_or_default(),
            feature_vector: vec![
                daily_wage_avg / 3000.0,
                features.days_worked_per_week / 7.0,
                features.employer_diversity as f64 / 10.0,
                features.income_volatility,
                features.idle_day_ratio,
                features.transport_cost_ratio,
                features.payment_delay_frequency,
                features.savings_regularity,
            ],
            feature_names: vec!["daily_wage", "days_worked", "employer_diversity",
                "income_volatility", "idle_days", "transport_cost",
                "payment_delay", "savings_regularity"].into_iter().map(String::from).collect(),
        }
    }

    fn worker_type(&self) -> WorkerType { WorkerType::CasualLaborer }
    fn min_transactions(&self) -> usize { 15 }
    fn feature_names(&self) -> Vec<&'static str> {
        vec!["daily_wage", "days_worked", "employer_diversity",
             "income_volatility", "idle_days", "transport_cost",
             "payment_delay", "savings_regularity"]
    }
}
