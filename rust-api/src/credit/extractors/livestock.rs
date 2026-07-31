// Credit Scoring — Livestock Keeper Feature Extractor
//
// Covers archetype: LivestockKeeper (A-007–A-014)
// Dairy Farmer, Poultry Farmer, Goat/Sheep Keeper, etc.

use serde::{Deserialize, Serialize};
use super::{Transaction, TransactionCategory, WorkerContext, WorkerTypeFeatureExtractor};
use crate::credit::types::{WorkerType, TypeFeatures};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LivestockFeatures {
    pub daily_production_income: f64,
    pub feed_cost_ratio: f64,
    pub vet_cost_ratio: f64,
    pub production_regularity: f64,
    pub animal_sales_frequency: f64,
    pub revenue_volatility: f64,
    pub mortality_proxy: f64,
    pub years_in_livestock: f64,
}

pub struct LivestockFeatureExtractor;

impl LivestockFeatureExtractor {
    pub fn new() -> Self { Self }
}

impl WorkerTypeFeatureExtractor for LivestockFeatureExtractor {
    fn extract(&self, transactions: &[Transaction], _context: &WorkerContext) -> TypeFeatures {
        let sales: Vec<f64> = transactions.iter()
            .filter(|tx| tx.category == TransactionCategory::Sale)
            .map(|tx| tx.amount)
            .collect();
        let daily_production_income = if sales.is_empty() { 0.0 } else { sales.iter().sum::<f64>() / 30.0 };

        let features = LivestockFeatures {
            daily_production_income,
            feed_cost_ratio: 0.40,
            vet_cost_ratio: 0.08,
            production_regularity: 0.7,
            animal_sales_frequency: 0.05,
            revenue_volatility: 0.3,
            mortality_proxy: 0.02,
            years_in_livestock: 2.0,
        };

        TypeFeatures {
            worker_type: WorkerType::LivestockKeeper,
            features: serde_json::to_value(&features).unwrap_or_default(),
            feature_vector: vec![
                daily_production_income / 5000.0,
                features.feed_cost_ratio,
                features.vet_cost_ratio,
                features.production_regularity,
                features.animal_sales_frequency,
                features.revenue_volatility,
                features.mortality_proxy,
                features.years_in_livestock / 20.0,
            ],
            feature_names: vec!["daily_production", "feed_cost", "vet_cost",
                "production_regularity", "animal_sales", "revenue_volatility",
                "mortality_proxy", "years_in_livestock"].into_iter().map(String::from).collect(),
        }
    }

    fn worker_type(&self) -> WorkerType { WorkerType::LivestockKeeper }
    fn min_transactions(&self) -> usize { 60 }
    fn feature_names(&self) -> Vec<&'static str> {
        vec!["daily_production", "feed_cost", "vet_cost",
             "production_regularity", "animal_sales", "revenue_volatility",
             "mortality_proxy", "years_in_livestock"]
    }
}
