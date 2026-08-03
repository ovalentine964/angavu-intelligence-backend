// Credit Scoring — Artisan/Maker Feature Extractor
//
// Covers archetype: Artisan (M-001–M-028)
// Welder, Carpenter, Tailor, Potter, Basket Weaver, etc.

use super::{Transaction, TransactionCategory, WorkerContext, WorkerTypeFeatureExtractor};
use crate::credit::types::{TypeFeatures, WorkerType};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ArtisanFeatures {
    /// Average job value
    pub avg_job_value: f64,
    /// Material cost as fraction of job price
    pub material_cost_ratio: f64,
    /// Number of jobs per month
    pub jobs_per_month: f64,
    /// Revenue volatility (project-based income)
    pub revenue_volatility: f64,
    /// Fraction of repeat customers
    pub repeat_customer_ratio: f64,
    /// Average days between jobs
    pub avg_gap_between_jobs: f64,
    /// Tool/equipment investment proxy
    pub tool_investment_proxy: f64,
    /// Upfront payment ratio
    pub upfront_payment_ratio: f64,
}

pub struct ArtisanFeatureExtractor;

impl ArtisanFeatureExtractor {
    pub fn new() -> Self {
        Self
    }
}

impl WorkerTypeFeatureExtractor for ArtisanFeatureExtractor {
    fn extract(&self, transactions: &[Transaction], _context: &WorkerContext) -> TypeFeatures {
        let sales: Vec<f64> = transactions
            .iter()
            .filter(|tx| tx.category == TransactionCategory::Sale)
            .map(|tx| tx.amount)
            .collect();
        let avg_job_value = if sales.is_empty() {
            0.0
        } else {
            sales.iter().sum::<f64>() / sales.len() as f64
        };
        let jobs_per_month = sales.len() as f64 / 3.0; // Assuming 3 months of data
        let material_cost_ratio = 0.40; // Placeholder
        let revenue_volatility = 0.5; // Project-based = high volatility

        let features = ArtisanFeatures {
            avg_job_value,
            material_cost_ratio,
            jobs_per_month,
            revenue_volatility,
            repeat_customer_ratio: 0.3,
            avg_gap_between_jobs: 30.0 / jobs_per_month.max(1.0),
            tool_investment_proxy: 0.0,
            upfront_payment_ratio: 0.5,
        };

        let feature_vector = vec![
            avg_job_value / 50000.0,
            material_cost_ratio,
            jobs_per_month / 20.0,
            revenue_volatility,
            features.repeat_customer_ratio,
            features.avg_gap_between_jobs / 30.0,
            features.tool_investment_proxy,
            features.upfront_payment_ratio,
        ];

        TypeFeatures {
            worker_type: WorkerType::Artisan,
            features: serde_json::to_value(&features).unwrap_or_default(),
            feature_vector,
            feature_names: vec![
                "avg_job_value",
                "material_cost_ratio",
                "jobs_per_month",
                "revenue_volatility",
                "repeat_customer_ratio",
                "avg_gap_between_jobs",
                "tool_investment_proxy",
                "upfront_payment_ratio",
            ]
            .into_iter()
            .map(String::from)
            .collect(),
        }
    }

    fn worker_type(&self) -> WorkerType {
        WorkerType::Artisan
    }
    fn min_transactions(&self) -> usize {
        20
    }
    fn feature_names(&self) -> Vec<&'static str> {
        vec![
            "avg_job_value",
            "material_cost_ratio",
            "jobs_per_month",
            "revenue_volatility",
            "repeat_customer_ratio",
            "avg_gap_between_jobs",
            "tool_investment_proxy",
            "upfront_payment_ratio",
        ]
    }
}
