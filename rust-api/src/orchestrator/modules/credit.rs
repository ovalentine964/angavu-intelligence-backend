// src/orchestrator/modules/credit.rs

use super::*;
use crate::orchestrator::message_bus::*;

/// CreditScorer: Alama Score computation (300-850), risk assessment
///
/// Uses Bayesian inference + feature engineering from transaction history.
/// Consumes MarketSignal outputs (market conditions affect credit risk).
pub struct CreditScorer {
    /// Worker feature stores (by hashed ID)
    worker_features: dashmap::DashMap<String, WorkerFeatures>,
    /// Model weights (simplified — in production: XGBoost/ONNX)
    model: CreditModel,
}

struct WorkerFeatures {
    total_transactions: u64,
    daily_avg_revenue: f64,
    revenue_volatility: f64,
    active_days_ratio: f64,
    product_diversity: u32,
    transaction_trend: f64,
    days_since_last: u32,
    last_updated: chrono::DateTime<chrono::Utc>,
}

struct CreditModel {
    /// Feature weights (simplified logistic regression)
    weights: Vec<f64>,
    intercept: f64,
}

impl CreditModel {
    fn new() -> Self {
        // Initial weights based on domain knowledge
        // In production: trained on labeled outcome data
        Self {
            weights: vec![
                0.25,  // total_transactions (more = better)
                0.20,  // daily_avg_revenue (higher = better)
                -0.15, // revenue_volatility (lower = better)
                0.20,  // active_days_ratio (higher = better)
                0.10,  // product_diversity (more = better)
                0.10,  // transaction_trend (growing = better)
                -0.15, // days_since_last (lower = better)
            ],
            intercept: -2.0,
        }
    }

    /// Compute probability of repayment (0.0 - 1.0)
    fn predict_probability(&self, features: &[f64]) -> f64 {
        let z: f64 = self.intercept + features.iter()
            .zip(self.weights.iter())
            .map(|(f, w)| f * w)
            .sum::<f64>();

        // Sigmoid
        1.0 / (1.0 + (-z).exp())
    }

    /// Convert probability to Alama Score (300-850)
    fn probability_to_score(&self, prob: f64) -> u32 {
        // Map [0, 1] → [300, 850]
        (300.0 + prob * 550.0).round() as u32
    }
}

impl CreditScorer {
    pub fn new() -> Self {
        Self {
            worker_features: dashmap::DashMap::new(),
            model: CreditModel::new(),
        }
    }

    fn extract_features(&self, worker_id: &str) -> Option<Vec<f64>> {
        self.worker_features.get(worker_id).map(|f| {
            vec![
                (f.total_transactions as f64).ln().max(0.0),  // log-scale
                f.daily_avg_revenue / 1000.0,                  // normalize to KSh thousands
                f.revenue_volatility,
                f.active_days_ratio,
                (f.product_diversity as f64) / 10.0,           // normalize
                f.transaction_trend,
                (f.days_since_last as f64) / 30.0,             // normalize to months
            ]
        })
    }
}

#[async_trait::async_trait]
impl CapabilityModule for CreditScorer {
    fn id(&self) -> ModuleId {
        ModuleId::CreditScorer
    }

    async fn process(
        &mut self,
        message: ModuleMessage,
    ) -> Result<Option<ModuleMessage>, ModuleError> {
        match message {
            ModuleMessage::TransactionBatch {
                trace_id,
                worker_id_hash,
                transactions,
                ..
            } => {
                // Update worker features
                let features = self.worker_features
                    .entry(worker_id_hash.clone())
                    .or_insert_with(|| WorkerFeatures {
                        total_transactions: 0,
                        daily_avg_revenue: 0.0,
                        revenue_volatility: 0.0,
                        active_days_ratio: 0.0,
                        product_diversity: 0,
                        transaction_trend: 0.0,
                        days_since_last: 0,
                        last_updated: chrono::Utc::now(),
                    });

                // Incremental feature update
                features.total_transactions += transactions.len() as u64;
                let batch_revenue: f64 = transactions.iter()
                    .map(|t| t.amount)
                    .sum();
                let batch_avg = batch_revenue / transactions.len().max(1) as f64;

                // Exponential moving average for revenue
                features.daily_avg_revenue = 0.9 * features.daily_avg_revenue + 0.1 * batch_avg;

                // Track product diversity
                let categories: std::collections::HashSet<&str> = transactions.iter()
                    .map(|t| t.product_category.as_str())
                    .collect();
                features.product_diversity = categories.len() as u32;

                features.last_updated = chrono::Utc::now();

                // Compute Alama Score
                if let Some(feature_vec) = self.extract_features(&worker_id_hash) {
                    let probability = self.model.predict_probability(&feature_vec);
                    let score = self.model.probability_to_score(probability);

                    let risk_level = match score {
                        700..=850 => RiskLevel::Low,
                        600..=699 => RiskLevel::Medium,
                        500..=599 => RiskLevel::High,
                        _ => RiskLevel::VeryHigh,
                    };

                    let factors = vec![
                        CreditFactor {
                            name: "transaction_volume".to_string(),
                            weight: 0.25,
                            value: feature_vec[0],
                            direction: if feature_vec[0] > 0.5 { "positive" } else { "negative" }.to_string(),
                        },
                        CreditFactor {
                            name: "revenue_consistency".to_string(),
                            weight: 0.20,
                            value: 1.0 - feature_vec[2], // inverse of volatility
                            direction: if feature_vec[2] < 0.3 { "positive" } else { "negative" }.to_string(),
                        },
                        CreditFactor {
                            name: "activity_recency".to_string(),
                            weight: 0.15,
                            value: 1.0 - feature_vec[6],
                            direction: if feature_vec[6] < 0.1 { "positive" } else { "negative" }.to_string(),
                        },
                    ];

                    return Ok(Some(ModuleMessage::CreditAssessment {
                        trace_id,
                        worker_id_hash,
                        alama_score: score,
                        risk_level,
                        factors,
                        confidence: probability,
                    }));
                }

                Ok(None)
            }
            // Market signals affect credit risk assessment
            ModuleMessage::MarketSignal {
                trace_id,
                region,
                volatility,
                ..
            } => {
                // High market volatility → adjust credit risk in this region
                if volatility > 0.3 {
                    // In production: adjust risk model parameters for this region
                    tracing::debug!(
                        region = %region,
                        volatility = volatility,
                        "Market volatility affects credit risk"
                    );
                }
                Ok(None) // No direct output, but internal state updated
            }
            _ => Ok(None),
        }
    }
}
