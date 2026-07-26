// Credit Scoring — Mining Worker Feature Extractor

use serde::{Deserialize, Serialize};
use super::{Transaction, TransactionCategory, WorkerContext, WorkerTypeFeatureExtractor};
use crate::credit::types::{WorkerType, TypeFeatures, MineType, MineralType, AssetValueBucket};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MiningFeatures {
    pub mine_type: MineType,
    pub mineral_type: MineralType,
    pub equipment_investment: AssetValueBucket,
    pub seasonal_income_profile: [f64; 12],
    pub active_period_stability: f64,
    pub buyer_diversity: u8,
    pub savings_rate: f64,
    pub income_trajectory: f64,
    pub avg_inactive_gap_days: u32,
    pub safety_investment_ratio: f64,
}

pub struct MiningFeatureExtractor;

impl MiningFeatureExtractor {
    pub fn new() -> Self { Self }

    fn detect_mineral(&self, transactions: &[Transaction]) -> MineralType {
        for tx in transactions {
            if let Some(ref product) = tx.product {
                let l = product.to_lowercase();
                if l.contains("gold") || l.contains("dhahabu") { return MineralType::Gold; }
                if l.contains("gem") || l.contains("ruby") || l.contains("sapphire") { return MineralType::Gemstones; }
                if l.contains("sand") || l.contains("mchanga") { return MineralType::Sand; }
                if l.contains("limestone") || l.contains("cement") { return MineralType::Limestone; }
            }
        }
        MineralType::Other
    }

    fn detect_mine_type(&self, transactions: &[Transaction]) -> MineType {
        let equipment_spend: f64 = transactions.iter()
            .filter(|tx| tx.category == TransactionCategory::Expense)
            .map(|tx| tx.amount).sum();
        if equipment_spend > 500_000.0 { MineType::Industrial }
        else if equipment_spend > 50_000.0 { MineType::SmallScale }
        else { MineType::Artisanal }
    }

    fn savings_rate(&self, transactions: &[Transaction]) -> f64 {
        let income: f64 = transactions.iter().filter(|tx| tx.category == TransactionCategory::Sale).map(|tx| tx.amount).sum();
        let savings: f64 = transactions.iter().filter(|tx| tx.category == TransactionCategory::Savings).map(|tx| tx.amount).sum();
        if income > 0.0 { (savings / income).min(1.0) } else { 0.0 }
    }

    fn inactive_gap(&self, transactions: &[Transaction]) -> u32 {
        let sales: Vec<i64> = transactions.iter()
            .filter(|tx| tx.category == TransactionCategory::Sale)
            .map(|tx| tx.timestamp / 86400).collect();
        if sales.len() < 2 { return 0; }
        let mut sorted = sales.clone(); sorted.sort(); sorted.dedup();
        let mut max_gap = 0u32;
        for w in sorted.windows(2) {
            let gap = (w[1] - w[0]) as u32;
            if gap > 7 { max_gap = max_gap.max(gap); }
        }
        max_gap
    }

    fn safety_investment(&self, transactions: &[Transaction]) -> f64 {
        let total_expense: f64 = transactions.iter()
            .filter(|tx| tx.category == TransactionCategory::Expense).map(|tx| tx.amount).sum();
        if total_expense < 1.0 { return 0.0; }
        let safety: f64 = transactions.iter()
            .filter(|tx| {
                tx.category == TransactionCategory::Expense
                    && tx.product.as_ref().map_or(false, |p| {
                        let l = p.to_lowercase();
                        l.contains("helmet") || l.contains("glove") || l.contains("boot")
                            || l.contains("mask") || l.contains("safety") || l.contains("kinga")
                    })
            }).map(|tx| tx.amount).sum();
        safety / total_expense
    }

    fn monthly_profile(&self, transactions: &[Transaction]) -> [f64; 12] {
        let mut totals = [0.0f64; 12];
        let mut counts = [0u32; 12];
        for tx in transactions {
            if tx.category == TransactionCategory::Sale {
                let month = ((tx.timestamp / 86400) % 365) / 30;
                let idx = (month as usize).min(11);
                totals[idx] += tx.amount;
                counts[idx] += 1;
            }
        }
        let mut profile = [0.0f64; 12];
        for i in 0..12 { if counts[i] > 0 { profile[i] = totals[i] / counts[i] as f64; } }
        profile
    }
}

impl WorkerTypeFeatureExtractor for MiningFeatureExtractor {
    fn extract(&self, transactions: &[Transaction], _ctx: &WorkerContext) -> TypeFeatures {
        let mineral = self.detect_mineral(transactions);
        let mine = self.detect_mine_type(transactions);
        let savings = self.savings_rate(transactions);
        let gap = self.inactive_gap(transactions);
        let safety = self.safety_investment(transactions);
        let profile = self.monthly_profile(transactions);
        let buyers: u8 = transactions.iter()
            .filter(|tx| tx.category == TransactionCategory::Sale)
            .filter_map(|tx| tx.counterparty_id.clone())
            .collect::<std::collections::HashSet<_>>().len() as u8;

        let features = MiningFeatures {
            mine_type: mine, mineral_type: mineral,
            equipment_investment: AssetValueBucket::Medium,
            seasonal_income_profile: profile, active_period_stability: 0.6,
            buyer_diversity: buyers, savings_rate: savings,
            income_trajectory: 0.0, avg_inactive_gap_days: gap,
            safety_investment_ratio: safety,
        };

        let fv = vec![
            match mine { MineType::Industrial => 1.0, MineType::SmallScale => 0.6, MineType::Artisanal => 0.3 },
            match mineral { MineralType::Gold => 1.0, MineralType::Gemstones => 0.8, MineralType::Sand => 0.4, MineralType::Limestone => 0.5, MineralType::Other => 0.3 },
            0.5, 0.6, (buyers as f64 / 5.0).min(1.0),
            savings, 0.5, (1.0 - (gap as f64 / 60.0).min(1.0)).max(0.0),
            safety, 0.5,
        ];

        TypeFeatures::from_features(WorkerType::MiningWorker, &features, fv, self.feature_names())
    }

    fn worker_type(&self) -> WorkerType { WorkerType::MiningWorker }
    fn min_transactions(&self) -> usize { 60 }
    fn feature_names(&self) -> Vec<&'static str> {
        vec!["mine_type", "mineral_type", "equipment_value", "seasonal_stability",
             "buyer_diversity", "savings_rate", "income_trajectory",
             "activity_consistency", "safety_investment", "stability"]
    }
}
