// Credit Scoring — Community/Care Worker Feature Extractor
//
// Covers archetype: CommunityCareWorker (O-005–O-030)
// MC/DJ, Photographer, Waste Picker, Security Guard, Tutor, etc.

use serde::{Deserialize, Serialize};
use super::{Transaction, TransactionCategory, WorkerContext, WorkerTypeFeatureExtractor};
use crate::credit::types::{WorkerType, TypeFeatures};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CommunityCareFeatures {
    pub avg_engagement_fee: f64,
    pub engagements_per_month: f64,
    pub income_volatility: f64,
    pub equipment_investment: f64,
    pub repeat_client_ratio: f64,
    pub seasonal_peak_factor: f64,
    pub advance_payment_ratio: f64,
    pub reputation_score: f64,
}

pub struct CommunityCareFeatureExtractor;

impl CommunityCareFeatureExtractor {
    pub fn new() -> Self { Self }
}

impl WorkerTypeFeatureExtractor for CommunityCareFeatureExtractor {
    fn extract(&self, transactions: &[Transaction], _context: &WorkerContext) -> TypeFeatures {
        let sales: Vec<f64> = transactions.iter()
            .filter(|tx| tx.category == TransactionCategory::Sale)
            .map(|tx| tx.amount)
            .collect();
        let avg_fee = if sales.is_empty() { 0.0 } else { sales.iter().sum::<f64>() / sales.len() as f64 };
        let engagements_per_month = sales.len() as f64 / 3.0;

        let features = CommunityCareFeatures {
            avg_engagement_fee: avg_fee,
            engagements_per_month,
            income_volatility: 0.7,
            equipment_investment: 0.0,
            repeat_client_ratio: 0.4,
            seasonal_peak_factor: 1.5,
            advance_payment_ratio: 0.3,
            reputation_score: 0.6,
        };

        TypeFeatures {
            worker_type: WorkerType::CommunityCareWorker,
            features: serde_json::to_value(&features).unwrap_or_default(),
            feature_vector: vec![
                avg_fee / 20000.0,
                engagements_per_month / 20.0,
                features.income_volatility,
                features.equipment_investment,
                features.repeat_client_ratio,
                features.seasonal_peak_factor / 3.0,
                features.advance_payment_ratio,
                features.reputation_score,
            ],
            feature_names: vec!["avg_fee", "engagements_per_month", "income_volatility",
                "equipment_investment", "repeat_clients", "seasonal_peak",
                "advance_payment", "reputation"].into_iter().map(String::from).collect(),
        }
    }

    fn worker_type(&self) -> WorkerType { WorkerType::CommunityCareWorker }
    fn min_transactions(&self) -> usize { 20 }
    fn feature_names(&self) -> Vec<&'static str> {
        vec!["avg_fee", "engagements_per_month", "income_volatility",
             "equipment_investment", "repeat_clients", "seasonal_peak",
             "advance_payment", "reputation"]
    }
}
