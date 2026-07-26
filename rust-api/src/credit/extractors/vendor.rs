// Credit Scoring — Market Vendor Feature Extractor

use serde::{Deserialize, Serialize};
use super::{Transaction, TransactionCategory, WorkerContext, WorkerTypeFeatureExtractor};
use crate::credit::types::{WorkerType, TypeFeatures, MarketTier};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VendorFeatures {
    pub market_tier: MarketTier,
    pub product_diversity: u8,
    pub supplier_count: u8,
    pub years_in_business: f64,
    pub daily_txn_count_median: u32,
    pub avg_transaction_size: f64,
    pub inventory_turnover_days: u32,
    pub weekend_premium: f64,
    pub savings_regularity: f64,
    pub restock_frequency_days: u32,
}

pub struct VendorFeatureExtractor;

impl VendorFeatureExtractor {
    pub fn new() -> Self { Self }

    fn detect_market_tier(&self, transactions: &[Transaction]) -> MarketTier {
        let avg_size: f64 = {
            let sales: Vec<f64> = transactions.iter()
                .filter(|tx| tx.category == TransactionCategory::Sale)
                .map(|tx| tx.amount).collect();
            if sales.is_empty() { return MarketTier::Tier3; }
            sales.iter().sum::<f64>() / sales.len() as f64
        };
        if avg_size > 1000.0 { MarketTier::Tier1 }
        else if avg_size > 300.0 { MarketTier::Tier2 }
        else { MarketTier::Tier3 }
    }

    fn product_diversity(&self, transactions: &[Transaction]) -> u8 {
        let products: std::collections::HashSet<String> = transactions.iter()
            .filter(|tx| tx.category == TransactionCategory::Sale)
            .filter_map(|tx| tx.product.clone())
            .collect();
        products.len() as u8
    }

    fn supplier_count(&self, transactions: &[Transaction]) -> u8 {
        let suppliers: std::collections::HashSet<String> = transactions.iter()
            .filter(|tx| tx.category == TransactionCategory::Purchase)
            .filter_map(|tx| tx.counterparty_id.clone())
            .collect();
        suppliers.len() as u8
    }

    fn daily_txn_median(&self, transactions: &[Transaction]) -> u32 {
        let day_seconds = 86400i64;
        let mut daily_counts: std::collections::HashMap<i64, u32> = std::collections::HashMap::new();
        for tx in transactions {
            if tx.category == TransactionCategory::Sale {
                *daily_counts.entry(tx.timestamp / day_seconds).or_insert(0) += 1;
            }
        }
        if daily_counts.is_empty() { return 0; }
        let mut counts: Vec<u32> = daily_counts.values().copied().collect();
        counts.sort();
        counts[counts.len() / 2]
    }

    fn restock_frequency(&self, transactions: &[Transaction]) -> u32 {
        let purchases: Vec<i64> = transactions.iter()
            .filter(|tx| tx.category == TransactionCategory::Purchase)
            .map(|tx| tx.timestamp)
            .collect();
        if purchases.len() < 2 { return 7; }
        let mut sorted = purchases.clone();
        sorted.sort();
        let gaps: Vec<u32> = sorted.windows(2)
            .map(|w| ((w[1] - w[0]) / 86400) as u32)
            .filter(|&g| g > 0 && g < 30)
            .collect();
        if gaps.is_empty() { 7 } else { gaps.iter().sum::<u32>() / gaps.len() as u32 }
    }

    fn savings_regularity(&self, transactions: &[Transaction]) -> f64 {
        let savings: Vec<i64> = transactions.iter()
            .filter(|tx| tx.category == TransactionCategory::Savings)
            .map(|tx| tx.timestamp / 86400)
            .collect();
        if savings.len() < 3 { return 0.0; }
        let mut sorted = savings.clone();
        sorted.sort();
        sorted.dedup();
        let gaps: Vec<f64> = sorted.windows(2)
            .map(|w| (w[1] - w[0]) as f64)
            .collect();
        let mean = gaps.iter().sum::<f64>() / gaps.len() as f64;
        if mean < 1.0 { return 0.0; }
        let var = gaps.iter().map(|g| (g - mean).powi(2)).sum::<f64>() / gaps.len() as f64;
        (1.0 - (var.sqrt() / mean).min(1.0)).max(0.0)
    }
}

impl WorkerTypeFeatureExtractor for VendorFeatureExtractor {
    fn extract(&self, transactions: &[Transaction], ctx: &WorkerContext) -> TypeFeatures {
        let tier = self.detect_market_tier(transactions);
        let diversity = self.product_diversity(transactions);
        let suppliers = self.supplier_count(transactions);
        let years = ctx.first_transaction_days_ago as f64 / 365.0;
        let daily_txn = self.daily_txn_median(transactions);
        let avg_size = {
            let sales: Vec<f64> = transactions.iter()
                .filter(|tx| tx.category == TransactionCategory::Sale)
                .map(|tx| tx.amount).collect();
            if sales.is_empty() { 0.0 } else { sales.iter().sum::<f64>() / sales.len() as f64 }
        };
        let restock = self.restock_frequency(transactions);
        let savings_reg = self.savings_regularity(transactions);

        let features = VendorFeatures {
            market_tier: tier, product_diversity: diversity, supplier_count: suppliers,
            years_in_business: years, daily_txn_count_median: daily_txn,
            avg_transaction_size: avg_size, inventory_turnover_days: restock,
            weekend_premium: 1.0, savings_regularity: savings_reg, restock_frequency_days: restock,
        };

        let fv = vec![
            tier.normalize(), (diversity as f64 / 20.0).min(1.0),
            (suppliers as f64 / 10.0).min(1.0), (years / 10.0).min(1.0),
            (daily_txn as f64 / 30.0).min(1.0), (avg_size / 5000.0).min(1.0),
            (1.0 - (restock as f64 / 14.0).min(1.0)).max(0.0), 0.5,
            savings_reg, 0.5,
        ];

        TypeFeatures::from_features(WorkerType::MarketVendor, &features, fv, self.feature_names())
    }

    fn worker_type(&self) -> WorkerType { WorkerType::MarketVendor }
    fn min_transactions(&self) -> usize { 60 }
    fn feature_names(&self) -> Vec<&'static str> {
        vec!["market_tier", "product_diversity", "supplier_count", "years_in_business",
             "daily_txn_count", "avg_txn_size", "inventory_turnover", "weekend_premium",
             "savings_regularity", "restock_frequency"]
    }
}
