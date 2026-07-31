// Credit Scoring — Agent/Broker Feature Extractor
//
// Covers archetype: AgentBroker (D-001–D-004, T-023)
// M-Pesa Agent, Forex Bureau, Money Lender, Produce Broker

use serde::{Deserialize, Serialize};
use super::{Transaction, TransactionCategory, WorkerContext, WorkerTypeFeatureExtractor};
use crate::credit::types::{WorkerType, TypeFeatures};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentBrokerFeatures {
    pub daily_transaction_count: u32,
    pub float_turnover_ratio: f64,
    pub commission_rate: f64,
    pub peak_hour_concentration: f64,
    pub fraud_risk_score: f64,
    pub transaction_volume: f64,
    pub repeat_customer_ratio: f64,
    pub operating_hours: f64,
}

pub struct AgentBrokerFeatureExtractor;

impl AgentBrokerFeatureExtractor {
    pub fn new() -> Self { Self }
}

impl WorkerTypeFeatureExtractor for AgentBrokerFeatureExtractor {
    fn extract(&self, transactions: &[Transaction], _context: &WorkerContext) -> TypeFeatures {
        let daily_txn = transactions.len() as f64 / 30.0;
        let volume: f64 = transactions.iter().map(|tx| tx.amount).sum();

        let features = AgentBrokerFeatures {
            daily_transaction_count: daily_txn as u32,
            float_turnover_ratio: 3.0,
            commission_rate: 0.01,
            peak_hour_concentration: 0.6,
            fraud_risk_score: 0.1,
            transaction_volume: volume,
            repeat_customer_ratio: 0.65,
            operating_hours: 10.0,
        };

        TypeFeatures {
            worker_type: WorkerType::AgentBroker,
            features: serde_json::to_value(&features).unwrap_or_default(),
            feature_vector: vec![
                daily_txn / 100.0,
                features.float_turnover_ratio / 10.0,
                features.commission_rate * 100.0,
                features.peak_hour_concentration,
                features.fraud_risk_score,
                volume / 1000000.0,
                features.repeat_customer_ratio,
                features.operating_hours / 24.0,
            ],
            feature_names: vec!["daily_txn", "float_turnover", "commission_rate",
                "peak_concentration", "fraud_risk", "volume",
                "repeat_customers", "operating_hours"].into_iter().map(String::from).collect(),
        }
    }

    fn worker_type(&self) -> WorkerType { WorkerType::AgentBroker }
    fn min_transactions(&self) -> usize { 30 }
    fn feature_names(&self) -> Vec<&'static str> {
        vec!["daily_txn", "float_turnover", "commission_rate",
             "peak_concentration", "fraud_risk", "volume",
             "repeat_customers", "operating_hours"]
    }
}
