// Credit Scoring — Seasonality-Adjusted Base Features
// Wraps existing CreditFeatures with seasonal adjustment

use crate::credit::seasonality::SeasonalBaseline;
use crate::credit::seasonality_enhanced::TrajectoryType;
use serde::{Deserialize, Serialize};

/// Existing credit features from credit_feedback.rs (unchanged for backward compat)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CreditFeatures {
    pub transaction_count_90d: u32,
    pub daily_avg_revenue_bucket: String,
    pub active_days_ratio: f64,
    pub revenue_volatility: f64,
    pub product_diversity: u8,
    pub consistency_score: f64,
    pub repayment_history_count: u32,
    pub loan_count: u32,
    pub days_since_last_transaction: u32,
    pub region_economic_index: f64,
}

/// Seasonality-adjusted base features.
/// Wraps CreditFeatures with seasonal correction.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AdjustedBaseFeatures {
    /// Original raw features (unchanged)
    pub raw: CreditFeatures,

    /// Seasonality-adjusted stability score
    /// For seasonal workers: replaces consistency_score
    pub adjusted_stability: f64,

    /// Income trajectory (YoY growth)
    pub income_trajectory: TrajectoryType,

    /// Year-over-year growth rate
    pub yoy_growth_rate: f64,

    /// Whether seasonal pattern was detected
    pub is_seasonal: bool,

    /// Strength of seasonality signal (0.0-1.0)
    pub seasonality_strength: f64,
}

impl AdjustedBaseFeatures {
    /// Create from raw features + seasonality analysis
    pub fn from_raw_with_seasonality(
        raw: CreditFeatures,
        seasonal_baseline: Option<&SeasonalBaseline>,
        monthly_incomes_current: Option<&[f64; 12]>,
        monthly_incomes_previous: Option<&[f64; 12]>,
    ) -> Self {
        match (seasonal_baseline, monthly_incomes_current) {
            (Some(baseline), Some(current)) if baseline.is_seasonal => {
                let adjusted_stability = baseline.adjusted_stability(current);
                let yoy = match monthly_incomes_previous {
                    Some(previous) => baseline.yoy_growth(current, previous),
                    None => super::seasonality::IncomeTrajectory {
                        yoy_monthly_growth: [0.0; 12],
                        annual_growth_rate: 0.0,
                        trajectory: TrajectoryType::Insufficient,
                    },
                };

                Self {
                    raw,
                    adjusted_stability,
                    income_trajectory: yoy.trajectory,
                    yoy_growth_rate: yoy.annual_growth_rate,
                    is_seasonal: true,
                    seasonality_strength: baseline.seasonality_strength,
                }
            }
            _ => {
                // No seasonality data or non-seasonal worker
                Self {
                    raw,
                    adjusted_stability: 0.0, // not used for non-seasonal
                    income_trajectory: TrajectoryType::Insufficient,
                    yoy_growth_rate: 0.0,
                    is_seasonal: false,
                    seasonality_strength: 0.0,
                }
            }
        }
    }

    /// Get the effective stability score.
    /// For seasonal workers: returns seasonality-adjusted stability.
    /// For non-seasonal workers: returns raw consistency_score.
    pub fn effective_stability(&self) -> f64 {
        if self.is_seasonal && self.seasonality_strength > 0.3 {
            self.adjusted_stability
        } else {
            self.raw.consistency_score
        }
    }

    /// Get the effective active days ratio.
    /// For seasonal workers: don't penalize low activity during trough months.
    pub fn effective_active_ratio(&self) -> f64 {
        if self.is_seasonal && self.seasonality_strength > 0.3 {
            // During trough months, low activity is expected — don't penalize
            // Use peak-month activity as the real signal
            (self.raw.active_days_ratio * 1.2).min(1.0)
        } else {
            self.raw.active_days_ratio
        }
    }

    /// Normalize to feature vector for model input (10 features)
    pub fn to_feature_vector(&self) -> Vec<f64> {
        vec![
            (self.raw.transaction_count_90d as f64 / 500.0).min(1.0),
            self.effective_active_ratio(),
            1.0 - self.effective_stability().min(1.0), // lower volatility = better
            (self.raw.product_diversity as f64 / 20.0).min(1.0),
            self.effective_stability(),
            (self.raw.repayment_history_count as f64 / 10.0).min(1.0),
            (self.raw.loan_count as f64 / 10.0).min(1.0),
            (1.0 - (self.raw.days_since_last_transaction as f64 / 90.0)).max(0.0),
            self.raw.region_economic_index,
            self.income_trajectory.normalize(),
        ]
    }

    /// Feature names for interpretability
    pub fn feature_names() -> Vec<&'static str> {
        vec![
            "transaction_volume",
            "active_days_ratio",
            "revenue_stability",
            "product_diversity",
            "income_consistency",
            "repayment_history",
            "loan_count",
            "recency",
            "region_economic_index",
            "income_trajectory",
        ]
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample_raw_features() -> CreditFeatures {
        CreditFeatures {
            transaction_count_90d: 150,
            daily_avg_revenue_bucket: "medium".to_string(),
            active_days_ratio: 0.85,
            revenue_volatility: 0.3,
            product_diversity: 5,
            consistency_score: 0.7,
            repayment_history_count: 2,
            loan_count: 3,
            days_since_last_transaction: 1,
            region_economic_index: 0.7,
        }
    }

    #[test]
    fn test_non_seasonal_uses_raw_features() {
        let raw = sample_raw_features();
        let adjusted =
            AdjustedBaseFeatures::from_raw_with_seasonality(raw.clone(), None, None, None);

        assert!(!adjusted.is_seasonal);
        assert_eq!(adjusted.effective_stability(), raw.consistency_score);
        assert_eq!(adjusted.effective_active_ratio(), raw.active_days_ratio);
    }

    #[test]
    fn test_seasonal_farmer_not_penalized() {
        let raw = sample_raw_features();
        let baseline = SeasonalBaseline {
            monthly_baselines: [
                100.0, 100.0, 500.0, 800.0, 600.0, 200.0, 100.0, 100.0, 100.0, 100.0, 200.0, 300.0,
            ],
            weekly_baselines: [0.0; 7],
            is_seasonal: true,
            seasonality_strength: 0.7,
            peak_months: vec![3, 4, 5],
            trough_months: vec![1, 2, 7, 8],
        };

        // Current year follows seasonal pattern
        let current = [
            110.0, 90.0, 520.0, 780.0, 610.0, 190.0, 105.0, 95.0, 110.0, 95.0, 210.0, 310.0,
        ];

        let adjusted = AdjustedBaseFeatures::from_raw_with_seasonality(
            raw,
            Some(&baseline),
            Some(&current),
            None,
        );

        assert!(adjusted.is_seasonal);
        // Seasonal farmer following their pattern should have good stability
        assert!(
            adjusted.effective_stability() > 0.7,
            "On-track farmer should have high effective stability, got {}",
            adjusted.effective_stability()
        );
    }

    #[test]
    fn test_feature_vector_length() {
        let raw = sample_raw_features();
        let adjusted = AdjustedBaseFeatures::from_raw_with_seasonality(raw, None, None, None);
        let fv = adjusted.to_feature_vector();
        assert_eq!(fv.len(), 10);
        assert_eq!(AdjustedBaseFeatures::feature_names().len(), 10);
    }
}
