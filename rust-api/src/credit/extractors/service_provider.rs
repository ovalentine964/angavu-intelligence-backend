// Credit Scoring — Service Provider Feature Extractor
//
// Covers archetype: ServiceProvider (S-001–S-034)
// Barber, Hairdresser, Mechanic, Plumber, Electrician, etc.

use super::{Transaction, TransactionCategory, WorkerContext, WorkerTypeFeatureExtractor};
use crate::credit::types::{TypeFeatures, WorkerType};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ServiceProviderFeatures {
    pub avg_service_price: f64,
    pub services_per_day: f64,
    pub parts_markup_ratio: f64,
    pub repeat_customer_ratio: f64,
    pub appointment_regularity: f64,
    pub revenue_volatility: f64,
    pub workspace_cost_ratio: f64,
    pub service_diversity: u8,
}

pub struct ServiceProviderFeatureExtractor;

impl ServiceProviderFeatureExtractor {
    pub fn new() -> Self {
        Self
    }
}

impl WorkerTypeFeatureExtractor for ServiceProviderFeatureExtractor {
    fn extract(&self, transactions: &[Transaction], _context: &WorkerContext) -> TypeFeatures {
        let sales: Vec<f64> = transactions
            .iter()
            .filter(|tx| tx.category == TransactionCategory::Sale)
            .map(|tx| tx.amount)
            .collect();
        let avg_service_price = if sales.is_empty() {
            0.0
        } else {
            sales.iter().sum::<f64>() / sales.len() as f64
        };
        let services_per_day = sales.len() as f64 / 30.0;
        let service_diversity = transactions
            .iter()
            .filter(|tx| tx.category == TransactionCategory::Sale)
            .filter_map(|tx| tx.product.clone())
            .collect::<std::collections::HashSet<_>>()
            .len() as u8;

        let features = ServiceProviderFeatures {
            avg_service_price,
            services_per_day,
            parts_markup_ratio: 0.20,
            repeat_customer_ratio: 0.5,
            appointment_regularity: 0.6,
            revenue_volatility: 0.3,
            workspace_cost_ratio: 0.10,
            service_diversity,
        };

        TypeFeatures {
            worker_type: WorkerType::ServiceProvider,
            features: serde_json::to_value(&features).unwrap_or_default(),
            feature_vector: vec![
                avg_service_price / 5000.0,
                services_per_day / 20.0,
                features.parts_markup_ratio,
                features.repeat_customer_ratio,
                features.appointment_regularity,
                features.revenue_volatility,
                features.workspace_cost_ratio,
                service_diversity as f64 / 20.0,
            ],
            feature_names: vec![
                "avg_service_price",
                "services_per_day",
                "parts_markup",
                "repeat_customers",
                "appointment_regularity",
                "revenue_volatility",
                "workspace_cost",
                "service_diversity",
            ]
            .into_iter()
            .map(String::from)
            .collect(),
        }
    }

    fn worker_type(&self) -> WorkerType {
        WorkerType::ServiceProvider
    }
    fn min_transactions(&self) -> usize {
        20
    }
    fn feature_names(&self) -> Vec<&'static str> {
        vec![
            "avg_service_price",
            "services_per_day",
            "parts_markup",
            "repeat_customers",
            "appointment_regularity",
            "revenue_volatility",
            "workspace_cost",
            "service_diversity",
        ]
    }
}
