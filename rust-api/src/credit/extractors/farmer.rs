// Credit Scoring — Farmer Feature Extractor
// Extracts credit signals unique to agricultural workers

use super::{
    PaymentMethod, Transaction, TransactionCategory, WorkerContext, WorkerTypeFeatureExtractor,
};
use crate::credit::types::{CropType, LandSizeBucket, TypeFeatures, WorkerType};
use serde::{Deserialize, Serialize};

/// Farmer-specific credit features
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FarmerFeatures {
    pub primary_crop: CropType,
    pub land_size_bucket: LandSizeBucket,
    pub harvest_cycle_days: Option<u32>,
    pub intra_season_stability: f64,
    pub seasonal_ratio: f64,
    pub input_investment_ratio: f64,
    pub has_cooperative_membership: bool,
    pub post_harvest_savings_ratio: f64,
    pub buyer_diversity: u8,
    pub avg_storage_duration_days: u32,
}

pub struct FarmerFeatureExtractor;

impl FarmerFeatureExtractor {
    pub fn new() -> Self {
        Self
    }

    /// Detect crop type from product names in transactions
    fn detect_crop(&self, transactions: &[Transaction]) -> CropType {
        let mut crop_counts: std::collections::HashMap<String, u32> =
            std::collections::HashMap::new();
        let crop_keywords = [
            ("maize", "maize"),
            ("mahindi", "maize"),
            ("corn", "maize"),
            ("beans", "beans"),
            ("maharagwe", "beans"),
            ("tomato", "vegetables"),
            ("nyanya", "vegetables"),
            ("spinach", "vegetables"),
            ("sukuma", "vegetables"),
            ("mango", "fruit"),
            ("embe", "fruit"),
            ("banana", "fruit"),
            ("ndizi", "fruit"),
            ("tea", "tea"),
            ("chai", "tea"),
            ("coffee", "coffee"),
            ("kahawa", "coffee"),
            ("rice", "rice"),
            ("mpunga", "rice"),
            ("wheat", "wheat"),
            ("ngano", "wheat"),
            ("sugarcane", "sugarcane"),
            ("miwa", "sugarcane"),
        ];

        for tx in transactions {
            if let Some(ref product) = tx.product {
                let lower = product.to_lowercase();
                for (keyword, crop) in &crop_keywords {
                    if lower.contains(keyword) {
                        *crop_counts.entry(crop.to_string()).or_insert(0) += 1;
                    }
                }
            }
        }

        match crop_counts.iter().max_by_key(|(_, &count)| count) {
            Some((crop, _)) => match crop.as_str() {
                "maize" => CropType::Maize,
                "beans" => CropType::Beans,
                "vegetables" => CropType::Vegetables,
                "fruit" => CropType::Fruit,
                "tea" => CropType::Tea,
                "coffee" => CropType::Coffee,
                "rice" => CropType::Rice,
                "wheat" => CropType::Wheat,
                "sugarcane" => CropType::Sugarcane,
                _ => CropType::Other,
            },
            None => CropType::Mixed,
        }
    }

    /// Estimate land size from input purchase quantities
    fn estimate_land_size(&self, transactions: &[Transaction]) -> LandSizeBucket {
        let input_spend: f64 = transactions
            .iter()
            .filter(|tx| {
                tx.category == TransactionCategory::Purchase
                    && tx.product.as_ref().map_or(false, |p| {
                        let lower = p.to_lowercase();
                        lower.contains("seed")
                            || lower.contains("fertilizer")
                            || lower.contains("mbegu")
                            || lower.contains("mbolea")
                    })
            })
            .map(|tx| tx.amount)
            .sum();

        // Rough heuristic: seed+fertilizer spend → land size
        if input_spend > 50_000.0 {
            LandSizeBucket::Large
        } else if input_spend > 10_000.0 {
            LandSizeBucket::Medium
        } else {
            LandSizeBucket::Small
        }
    }

    /// Detect harvest cycle from income periodicity
    fn detect_harvest_cycle(&self, transactions: &[Transaction]) -> Option<u32> {
        let sales: Vec<&Transaction> = transactions
            .iter()
            .filter(|tx| tx.category == TransactionCategory::Sale)
            .collect();

        if sales.len() < 10 {
            return None;
        }

        // Build daily income series
        let mut daily_income: std::collections::BTreeMap<i64, f64> =
            std::collections::BTreeMap::new();
        let day_seconds = 86400;
        for tx in &sales {
            let day = tx.timestamp / day_seconds;
            *daily_income.entry(day).or_insert(0.0) += tx.amount;
        }

        // Simple peak detection: find gaps between income bursts
        let incomes: Vec<f64> = daily_income.values().copied().collect();
        let mean: f64 = incomes.iter().sum::<f64>() / incomes.len() as f64;
        let threshold = mean * 2.0; // "burst" = 2x average

        let mut burst_days: Vec<i64> = Vec::new();
        for (&day, &income) in &daily_income {
            if income > threshold {
                burst_days.push(day);
            }
        }

        if burst_days.len() < 2 {
            return None;
        }

        // Average gap between bursts
        let gaps: Vec<u32> = burst_days
            .windows(2)
            .map(|w| (w[1] - w[0]) as u32)
            .collect();

        if gaps.is_empty() {
            return None;
        }

        let avg_gap = gaps.iter().sum::<u32>() / gaps.len() as u32;
        if avg_gap > 30 && avg_gap < 400 {
            Some(avg_gap)
        } else {
            None
        }
    }

    /// Check for cooperative membership (recurring payments to same entity)
    fn detect_cooperative(&self, transactions: &[Transaction]) -> bool {
        let mut entity_counts: std::collections::HashMap<String, u32> =
            std::collections::HashMap::new();
        for tx in transactions {
            if tx.category == TransactionCategory::Expense
                || tx.category == TransactionCategory::Transfer
            {
                if let Some(ref name) = tx.counterparty_name {
                    let lower = name.to_lowercase();
                    if lower.contains("cooperative")
                        || lower.contains("sacco")
                        || lower.contains("chama")
                        || lower.contains("society")
                    {
                        *entity_counts.entry(name.clone()).or_insert(0) += 1;
                    }
                }
            }
        }
        entity_counts.values().any(|&count| count >= 3)
    }

    /// Compute input investment ratio
    fn input_investment_ratio(&self, transactions: &[Transaction]) -> f64 {
        let total_expenses: f64 = transactions
            .iter()
            .filter(|tx| {
                matches!(
                    tx.category,
                    TransactionCategory::Purchase | TransactionCategory::Expense
                )
            })
            .map(|tx| tx.amount)
            .sum();

        if total_expenses < 1.0 {
            return 0.0;
        }

        let input_expenses: f64 = transactions
            .iter()
            .filter(|tx| {
                tx.category == TransactionCategory::Purchase
                    && tx.product.as_ref().map_or(false, |p| {
                        let lower = p.to_lowercase();
                        lower.contains("seed")
                            || lower.contains("fertilizer")
                            || lower.contains("pesticide")
                            || lower.contains("mbegu")
                            || lower.contains("mbolea")
                    })
            })
            .map(|tx| tx.amount)
            .sum();

        input_expenses / total_expenses
    }

    /// Post-harvest savings: savings deposits within 30 days of income spikes
    fn post_harvest_savings_ratio(&self, transactions: &[Transaction]) -> f64 {
        let sales: Vec<&Transaction> = transactions
            .iter()
            .filter(|tx| tx.category == TransactionCategory::Sale)
            .collect();

        let savings: Vec<&Transaction> = transactions
            .iter()
            .filter(|tx| tx.category == TransactionCategory::Savings)
            .collect();

        if sales.is_empty() || savings.is_empty() {
            return 0.0;
        }

        // Find income spikes (>2x average)
        let total_income: f64 = sales.iter().map(|tx| tx.amount).sum();
        let avg_sale = total_income / sales.len() as f64;
        let spike_threshold = avg_sale * 2.0;

        let spike_sales: Vec<&Transaction> = sales
            .iter()
            .filter(|tx| tx.amount > spike_threshold)
            .cloned()
            .collect();

        if spike_sales.is_empty() {
            return 0.0;
        }

        // Savings within 30 days of each spike
        let thirty_days = 30 * 86400;
        let mut post_spike_savings = 0.0;
        let mut spike_total = 0.0;

        for spike in &spike_sales {
            spike_total += spike.amount;
            for saving in &savings {
                if saving.timestamp > spike.timestamp
                    && saving.timestamp < spike.timestamp + thirty_days
                {
                    post_spike_savings += saving.amount;
                }
            }
        }

        if spike_total > 0.0 {
            post_spike_savings / spike_total
        } else {
            0.0
        }
    }

    /// Count unique buyers
    fn buyer_diversity(&self, transactions: &[Transaction]) -> u8 {
        let unique_buyers: std::collections::HashSet<String> = transactions
            .iter()
            .filter(|tx| tx.category == TransactionCategory::Sale)
            .filter_map(|tx| tx.counterparty_id.clone())
            .collect();
        unique_buyers.len() as u8
    }

    /// Estimate storage duration (days between harvest sale and next income)
    fn avg_storage_duration(&self, transactions: &[Transaction]) -> u32 {
        let sales: Vec<&Transaction> = transactions
            .iter()
            .filter(|tx| tx.category == TransactionCategory::Sale)
            .collect();

        if sales.len() < 2 {
            return 0;
        }

        // Average gap between consecutive sales
        let mut sorted = sales.clone();
        sorted.sort_by_key(|tx| tx.timestamp);

        let gaps: Vec<u32> = sorted
            .windows(2)
            .map(|w| ((w[1].timestamp - w[0].timestamp) / 86400) as u32)
            .filter(|&g| g > 0 && g < 365)
            .collect();

        if gaps.is_empty() {
            0
        } else {
            gaps.iter().sum::<u32>() / gaps.len() as u32
        }
    }
}

impl WorkerTypeFeatureExtractor for FarmerFeatureExtractor {
    fn extract(&self, transactions: &[Transaction], context: &WorkerContext) -> TypeFeatures {
        let primary_crop = self.detect_crop(transactions);
        let land_size = self.estimate_land_size(transactions);
        let harvest_cycle = self.detect_harvest_cycle(transactions);
        let has_coop = self.detect_cooperative(transactions);
        let input_ratio = self.input_investment_ratio(transactions);
        let savings_ratio = self.post_harvest_savings_ratio(transactions);
        let buyer_div = self.buyer_diversity(transactions);
        let storage_days = self.avg_storage_duration(transactions);

        // Intra-season stability: will be computed in seasonality module
        // For now: placeholder based on harvest cycle consistency
        let intra_season_stability = if harvest_cycle.is_some() { 0.7 } else { 0.5 };

        // Seasonal ratio: peak/trough
        let seasonal_ratio = 3.0; // placeholder — computed from monthly profile

        let features = FarmerFeatures {
            primary_crop,
            land_size_bucket: land_size,
            harvest_cycle_days: harvest_cycle,
            intra_season_stability,
            seasonal_ratio,
            input_investment_ratio: input_ratio,
            has_cooperative_membership: has_coop,
            post_harvest_savings_ratio: savings_ratio,
            buyer_diversity: buyer_div,
            avg_storage_duration_days: storage_days,
        };

        // Normalize to feature vector
        let feature_vector = vec![
            primary_crop.normalize(),
            land_size.normalize(),
            harvest_cycle
                .map(|c| (c as f64 / 365.0).min(1.0))
                .unwrap_or(0.5),
            intra_season_stability,
            (seasonal_ratio / 10.0).min(1.0),
            input_ratio,
            if has_coop { 1.0 } else { 0.0 },
            savings_ratio.min(1.0),
            (buyer_div as f64 / 10.0).min(1.0),
            (storage_days as f64 / 90.0).min(1.0),
        ];

        TypeFeatures::from_features(
            WorkerType::Farmer,
            &features,
            feature_vector,
            self.feature_names(),
        )
    }

    fn worker_type(&self) -> WorkerType {
        WorkerType::Farmer
    }

    fn min_transactions(&self) -> usize {
        90
    }

    fn feature_names(&self) -> Vec<&'static str> {
        vec![
            "crop_type",
            "land_size",
            "harvest_cycle",
            "intra_season_stability",
            "seasonal_ratio",
            "input_investment",
            "cooperative_membership",
            "post_harvest_savings",
            "buyer_diversity",
            "storage_duration",
        ]
    }
}
