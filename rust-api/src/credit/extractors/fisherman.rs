// Credit Scoring — Fisherman Feature Extractor

use super::{Transaction, TransactionCategory, WorkerContext, WorkerTypeFeatureExtractor};
use crate::credit::types::{BoatOwnership, FishingZone, TypeFeatures, WorkerType};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FishermanFeatures {
    pub boat_ownership: BoatOwnership,
    pub fishing_zone: FishingZone,
    pub catch_cycle_days: Option<u32>,
    pub monthly_income_profile: [f64; 12],
    pub landing_site_count: u8,
    pub has_cold_chain_access: bool,
    pub intra_season_stability: f64,
    pub avg_weather_gap_days: u32,
    pub savings_rate: f64,
    pub buyer_diversity: u8,
}

pub struct FishermanFeatureExtractor;

impl FishermanFeatureExtractor {
    pub fn new() -> Self {
        Self
    }

    fn detect_boat_ownership(&self, transactions: &[Transaction]) -> BoatOwnership {
        let has_major_repair = transactions.iter().any(|tx| {
            tx.category == TransactionCategory::Expense
                && tx.amount > 10_000.0
                && tx.product.as_ref().map_or(false, |p| {
                    let l = p.to_lowercase();
                    l.contains("boat") || l.contains("engine") || l.contains("meshi")
                })
        });
        if has_major_repair {
            BoatOwnership::Owned
        } else {
            BoatOwnership::Shared
        }
    }

    fn detect_fishing_zone(&self, transactions: &[Transaction]) -> FishingZone {
        let sales: Vec<&Transaction> = transactions
            .iter()
            .filter(|tx| tx.category == TransactionCategory::Sale)
            .collect();
        let avg_catch_value: f64 = if sales.is_empty() {
            0.0
        } else {
            sales.iter().map(|tx| tx.amount).sum::<f64>() / sales.len() as f64
        };
        if avg_catch_value > 10_000.0 {
            FishingZone::DeepSea
        } else if avg_catch_value > 3_000.0 {
            FishingZone::Offshore
        } else {
            FishingZone::Nearshore
        }
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
        for i in 0..12 {
            if counts[i] > 0 {
                profile[i] = totals[i] / counts[i] as f64;
            }
        }
        profile
    }

    fn detect_cold_chain(&self, transactions: &[Transaction]) -> bool {
        transactions.iter().any(|tx| {
            tx.product.as_ref().map_or(false, |p| {
                let l = p.to_lowercase();
                l.contains("ice")
                    || l.contains("cold")
                    || l.contains("freez")
                    || l.contains("barafu")
            })
        })
    }

    fn weather_gap_days(&self, transactions: &[Transaction]) -> u32 {
        let sales: Vec<i64> = transactions
            .iter()
            .filter(|tx| tx.category == TransactionCategory::Sale)
            .map(|tx| tx.timestamp / 86400)
            .collect();
        if sales.len() < 2 {
            return 0;
        }
        let mut sorted = sales.clone();
        sorted.sort();
        sorted.dedup();
        let mut max_gap = 0u32;
        let mut current_gap = 0u32;
        for w in sorted.windows(2) {
            let gap = (w[1] - w[0]) as u32;
            if gap > 3 {
                current_gap += gap;
            } else {
                current_gap = 0;
            }
            max_gap = max_gap.max(current_gap);
        }
        max_gap
    }

    fn savings_rate(&self, transactions: &[Transaction]) -> f64 {
        let income: f64 = transactions
            .iter()
            .filter(|tx| tx.category == TransactionCategory::Sale)
            .map(|tx| tx.amount)
            .sum();
        let savings: f64 = transactions
            .iter()
            .filter(|tx| tx.category == TransactionCategory::Savings)
            .map(|tx| tx.amount)
            .sum();
        if income > 0.0 {
            (savings / income).min(1.0)
        } else {
            0.0
        }
    }

    fn buyer_diversity(&self, transactions: &[Transaction]) -> u8 {
        let unique: std::collections::HashSet<String> = transactions
            .iter()
            .filter(|tx| tx.category == TransactionCategory::Sale)
            .filter_map(|tx| tx.counterparty_id.clone())
            .collect();
        unique.len() as u8
    }
}

impl WorkerTypeFeatureExtractor for FishermanFeatureExtractor {
    fn extract(&self, transactions: &[Transaction], _ctx: &WorkerContext) -> TypeFeatures {
        let boat = self.detect_boat_ownership(transactions);
        let zone = self.detect_fishing_zone(transactions);
        let profile = self.monthly_profile(transactions);
        let cold_chain = self.detect_cold_chain(transactions);
        let weather_gap = self.weather_gap_days(transactions);
        let savings = self.savings_rate(transactions);
        let buyers = self.buyer_diversity(transactions);

        let features = FishermanFeatures {
            boat_ownership: boat,
            fishing_zone: zone,
            catch_cycle_days: None,
            monthly_income_profile: profile,
            landing_site_count: buyers.min(10),
            has_cold_chain_access: cold_chain,
            intra_season_stability: 0.7,
            avg_weather_gap_days: weather_gap,
            savings_rate: savings,
            buyer_diversity: buyers,
        };

        let fv = vec![
            match boat {
                BoatOwnership::Owned => 1.0,
                BoatOwnership::Leased => 0.6,
                BoatOwnership::Shared => 0.3,
            },
            match zone {
                FishingZone::DeepSea => 1.0,
                FishingZone::Offshore => 0.6,
                FishingZone::Nearshore => 0.3,
            },
            0.5, // catch_cycle placeholder
            0.7, // stability placeholder
            (buyers as f64 / 10.0).min(1.0),
            if cold_chain { 1.0 } else { 0.0 },
            (1.0 - (weather_gap as f64 / 30.0)).max(0.0),
            savings,
            (profile.iter().sum::<f64>() / 12.0 / 5000.0).min(1.0),
            0.5,
        ];

        TypeFeatures::from_features(WorkerType::Fisherman, &features, fv, self.feature_names())
    }

    fn worker_type(&self) -> WorkerType {
        WorkerType::Fisherman
    }
    fn min_transactions(&self) -> usize {
        90
    }
    fn feature_names(&self) -> Vec<&'static str> {
        vec![
            "boat_ownership",
            "fishing_zone",
            "catch_cycle",
            "stability",
            "landing_sites",
            "cold_chain",
            "weather_resilience",
            "savings_rate",
            "income_level",
            "trajectory",
        ]
    }
}
