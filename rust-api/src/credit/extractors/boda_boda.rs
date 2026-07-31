// Credit Scoring — Boda Boda Rider Feature Extractor
// Extracts credit signals unique to motorcycle transport workers

use serde::{Deserialize, Serialize};
use super::{Transaction, TransactionCategory, PaymentMethod, WorkerContext, WorkerTypeFeatureExtractor};
use crate::credit::types::{WorkerType, TypeFeatures, AssetValueBucket};

/// Boda boda rider-specific credit features
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BodaBodaFeatures {
    pub asset_value_bucket: AssetValueBucket,
    pub daily_fuel_cost_median: f64,
    pub fuel_cost_ratio: f64,
    pub daily_trip_count_median: u32,
    pub daily_revenue_cv: f64,
    pub peak_hour_income_ratio: f64,
    pub maintenance_frequency_days: u32,
    pub income_trajectory: f64,
    pub weekend_weekday_ratio: f64,
    pub regular_passenger_count: u32,
}

pub struct BodaBodaFeatureExtractor;

impl BodaBodaFeatureExtractor {
    pub fn new() -> Self {
        Self
    }

    /// Estimate motorcycle value from maintenance/repair spending
    fn estimate_asset_value(&self, transactions: &[Transaction]) -> AssetValueBucket {
        let maintenance_spend: f64 = transactions
            .iter()
            .filter(|tx| {
                tx.category == TransactionCategory::Expense
                    && tx.product.as_ref().map_or(false, |p| {
                        let lower = p.to_lowercase();
                        lower.contains("repair")
                            || lower.contains("service")
                            || lower.contains("spare")
                            || lower.contains("tire")
                            || lower.contains("battery")
                            || lower.contains("parts")
                    })
            })
            .map(|tx| tx.amount)
            .sum();

        // Higher maintenance spend → higher value bike
        AssetValueBucket::from_total_spend(maintenance_spend * 3.0) // rough 3x multiplier
    }

    /// Daily fuel cost (median)
    fn daily_fuel_cost(&self, transactions: &[Transaction]) -> f64 {
        let fuel_txns: Vec<f64> = transactions
            .iter()
            .filter(|tx| {
                tx.category == TransactionCategory::Expense
                    && tx.product.as_ref().map_or(false, |p| {
                        let lower = p.to_lowercase();
                        lower.contains("fuel") || lower.contains("petrol") || lower.contains("mafuta")
                    })
            })
            .map(|tx| tx.amount)
            .collect();

        if fuel_txns.is_empty() {
            return 0.0;
        }

        let mut sorted = fuel_txns.clone();
        sorted.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
        sorted[sorted.len() / 2] // median
    }

    /// Fuel cost as ratio of daily revenue
    fn fuel_cost_ratio(&self, transactions: &[Transaction]) -> f64 {
        let daily_fuel = self.daily_fuel_cost(transactions);
        let daily_revenue = self.daily_revenue_median(transactions);
        if daily_revenue > 0.0 {
            (daily_fuel / daily_revenue).min(1.0)
        } else {
            0.0
        }
    }

    /// Daily trip count (individual small M-Pesa receipts = fares)
    fn daily_trip_count(&self, transactions: &[Transaction]) -> u32 {
        let fare_txns: Vec<&Transaction> = transactions
            .iter()
            .filter(|tx| {
                tx.category == TransactionCategory::Sale
                    && tx.payment_method == PaymentMethod::MPesa
                    && tx.amount < 500.0 // typical boda fare
            })
            .collect();

        if fare_txns.is_empty() {
            return 0;
        }

        // Count unique days
        let day_seconds = 86400;
        let mut daily_counts: std::collections::HashMap<i64, u32> = std::collections::HashMap::new();
        for tx in &fare_txns {
            let day = tx.timestamp / day_seconds;
            *daily_counts.entry(day).or_insert(0) += 1;
        }

        if daily_counts.is_empty() {
            0
        } else {
            let mut counts: Vec<u32> = daily_counts.values().copied().collect();
            counts.sort();
            counts[counts.len() / 2] // median
        }
    }

    /// Daily revenue (median)
    fn daily_revenue_median(&self, transactions: &[Transaction]) -> f64 {
        let sales: Vec<&Transaction> = transactions
            .iter()
            .filter(|tx| tx.category == TransactionCategory::Sale)
            .collect();

        if sales.is_empty() {
            return 0.0;
        }

        let day_seconds = 86400;
        let mut daily_revenue: std::collections::HashMap<i64, f64> = std::collections::HashMap::new();
        for tx in &sales {
            let day = tx.timestamp / day_seconds;
            *daily_revenue.entry(day).or_insert(0.0) += tx.amount;
        }

        let mut revenues: Vec<f64> = daily_revenue.values().copied().collect();
        revenues.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
        revenues[revenues.len() / 2]
    }

    /// Daily revenue coefficient of variation
    fn daily_revenue_cv(&self, transactions: &[Transaction]) -> f64 {
        let sales: Vec<&Transaction> = transactions
            .iter()
            .filter(|tx| tx.category == TransactionCategory::Sale)
            .collect();

        if sales.is_empty() {
            return 0.0;
        }

        let day_seconds = 86400;
        let mut daily_revenue: std::collections::HashMap<i64, f64> = std::collections::HashMap::new();
        for tx in &sales {
            let day = tx.timestamp / day_seconds;
            *daily_revenue.entry(day).or_insert(0.0) += tx.amount;
        }

        let revenues: Vec<f64> = daily_revenue.values().copied().collect();
        if revenues.len() < 2 {
            return 0.0;
        }

        let mean = revenues.iter().sum::<f64>() / revenues.len() as f64;
        if mean < 1.0 {
            return 0.0;
        }

        let variance = revenues.iter().map(|r| (r - mean).powi(2)).sum::<f64>() / revenues.len() as f64;
        variance.sqrt() / mean
    }

    /// Peak hours income ratio (7-9am + 5-7pm vs rest)
    fn peak_hour_income_ratio(&self, transactions: &[Transaction]) -> f64 {
        let sales: Vec<&Transaction> = transactions
            .iter()
            .filter(|tx| tx.category == TransactionCategory::Sale)
            .collect();

        if sales.is_empty() {
            return 0.5;
        }

        let total: f64 = sales.iter().map(|tx| tx.amount).sum();
        let peak: f64 = sales
            .iter()
            .filter(|tx| {
                let hour = ((tx.timestamp % 86400) / 3600) as u32;
                (7..9).contains(&hour) || (17..19).contains(&hour)
            })
            .map(|tx| tx.amount)
            .sum();

        if total > 0.0 { peak / total } else { 0.5 }
    }

    /// Maintenance frequency (days between repairs)
    fn maintenance_frequency(&self, transactions: &[Transaction]) -> u32 {
        let repairs: Vec<i64> = transactions
            .iter()
            .filter(|tx| {
                tx.category == TransactionCategory::Expense
                    && tx.product.as_ref().map_or(false, |p| {
                        let lower = p.to_lowercase();
                        lower.contains("repair") || lower.contains("service")
                    })
            })
            .map(|tx| tx.timestamp)
            .collect();

        if repairs.len() < 2 {
            return 90; // default: quarterly
        }

        let mut sorted = repairs.clone();
        sorted.sort();

        let gaps: Vec<u32> = sorted
            .windows(2)
            .map(|w| ((w[1] - w[0]) / 86400) as u32)
            .filter(|&g| g > 0 && g < 365)
            .collect();

        if gaps.is_empty() {
            90
        } else {
            gaps.iter().sum::<u32>() / gaps.len() as u32
        }
    }

    /// Weekend vs weekday income ratio
    fn weekend_weekday_ratio(&self, transactions: &[Transaction]) -> f64 {
        let sales: Vec<&Transaction> = transactions
            .iter()
            .filter(|tx| tx.category == TransactionCategory::Sale)
            .collect();

        if sales.is_empty() {
            return 1.0;
        }

        let mut weekend_total = 0.0;
        let mut weekday_total = 0.0;

        for tx in &sales {
            // Approximate day of week from timestamp (0=Jan 1 1970 was Thursday)
            let days_since_epoch = tx.timestamp / 86400;
            let day_of_week = ((days_since_epoch + 4) % 7) as u32; // 0=Sun, 6=Sat
            if day_of_week == 0 || day_of_week == 6 {
                weekend_total += tx.amount;
            } else {
                weekday_total += tx.amount;
            }
        }

        let weekend_avg = weekend_total / 2.0; // 2 weekend days
        let weekday_avg = weekday_total / 5.0; // 5 weekdays

        if weekday_avg > 0.0 {
            (weekend_avg / weekday_avg).min(3.0)
        } else {
            1.0
        }
    }

    /// Regular passengers (counterparties with >5 transactions)
    fn regular_passenger_count(&self, transactions: &[Transaction]) -> u32 {
        let mut counterparty_counts: std::collections::HashMap<String, u32> = std::collections::HashMap::new();
        for tx in transactions {
            if tx.category == TransactionCategory::Sale {
                if let Some(ref cp) = tx.counterparty_id {
                    *counterparty_counts.entry(cp.clone()).or_insert(0) += 1;
                }
            }
        }
        counterparty_counts.values().filter(|&&count| count > 5).count() as u32
    }
}

impl WorkerTypeFeatureExtractor for BodaBodaFeatureExtractor {
    fn extract(&self, transactions: &[Transaction], _context: &WorkerContext) -> TypeFeatures {
        let asset_value = self.estimate_asset_value(transactions);
        let fuel_cost = self.daily_fuel_cost(transactions);
        let fuel_ratio = self.fuel_cost_ratio(transactions);
        let trip_count = self.daily_trip_count(transactions);
        let revenue_cv = self.daily_revenue_cv(transactions);
        let peak_ratio = self.peak_hour_income_ratio(transactions);
        let maint_freq = self.maintenance_frequency(transactions);
        let weekend_ratio = self.weekend_weekday_ratio(transactions);
        let regular_count = self.regular_passenger_count(transactions);

        let features = BodaBodaFeatures {
            asset_value_bucket: asset_value,
            daily_fuel_cost_median: fuel_cost,
            fuel_cost_ratio: fuel_ratio,
            daily_trip_count_median: trip_count,
            daily_revenue_cv: revenue_cv,
            peak_hour_income_ratio: peak_ratio,
            maintenance_frequency_days: maint_freq,
            income_trajectory: 0.0, // computed externally
            weekend_weekday_ratio: weekend_ratio,
            regular_passenger_count: regular_count,
        };

        let feature_vector = vec![
            asset_value.normalize(),
            (fuel_cost / 500.0).min(1.0), // normalize to 500 KES max
            fuel_ratio,
            (trip_count as f64 / 30.0).min(1.0), // normalize to 30 trips max
            1.0 - revenue_cv.min(1.0), // lower CV = better
            peak_ratio,
            (1.0 - (maint_freq as f64 / 90.0)).max(0.0), // more frequent = better maintenance
            (weekend_ratio - 0.5).abs().min(1.0), // closer to 1.0 = balanced
            (regular_count as f64 / 20.0).min(1.0),
            0.5, // income_trajectory placeholder
        ];

        TypeFeatures::from_features(
            WorkerType::BodaBodaRider,
            &features,
            feature_vector,
            self.feature_names(),
        )
    }

    fn worker_type(&self) -> WorkerType {
        WorkerType::BodaBodaRider
    }

    fn min_transactions(&self) -> usize {
        30
    }

    fn feature_names(&self) -> Vec<&'static str> {
        vec![
            "asset_value", "fuel_cost", "fuel_ratio", "trip_count",
            "revenue_stability", "peak_utilization", "maintenance_frequency",
            "weekend_balance", "regular_passengers", "income_trajectory",
        ]
    }
}
