//! Enhanced seasonality detection for credit scoring

use chrono::NaiveDate;
use std::collections::BTreeMap;

/// Detect periodic patterns in income time series
pub struct SeasonalityDetector {
    /// Daily income history (date → total income)
    daily_income: BTreeMap<NaiveDate, f64>,
    /// Detected periods (cycle_length_days, strength)
    detected_periods: Vec<PeriodCandidate>,
}

pub struct PeriodCandidate {
    pub cycle_length_days: u32, // e.g., 7 (weekly), 30 (monthly), 365 (annual)
    pub strength: f64,          // 0.0-1.0, how strong the periodic signal is
    pub phase: f64,             // where in the cycle we currently are
    pub peak_months: Vec<u32>,  // months with highest income
    pub trough_months: Vec<u32>, // months with lowest income
}

/// Instead of comparing to overall average, compare to same-period historical
pub struct SeasonalBaseline {
    /// Monthly income averages (indexed 0-11)
    monthly_baselines: [f64; 12],
    /// Weekly income averages (indexed 0-6, Monday=0)
    weekly_baselines: [f64; 7],
    /// Whether this worker has seasonal patterns
    is_seasonal: bool,
    /// Seasonality strength (0.0 = flat, 1.0 = highly seasonal)
    seasonality_strength: f64,
}

impl SeasonalBaseline {
    /// Compute seasonality-adjusted income stability
    /// Instead of coefficient of variation (which penalizes seasonality),
    /// compute how well income matches the seasonal pattern
    pub fn adjusted_stability(&self, monthly_incomes: &[f64; 12]) -> f64 {
        if !self.is_seasonal {
            // Non-seasonal workers: use traditional stability
            return coefficient_of_variation(monthly_incomes);
        }

        // Seasonal workers: compare each month to its baseline
        let deviations: Vec<f64> = monthly_incomes
            .iter()
            .enumerate()
            .map(|(i, &income)| {
                let baseline = self.monthly_baselines[i];
                if baseline > 0.0 {
                    ((income - baseline) / baseline).abs()
                } else {
                    0.0
                }
            })
            .collect();

        // Stability = 1 - mean(deviation) — higher is better
        let mean_deviation = deviations.iter().sum::<f64>() / deviations.len() as f64;
        (1.0 - mean_deviation).max(0.0)
    }

    /// Check if current period is "on track" compared to historical
    pub fn is_on_track(&self, current_month: u32, current_income: f64) -> bool {
        let baseline = self.monthly_baselines[current_month as usize];
        // Within 40% of historical baseline = on track
        (current_income - baseline).abs() / baseline.max(1.0) < 0.4
    }
}

/// Compare current period to same period last year
pub struct IncomeTrajectory {
    /// Year-over-year growth rate for each month
    pub yoy_monthly_growth: [f64; 12],
    /// Overall annual growth trend
    pub annual_growth_rate: f64,
    /// Trajectory classification
    pub trajectory: TrajectoryType,
}

pub enum TrajectoryType {
    Growing,      // YoY positive across most months
    Stable,       // YoY within ±10%
    Declining,    // YoY negative across most months
    Volatile,     // Mixed signals
    Insufficient, // Not enough history
}

/// Seasonality-adjusted base features
pub struct AdjustedBaseFeatures {
    // Original base features (unchanged)
    pub raw: CreditFeatures,

    // Seasonality-adjusted features
    pub adjusted_stability: f64, // replaces raw consistency_score for seasonal workers
    pub income_trajectory: TrajectoryType,
    pub yoy_growth_rate: f64,
    pub is_seasonal: bool,
    pub seasonality_strength: f64,
}

impl AdjustedBaseFeatures {
    /// Get the appropriate stability score (seasonal-adjusted or raw)
    pub fn effective_stability(&self) -> f64 {
        if self.is_seasonal && self.seasonality_strength > 0.3 {
            self.adjusted_stability
        } else {
            self.raw.consistency_score
        }
    }
}
