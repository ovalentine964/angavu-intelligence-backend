//! CreditScorer — Alama Score (300-850)
//!
//! Computes a credit score for Angavu workers based on their transaction history,
//! payment patterns, and engagement metrics. The Alama Score ranges from 300-850,
//! similar to FICO but tuned for informal economy workers.

use anyhow::{anyhow, Result};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

use crate::db::DatabaseConnections;

/// Credit score output
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CreditScore {
    pub score_id: Uuid,
    pub worker_id: Uuid,
    pub alama_score: u32,
    pub score_range: ScoreRange,
    pub confidence: f64,
    pub factors: Vec<ScoreFactor>,
    pub model_version: String,
    pub computed_at: DateTime<Utc>,
    pub valid_until: DateTime<Utc>,
}

/// Score range classification
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum ScoreRange {
    Excellent, // 750-850
    Good,      // 650-749
    Fair,      // 550-649
    Poor,      // 450-549
    VeryPoor,  // 300-449
}

/// Factor contributing to the score
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScoreFactor {
    pub factor_name: String,
    pub impact: FactorImpact,
    pub weight: f64,
    pub raw_value: f64,
    pub description: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum FactorImpact {
    Positive,
    Negative,
    Neutral,
}

/// Outcome for score calibration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CreditOutcome {
    pub worker_id: Uuid,
    pub outcome_type: OutcomeType,
    pub amount: f64,
    pub timestamp: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum OutcomeType {
    RepaymentOnTime,
    RepaymentLate,
    Default,
    NewIncome,
    ConsistentSavings,
}

/// The CreditScorer tool
pub struct CreditScorer {
    db: DatabaseConnections,
    model_version: String,
}

impl CreditScorer {
    pub fn new(db: DatabaseConnections) -> Self {
        Self {
            db,
            model_version: "alama-v2.1.0".to_string(),
        }
    }

    /// Calculate the Alama Score for a worker
    pub async fn calculate_score(&self, worker_id: Uuid) -> Result<CreditScore> {
        // Fetch worker's transaction history from ClickHouse
        let query = format!(
            r#"
            SELECT 
                count() as tx_count,
                sum(amount) as total_volume,
                avg(amount) as avg_tx,
                stddevPop(amount) as tx_stddev,
                min(event_time) as first_tx,
                max(event_time) as last_tx,
                count(DISTINCT toStartOfMonth(event_time)) as active_months,
                sum(CASE WHEN event_type = 'income' THEN amount ELSE 0 END) as total_income,
                sum(CASE WHEN event_type = 'expense' THEN amount ELSE 0 END) as total_expense
            FROM revenue_events
            WHERE customer_id = '{}'
            "#,
            worker_id
        );

        #[derive(clickhouse::Row, Deserialize)]
        struct TxStats {
            tx_count: u64,
            total_volume: f64,
            avg_tx: f64,
            tx_stddev: f64,
            first_tx: chrono::NaiveDateTime,
            last_tx: chrono::NaiveDateTime,
            active_months: u64,
            total_income: f64,
            total_expense: f64,
        }

        let stats = self
            .db
            .clickhouse
            .query(&query)
            .fetch_one::<TxStats>()
            .await;

        let (stats, factors) = match stats {
            Ok(s) if s.tx_count > 0 => {
                let factors = self.compute_factors(&s);
                (Some(s), factors)
            }
            _ => {
                // New worker with no history — assign baseline score
                let factors = vec![ScoreFactor {
                    factor_name: "new_worker".to_string(),
                    impact: FactorImpact::Neutral,
                    weight: 1.0,
                    raw_value: 0.0,
                    description: "No transaction history available".to_string(),
                }];
                (None, factors)
            }
        };

        // Compute weighted score
        let raw_score = if let Some(ref s) = stats {
            let mut weighted_sum = 0.0;
            let mut total_weight = 0.0;

            for factor in &factors {
                let normalized = normalize_factor(&factor.factor_name, factor.raw_value);
                weighted_sum += normalized * factor.weight;
                total_weight += factor.weight;
            }

            let base = if total_weight > 0.0 {
                weighted_sum / total_weight
            } else {
                0.5
            };

            // Map 0.0-1.0 to 300-850
            (base * 550.0 + 300.0).round() as u32
        } else {
            // Default score for new workers
            500
        };

        let alama_score = raw_score.clamp(300, 850);
        let score_range = ScoreRange::from_score(alama_score);

        // Confidence based on data availability
        let confidence = if let Some(ref s) = stats {
            let tx_factor = (s.tx_count as f64 / 100.0).min(1.0);
            let month_factor = (s.active_months as f64 / 12.0).min(1.0);
            tx_factor * 0.6 + month_factor * 0.4
        } else {
            0.1
        };

        Ok(CreditScore {
            score_id: Uuid::new_v4(),
            worker_id,
            alama_score,
            score_range,
            confidence,
            factors,
            model_version: self.model_version.clone(),
            computed_at: Utc::now(),
            valid_until: Utc::now() + chrono::Duration::days(30),
        })
    }

    /// Update score model from real-world outcomes
    pub async fn update_from_outcome(&self, outcome: &CreditOutcome) -> Result<()> {
        // Store outcome for model recalibration
        sqlx::query!(
            r#"
            INSERT INTO credit_outcomes (id, worker_id, outcome_type, amount, created_at)
            VALUES ($1, $2, $3, $4, $5)
            "#,
            Uuid::new_v4(),
            outcome.worker_id,
            serde_json::to_string(&outcome.outcome_type)?,
            outcome.amount,
            outcome.timestamp
        )
        .execute(&self.db.postgres)
        .await?;

        // Update the worker's score if outcome is significant
        match outcome.outcome_type {
            OutcomeType::Default => {
                // Recalculate score immediately for defaults
                let _ = self.calculate_score(outcome.worker_id).await;
            }
            OutcomeType::RepaymentOnTime => {
                // Positive signal — will be picked up in next cycle
            }
            _ => {}
        }

        Ok(())
    }

    /// Get detailed factors for a worker's score
    pub async fn get_factors(&self, worker_id: Uuid) -> Result<Vec<ScoreFactor>> {
        let score = self.calculate_score(worker_id).await?;
        Ok(score.factors)
    }

    // Private helpers

    fn compute_factors(
        &self,
        stats: &impl TxStatsLike,
    ) -> Vec<ScoreFactor> {
        let mut factors = Vec::new();

        // Factor 1: Transaction volume (higher is better)
        factors.push(ScoreFactor {
            factor_name: "transaction_volume".to_string(),
            impact: if stats.tx_count() > 50 {
                FactorImpact::Positive
            } else {
                FactorImpact::Negative
            },
            weight: 0.15,
            raw_value: stats.tx_count() as f64,
            description: format!("{} total transactions", stats.tx_count()),
        });

        // Factor 2: Active months (consistency)
        factors.push(ScoreFactor {
            factor_name: "consistency".to_string(),
            impact: if stats.active_months() >= 6 {
                FactorImpact::Positive
            } else {
                FactorImpact::Negative
            },
            weight: 0.25,
            raw_value: stats.active_months() as f64,
            description: format!("{} active months", stats.active_months()),
        });

        // Factor 3: Income-to-expense ratio
        let ratio = if stats.total_expense() > 0.0 {
            stats.total_income() / stats.total_expense()
        } else {
            2.0 // Positive if no expenses
        };
        factors.push(ScoreFactor {
            factor_name: "income_expense_ratio".to_string(),
            impact: if ratio > 1.2 {
                FactorImpact::Positive
            } else if ratio < 0.8 {
                FactorImpact::Negative
            } else {
                FactorImpact::Neutral
            },
            weight: 0.3,
            raw_value: ratio,
            description: format!("Income/expense ratio: {:.2}", ratio),
        });

        // Factor 4: Average transaction size (engagement)
        factors.push(ScoreFactor {
            factor_name: "avg_transaction".to_string(),
            impact: FactorImpact::Neutral,
            weight: 0.1,
            raw_value: stats.avg_tx(),
            description: format!("Average transaction: {:.2}", stats.avg_tx()),
        });

        // Factor 5: Transaction regularity (low CV = good)
        let cv = if stats.avg_tx() > 0.0 {
            stats.tx_stddev() / stats.avg_tx()
        } else {
            0.0
        };
        factors.push(ScoreFactor {
            factor_name: "regularity".to_string(),
            impact: if cv < 1.0 {
                FactorImpact::Positive
            } else {
                FactorImpact::Negative
            },
            weight: 0.2,
            raw_value: cv,
            description: format!("Transaction regularity (CV): {:.2}", cv),
        });

        factors
    }
}

/// Trait to abstract over transaction statistics
trait TxStatsLike {
    fn tx_count(&self) -> u64;
    fn total_volume(&self) -> f64;
    fn avg_tx(&self) -> f64;
    fn tx_stddev(&self) -> f64;
    fn active_months(&self) -> u64;
    fn total_income(&self) -> f64;
    fn total_expense(&self) -> f64;
}

impl TxStatsLike for TxStats {
    fn tx_count(&self) -> u64 { self.tx_count }
    fn total_volume(&self) -> f64 { self.total_volume }
    fn avg_tx(&self) -> f64 { self.avg_tx }
    fn tx_stddev(&self) -> f64 { self.tx_stddev }
    fn active_months(&self) -> u64 { self.active_months }
    fn total_income(&self) -> f64 { self.total_income }
    fn total_expense(&self) -> f64 { self.total_expense }
}

struct TxStats {
    tx_count: u64,
    total_volume: f64,
    avg_tx: f64,
    tx_stddev: f64,
    active_months: u64,
    total_income: f64,
    total_expense: f64,
}

/// Normalize a factor to 0.0-1.0 range
fn normalize_factor(name: &str, raw: f64) -> f64 {
    match name {
        "transaction_volume" => (raw / 100.0).min(1.0),
        "consistency" => (raw / 24.0).min(1.0),
        "income_expense_ratio" => ((raw - 0.5) / 2.0).clamp(0.0, 1.0),
        "avg_transaction" => (raw / 10000.0).min(1.0),
        "regularity" => (1.0 - raw / 3.0).clamp(0.0, 1.0),
        _ => 0.5,
    }
}

impl ScoreRange {
    fn from_score(score: u32) -> Self {
        match score {
            750..=850 => ScoreRange::Excellent,
            650..=749 => ScoreRange::Good,
            550..=649 => ScoreRange::Fair,
            450..=549 => ScoreRange::Poor,
            _ => ScoreRange::VeryPoor,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_score_range() {
        assert_eq!(ScoreRange::from_score(800), ScoreRange::Excellent);
        assert_eq!(ScoreRange::from_score(700), ScoreRange::Good);
        assert_eq!(ScoreRange::from_score(600), ScoreRange::Fair);
        assert_eq!(ScoreRange::from_score(500), ScoreRange::Poor);
        assert_eq!(ScoreRange::from_score(350), ScoreRange::VeryPoor);
    }

    #[test]
    fn test_normalize_factor() {
        assert!((normalize_factor("transaction_volume", 50.0) - 0.5).abs() < 0.01);
        assert!((normalize_factor("consistency", 12.0) - 0.5).abs() < 0.01);
    }
}
