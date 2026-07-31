// Credit Scoring — Digital Worker Feature Extractor
//
// Covers archetype: DigitalWorker (D-005–D-013)
// Cyber Cafe, Graphic Designer, Social Media Manager, Content Creator, etc.

use serde::{Deserialize, Serialize};
use super::{Transaction, TransactionCategory, WorkerContext, WorkerTypeFeatureExtractor};
use crate::credit::types::{WorkerType, TypeFeatures};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DigitalWorkerFeatures {
    pub avg_project_value: f64,
    pub projects_per_month: f64,
    pub platform_income_ratio: f64,
    pub client_diversity: u8,
    pub income_volatility: f64,
    pub internet_cost_ratio: f64,
    pub international_payment_ratio: f64,
    pub skill_premium: f64,
}

pub struct DigitalWorkerFeatureExtractor;

impl DigitalWorkerFeatureExtractor {
    pub fn new() -> Self { Self }
}

impl WorkerTypeFeatureExtractor for DigitalWorkerFeatureExtractor {
    fn extract(&self, transactions: &[Transaction], _context: &WorkerContext) -> TypeFeatures {
        let sales: Vec<f64> = transactions.iter()
            .filter(|tx| tx.category == TransactionCategory::Sale)
            .map(|tx| tx.amount)
            .collect();
        let avg_project_value = if sales.is_empty() { 0.0 } else { sales.iter().sum::<f64>() / sales.len() as f64 };
        let projects_per_month = sales.len() as f64 / 3.0;

        let features = DigitalWorkerFeatures {
            avg_project_value,
            projects_per_month,
            platform_income_ratio: 0.4,
            client_diversity: 5,
            income_volatility: 0.6,
            internet_cost_ratio: 0.10,
            international_payment_ratio: 0.3,
            skill_premium: 0.5,
        };

        TypeFeatures {
            worker_type: WorkerType::DigitalWorker,
            features: serde_json::to_value(&features).unwrap_or_default(),
            feature_vector: vec![
                avg_project_value / 50000.0,
                projects_per_month / 20.0,
                features.platform_income_ratio,
                features.client_diversity as f64 / 20.0,
                features.income_volatility,
                features.internet_cost_ratio,
                features.international_payment_ratio,
                features.skill_premium,
            ],
            feature_names: vec!["avg_project_value", "projects_per_month", "platform_income",
                "client_diversity", "income_volatility", "internet_cost",
                "international_payment", "skill_premium"].into_iter().map(String::from).collect(),
        }
    }

    fn worker_type(&self) -> WorkerType { WorkerType::DigitalWorker }
    fn min_transactions(&self) -> usize { 30 }
    fn feature_names(&self) -> Vec<&'static str> {
        vec!["avg_project_value", "projects_per_month", "platform_income",
             "client_diversity", "income_volatility", "internet_cost",
             "international_payment", "skill_premium"]
    }
}
