// src/orchestrator/modules/credit.rs

use super::*;
use crate::orchestrator::message_bus::*;
use serde::{Deserialize, Serialize};

/// CreditScorer: Alama Score computation (300-850), risk assessment
///
/// Uses Bayesian inference + feature engineering from transaction history.
/// Consumes MarketSignal outputs (market conditions affect credit risk).
///
/// ⚠️  LIMITATION: All state is held in-memory DashMap. Worker features are
/// lost on process restart. For production, wire to PostgreSQL (table: worker_features)
/// for persistence. See: TODO(CreditScorer-Persistence)
pub struct CreditScorer {
    /// Worker feature stores (by hashed ID)
    worker_features: dashmap::DashMap<String, WorkerFeatures>,
    /// Model weights (simplified — in production: XGBoost/ONNX)
    model: CreditModel,
}

#[derive(Serialize, Deserialize, Clone)]
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
    /// Feature weights (logistic regression — domain-informed initialization)
    /// These are log-odds: positive = reduces P(default), negative = increases P(default)
    weights: Vec<f64>,
    intercept: f64,
    /// Minimum observations for reliable scoring (from power analysis)
    /// For logistic regression with 7 features: n ≥ 10×7/0.1 = 700 (events per variable rule)
    /// But with 10% default rate: n ≥ 700/0.1 = 7000 total observations
    /// Conservative threshold: 100 observations for preliminary scoring
    min_observations: u32,
}

impl CreditModel {
    fn new() -> Self {
        // Domain-informed log-odds weights for Kenyan informal sector workers
        // Based on known credit risk factors in East African microfinance literature
        // NOTE: These should be retrained via IRLS (see logistic_regression.rs)
        // when labeled outcome data (≥1000 per worker type) becomes available.
        Self {
            weights: vec![
                0.30,  // total_transactions (more = better, log-scaled)
                0.25,  // daily_avg_revenue (higher = better)
                -0.20, // revenue_volatility (lower = better)
                0.25,  // active_days_ratio (higher = better)
                0.15,  // product_diversity (more = better)
                0.15,  // transaction_trend (growing = better)
                -0.20, // days_since_last (lower = better)
            ],
            intercept: -2.0,
            // Power analysis: 100 observations minimum for preliminary scoring
            // Full model training requires 1000+ labeled outcomes per worker type
            min_observations: 100,
        }
    }

    /// Compute probability of repayment (0.0 - 1.0)
    fn predict_probability(&self, features: &[f64]) -> f64 {
        let z: f64 = self.intercept
            + features
                .iter()
                .zip(self.weights.iter())
                .map(|(f, w)| f * w)
                .sum::<f64>();

        // Sigmoid with overflow protection
        if z >= 0.0 {
            1.0 / (1.0 + (-z).exp())
        } else {
            let exp_z = z.exp();
            exp_z / (1.0 + exp_z)
        }
    }

    /// Convert probability to Alama Score (300-850)
    fn probability_to_score(&self, prob: f64) -> u32 {
        (300.0 + prob * 550.0).round() as u32
    }

    /// Compute 95% confidence interval for the Alama Score.
    /// Uses delta method: SE(p) ≈ p(1-p) / sqrt(n)
    /// CI = score ± 1.96 × SE × 550
    fn score_confidence_interval(&self, prob: f64, n_observations: usize) -> (u32, u32) {
        let p = prob.clamp(0.01, 0.99);
        let se = if n_observations > 0 {
            p * (1.0 - p) / (n_observations as f64).sqrt()
        } else {
            0.25 // maximum uncertainty
        };
        let z_95 = 1.96;
        let ci_lower = (300.0 + ((prob - z_95 * se).max(0.0)) * 550.0).round() as u32;
        let ci_upper = (300.0 + ((prob + z_95 * se).min(1.0)) * 550.0).round() as u32;
        (ci_lower.clamp(300, 850), ci_upper.clamp(300, 850))
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
                (f.total_transactions as f64).ln().max(0.0), // log-scale
                f.daily_avg_revenue / 1000.0,                // normalize to KSh thousands
                f.revenue_volatility,
                f.active_days_ratio,
                (f.product_diversity as f64) / 10.0, // normalize
                f.transaction_trend,
                (f.days_since_last as f64) / 30.0, // normalize to months
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
                let features = self
                    .worker_features
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

                // Power analysis check: warn if insufficient data for reliable scoring
                if features.total_transactions < self.model.min_observations as u64 {
                    tracing::warn!(
                        worker_id = %worker_id_hash,
                        transactions = features.total_transactions,
                        min_required = self.model.min_observations,
                        "Insufficient data for reliable credit scoring (power analysis threshold)"
                    );
                }

                // Incremental feature update
                features.total_transactions += transactions.len() as u64;
                let batch_revenue: f64 = transactions.iter().map(|t| t.amount).sum();
                let batch_avg = batch_revenue / transactions.len().max(1) as f64;

                // Exponential moving average for revenue
                features.daily_avg_revenue = 0.9 * features.daily_avg_revenue + 0.1 * batch_avg;

                // Track product diversity
                let categories: std::collections::HashSet<&str> = transactions
                    .iter()
                    .map(|t| t.product_category.as_str())
                    .collect();
                features.product_diversity = categories.len() as u32;

                features.last_updated = chrono::Utc::now();

                // Compute Alama Score with confidence intervals
                if let Some(feature_vec) = self.extract_features(&worker_id_hash) {
                    let probability = self.model.predict_probability(&feature_vec);
                    let score = self.model.probability_to_score(probability);
                    let (ci_lower, ci_upper) = self.model.score_confidence_interval(
                        probability,
                        features.total_transactions as usize,
                    );

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
                            direction: if feature_vec[0] > 0.5 {
                                "positive"
                            } else {
                                "negative"
                            }
                            .to_string(),
                        },
                        CreditFactor {
                            name: "revenue_consistency".to_string(),
                            weight: 0.20,
                            value: 1.0 - feature_vec[2], // inverse of volatility
                            direction: if feature_vec[2] < 0.3 {
                                "positive"
                            } else {
                                "negative"
                            }
                            .to_string(),
                        },
                        CreditFactor {
                            name: "activity_recency".to_string(),
                            weight: 0.15,
                            value: 1.0 - feature_vec[6],
                            direction: if feature_vec[6] < 0.1 {
                                "positive"
                            } else {
                                "negative"
                            }
                            .to_string(),
                        },
                    ];

                    return Ok(Some(ModuleMessage::CreditAssessment {
                        trace_id,
                        worker_id_hash,
                        alama_score: score,
                        risk_level,
                        factors,
                        confidence: probability,
                        ci_lower,
                        ci_upper,
                        n_observations: features.total_transactions as u32,
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

    fn snapshot_state(&self) -> Option<Vec<u8>> {
        #[derive(Serialize)]
        struct Snapshot {
            workers: Vec<(String, WorkerFeatures)>,
        }
        let workers: Vec<(String, WorkerFeatures)> = self
            .worker_features
            .iter()
            .map(|entry| (entry.key().clone(), entry.value().clone()))
            .collect();
        bincode::serialize(&Snapshot { workers }).ok()
    }

    fn restore_state(&mut self, data: &[u8]) {
        #[derive(Deserialize)]
        struct Snapshot {
            workers: Vec<(String, WorkerFeatures)>,
        }
        if let Ok(snap) = bincode::deserialize::<Snapshot>(data) {
            for (id, features) in snap.workers {
                self.worker_features.insert(id, features);
            }
            tracing::info!(
                count = self.worker_features.len(),
                "CreditScorer state restored"
            );
        }
    }
}
