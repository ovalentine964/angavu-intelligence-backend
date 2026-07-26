// Credit Scoring — M-Pesa Agent Feature Extractor

use serde::{Deserialize, Serialize};
use super::{Transaction, TransactionCategory, WorkerContext, WorkerTypeFeatureExtractor};
use crate::credit::types::{WorkerType, TypeFeatures, AgentTier};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MpesaAgentFeatures {
    pub float_turnover_ratio: f64,
    pub daily_txn_count_median: u32,
    pub daily_commission_median: f64,
    pub agent_tier: AgentTier,
    pub foot_traffic_score: f64,
    pub float_efficiency: f64,
    pub deposit_withdrawal_ratio: f64,
    pub operating_hours_utilization: f64,
    pub revenue_trajectory: f64,
    pub large_txn_frequency: f64,
}

pub struct MpesaAgentFeatureExtractor;

impl MpesaAgentFeatureExtractor {
    pub fn new() -> Self { Self }

    fn daily_txn_median(&self, transactions: &[Transaction]) -> u32 {
        let day_seconds = 86400i64;
        let mut daily: std::collections::HashMap<i64, u32> = std::collections::HashMap::new();
        for tx in transactions {
            if matches!(tx.category, TransactionCategory::Sale | TransactionCategory::Commission) {
                *daily.entry(tx.timestamp / day_seconds).or_insert(0) += 1;
            }
        }
        if daily.is_empty() { return 0; }
        let mut counts: Vec<u32> = daily.values().copied().collect();
        counts.sort();
        counts[counts.len() / 2]
    }

    fn detect_tier(&self, daily_txn: u32) -> AgentTier {
        if daily_txn >= 100 { AgentTier::SuperAgent }
        else if daily_txn >= 30 { AgentTier::Standard }
        else { AgentTier::Mini }
    }

    fn foot_traffic_score(&self, transactions: &[Transaction]) -> f64 {
        let day_seconds = 86400i64;
        let mut hourly: [u32; 24] = [0; 24];
        for tx in transactions {
            let hour = ((tx.timestamp % day_seconds) / 3600) as usize;
            if hour < 24 { hourly[hour] += 1; }
        }
        let total: u32 = hourly.iter().sum();
        if total == 0 { return 0.0; }
        let business_hours: u32 = hourly[8..18].iter().sum();
        business_hours as f64 / total as f64
    }

    fn large_txn_frequency(&self, transactions: &[Transaction]) -> f64 {
        let total = transactions.len() as f64;
        if total < 1.0 { return 0.0; }
        let large = transactions.iter().filter(|tx| tx.amount > 50_000.0).count();
        large as f64 / total
    }
}

impl WorkerTypeFeatureExtractor for MpesaAgentFeatureExtractor {
    fn extract(&self, transactions: &[Transaction], _ctx: &WorkerContext) -> TypeFeatures {
        let daily_txn = self.daily_txn_median(transactions);
        let tier = self.detect_tier(daily_txn);
        let foot_traffic = self.foot_traffic_score(transactions);
        let large_freq = self.large_txn_frequency(transactions);
        let commission_median = {
            let comms: Vec<f64> = transactions.iter()
                .filter(|tx| tx.category == TransactionCategory::Commission)
                .map(|tx| tx.amount).collect();
            if comms.is_empty() { 0.0 } else {
                let mut s = comms.clone(); s.sort_by(|a,b| a.partial_cmp(b).unwrap());
                s[s.len()/2]
            }
        };
        let deposits = transactions.iter().filter(|tx| tx.amount > 0.0 && tx.category == TransactionCategory::Sale).count();
        let withdrawals = transactions.iter().filter(|tx| tx.amount < 0.0 || tx.category == TransactionCategory::Expense).count();
        let dw_ratio = if withdrawals > 0 { deposits as f64 / withdrawals as f64 } else { 1.0 };

        let features = MpesaAgentFeatures {
            float_turnover_ratio: 3.0, daily_txn_count_median: daily_txn,
            daily_commission_median: commission_median, agent_tier: tier,
            foot_traffic_score: foot_traffic, float_efficiency: 0.7,
            deposit_withdrawal_ratio: dw_ratio.min(3.0), operating_hours_utilization: foot_traffic,
            revenue_trajectory: 0.0, large_txn_frequency: large_freq,
        };

        let fv = vec![
            0.5, (daily_txn as f64 / 100.0).min(1.0), (commission_median / 5000.0).min(1.0),
            tier.normalize(), foot_traffic, 0.7, (dw_ratio / 3.0).min(1.0),
            foot_traffic, 0.5, 1.0 - large_freq,
        ];

        TypeFeatures::from_features(WorkerType::MpesaAgent, &features, fv, self.feature_names())
    }

    fn worker_type(&self) -> WorkerType { WorkerType::MpesaAgent }
    fn min_transactions(&self) -> usize { 30 }
    fn feature_names(&self) -> Vec<&'static str> {
        vec!["float_turnover", "daily_txn_count", "commission", "agent_tier",
             "foot_traffic", "float_efficiency", "deposit_withdrawal_ratio",
             "operating_utilization", "revenue_trajectory", "large_txn_risk"]
    }
}
