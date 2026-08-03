// Credit Scoring — Food Service Feature Extractor
//
// Covers archetypes: FoodService (F-001–F-019)
// Mama Lishe, Chapati Seller, Chips Seller, Nyama Choma, etc.

use super::{Transaction, TransactionCategory, WorkerContext, WorkerTypeFeatureExtractor};
use crate::credit::types::{TypeFeatures, WorkerType};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FoodServiceFeatures {
    /// Average daily revenue
    pub avg_daily_revenue: f64,
    /// Ingredient cost as fraction of revenue (target: 30-50%)
    pub ingredient_cost_ratio: f64,
    /// Fuel cost as fraction of revenue (target: 8-15%)
    pub fuel_cost_ratio: f64,
    /// Number of distinct menu items
    pub menu_diversity: u8,
    /// How many days per week the business operates
    pub operating_days_per_week: f64,
    /// Revenue volatility (coefficient of variation)
    pub revenue_volatility: f64,
    /// Fraction of revenue from delivery platforms
    pub delivery_platform_ratio: f64,
    /// Spoilage-related purchases (proxy for waste)
    pub spoilage_proxy: f64,
    /// Regularity of ingredient purchases
    pub restock_regularity: f64,
}

pub struct FoodServiceFeatureExtractor;

impl FoodServiceFeatureExtractor {
    pub fn new() -> Self {
        Self
    }
}

impl WorkerTypeFeatureExtractor for FoodServiceFeatureExtractor {
    fn extract(&self, transactions: &[Transaction], _context: &WorkerContext) -> TypeFeatures {
        let sales: Vec<f64> = transactions
            .iter()
            .filter(|tx| tx.category == TransactionCategory::Sale)
            .map(|tx| tx.amount)
            .collect();
        let purchases: Vec<f64> = transactions
            .iter()
            .filter(|tx| tx.category == TransactionCategory::Purchase)
            .map(|tx| tx.amount)
            .collect();

        let avg_daily_revenue = if sales.is_empty() {
            0.0
        } else {
            sales.iter().sum::<f64>() / 30.0
        };
        let total_revenue: f64 = sales.iter().sum();
        let total_purchases: f64 = purchases.iter().sum();

        let ingredient_cost_ratio = if total_revenue > 0.0 {
            total_purchases / total_revenue
        } else {
            0.0
        };
        let fuel_cost_ratio = 0.10; // Placeholder — needs fuel category tracking
        let menu_diversity = transactions
            .iter()
            .filter(|tx| tx.category == TransactionCategory::Sale)
            .filter_map(|tx| tx.product.clone())
            .collect::<std::collections::HashSet<_>>()
            .len() as u8;
        let operating_days_per_week = 6.0; // Default for food vendors
        let revenue_volatility = if avg_daily_revenue > 0.0 { 0.3 } else { 0.0 };
        let delivery_platform_ratio = 0.0; // Needs platform detection
        let spoilage_proxy = 0.0; // Needs spoilage tracking
        let restock_regularity = 0.7; // Placeholder

        let features = FoodServiceFeatures {
            avg_daily_revenue,
            ingredient_cost_ratio,
            fuel_cost_ratio,
            menu_diversity,
            operating_days_per_week,
            revenue_volatility,
            delivery_platform_ratio,
            spoilage_proxy,
            restock_regularity,
        };

        let feature_vector = vec![
            avg_daily_revenue / 10000.0, // normalized
            ingredient_cost_ratio,
            fuel_cost_ratio,
            menu_diversity as f64 / 20.0,
            operating_days_per_week / 7.0,
            revenue_volatility,
            delivery_platform_ratio,
            spoilage_proxy,
            restock_regularity,
        ];

        TypeFeatures {
            worker_type: WorkerType::FoodService,
            features: serde_json::to_value(&features).unwrap_or_default(),
            feature_vector,
            feature_names: vec![
                "avg_daily_revenue",
                "ingredient_cost_ratio",
                "fuel_cost_ratio",
                "menu_diversity",
                "operating_days",
                "revenue_volatility",
                "delivery_platform_ratio",
                "spoilage_proxy",
                "restock_regularity",
            ]
            .into_iter()
            .map(String::from)
            .collect(),
        }
    }

    fn worker_type(&self) -> WorkerType {
        WorkerType::FoodService
    }
    fn min_transactions(&self) -> usize {
        30
    }
    fn feature_names(&self) -> Vec<&'static str> {
        vec![
            "avg_daily_revenue",
            "ingredient_cost_ratio",
            "fuel_cost_ratio",
            "menu_diversity",
            "operating_days",
            "revenue_volatility",
            "delivery_platform_ratio",
            "spoilage_proxy",
            "restock_regularity",
        ]
    }
}
