// Credit Scoring — Seasonality Detection and Baseline Calibration
// Detects periodic income patterns (weekly, monthly, seasonal, annual)
// Computes period-over-period baselines instead of penalizing seasonal variance

use chrono::NaiveDate;
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

/// Seasonality detector using autocorrelation analysis.
/// Identifies periodic patterns in income time series.
#[derive(Debug, Clone)]
pub struct SeasonalityDetector {
    /// Daily income history
    daily_income: BTreeMap<NaiveDate, f64>,
    /// Detected periodic patterns
    detected_periods: Vec<PeriodCandidate>,
}

/// A detected periodic pattern in income
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PeriodCandidate {
    /// Cycle length in days (e.g., 7=weekly, 30=monthly, 365=annual)
    pub cycle_length_days: u32,
    /// Signal strength (0.0-1.0)
    pub strength: f64,
    /// Phase offset (where in the cycle the worker currently is)
    pub phase: f64,
    /// Months with highest income (for annual cycles)
    pub peak_months: Vec<u32>,
    /// Months with lowest income (for annual cycles)
    pub trough_months: Vec<u32>,
}

impl SeasonalityDetector {
    pub fn new() -> Self {
        Self {
            daily_income: BTreeMap::new(),
            detected_periods: Vec::new(),
        }
    }

    /// Record daily income data point
    pub fn record_day(&mut self, date: NaiveDate, income: f64) {
        *self.daily_income.entry(date).or_insert(0.0) += income;
    }

    /// Bulk load daily income data
    pub fn load_history(&mut self, data: &[(NaiveDate, f64)]) {
        for (date, income) in data {
            self.record_day(*date, *income);
        }
    }

    /// Detect periodic patterns. Requires minimum 180 days for seasonal detection.
    pub fn detect(&mut self) -> Option<SeasonalityResult> {
        if self.daily_income.len() < 14 {
            return None; // need at least 2 weeks
        }

        let values: Vec<f64> = self.daily_income.values().copied().collect();
        let n = values.len();

        // Compute mean and variance
        let mean: f64 = values.iter().sum::<f64>() / n as f64;
        let variance: f64 = values.iter().map(|v| (v - mean).powi(2)).sum::<f64>() / n as f64;

        if variance < 1e-10 {
            return None; // constant income — no seasonality
        }

        // Test common cycle lengths
        let candidates = vec![
            (7, "weekly"),
            (14, "biweekly"),
            (30, "monthly"),
            (90, "quarterly"),
            (182, "semiannual"),
            (365, "annual"),
        ];

        let mut detected = Vec::new();

        for (period, _label) in candidates {
            if period >= n {
                continue;
            }

            // Autocorrelation at this lag
            let acf = self.autocorrelation(&values, period, mean, variance);

            // Need at least 2 full cycles for confidence
            let full_cycles = n / period;
            let confidence_factor = (full_cycles as f64 / 2.0).min(1.0);

            let strength = acf * confidence_factor;

            if strength > 0.3 {
                let peak_months = if period >= 90 {
                    self.detect_peak_months(period)
                } else {
                    Vec::new()
                };

                let trough_months = if period >= 90 {
                    self.detect_trough_months(period)
                } else {
                    Vec::new()
                };

                detected.push(PeriodCandidate {
                    cycle_length_days: period as u32,
                    strength,
                    phase: self.current_phase(period),
                    peak_months,
                    trough_months,
                });
            }
        }

        // Sort by strength
        detected.sort_by(|a, b| {
            b.strength
                .partial_cmp(&a.strength)
                .unwrap_or(std::cmp::Ordering::Equal)
        });

        self.detected_periods = detected.clone();

        if detected.is_empty() {
            None
        } else {
            let strongest = &detected[0];
            Some(SeasonalityResult {
                is_seasonal: strongest.strength > 0.4,
                primary_period: strongest.clone(),
                all_periods: detected,
                monthly_profile: self.monthly_income_profile(),
            })
        }
    }

    /// Autocorrelation at a given lag
    fn autocorrelation(&self, values: &[f64], lag: usize, mean: f64, variance: f64) -> f64 {
        let n = values.len();
        if lag >= n || variance < 1e-10 {
            return 0.0;
        }

        let mut sum = 0.0;
        let count = n - lag;
        for i in 0..count {
            sum += (values[i] - mean) * (values[i + lag] - mean);
        }

        (sum / (count as f64 * variance)).abs()
    }

    /// Detect which months have peak income (for annual patterns)
    fn detect_peak_months(&self, cycle_length: usize) -> Vec<u32> {
        let mut monthly_totals: [f64; 12] = [0.0; 12];
        let mut monthly_counts: [u32; 12] = [0; 12];

        for (date, &income) in &self.daily_income {
            let month = date.month() as usize - 1; // 0-indexed
            monthly_totals[month] += income;
            monthly_counts[month] += 1;
        }

        let monthly_avgs: Vec<f64> = (0..12)
            .map(|i| {
                if monthly_counts[i] > 0 {
                    monthly_totals[i] / monthly_counts[i] as f64
                } else {
                    0.0
                }
            })
            .collect();

        let overall_avg: f64 = monthly_avgs.iter().sum::<f64>() / 12.0;

        // Peak months: >120% of average
        (0..12)
            .filter(|&i| monthly_avgs[i] > overall_avg * 1.2 && monthly_counts[i] > 0)
            .map(|i| (i + 1) as u32) // back to 1-indexed
            .collect()
    }

    /// Detect which months have trough income
    fn detect_trough_months(&self, cycle_length: usize) -> Vec<u32> {
        let mut monthly_totals: [f64; 12] = [0.0; 12];
        let mut monthly_counts: [u32; 12] = [0; 12];

        for (date, &income) in &self.daily_income {
            let month = date.month() as usize - 1;
            monthly_totals[month] += income;
            monthly_counts[month] += 1;
        }

        let monthly_avgs: Vec<f64> = (0..12)
            .map(|i| {
                if monthly_counts[i] > 0 {
                    monthly_totals[i] / monthly_counts[i] as f64
                } else {
                    0.0
                }
            })
            .collect();

        let overall_avg: f64 = monthly_avgs.iter().sum::<f64>() / 12.0;

        (0..12)
            .filter(|&i| monthly_avgs[i] < overall_avg * 0.8 && monthly_counts[i] > 0)
            .map(|i| (i + 1) as u32)
            .collect()
    }

    /// Current phase within the cycle (0.0 to 1.0)
    fn current_phase(&self, cycle_length: usize) -> f64 {
        let n = self.daily_income.len();
        (n % cycle_length) as f64 / cycle_length as f64
    }

    /// Monthly income profile (average income per month)
    fn monthly_income_profile(&self) -> [f64; 12] {
        let mut totals: [f64; 12] = [0.0; 12];
        let mut counts: [u32; 12] = [0; 12];

        for (date, &income) in &self.daily_income {
            let month = date.month() as usize - 1;
            totals[month] += income;
            counts[month] += 1;
        }

        let mut profile = [0.0; 12];
        for i in 0..12 {
            if counts[i] > 0 {
                profile[i] = totals[i] / counts[i] as f64;
            }
        }
        profile
    }
}

/// Result of seasonality detection
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SeasonalityResult {
    pub is_seasonal: bool,
    pub primary_period: PeriodCandidate,
    pub all_periods: Vec<PeriodCandidate>,
    /// Average income per month (0-11 indexed)
    pub monthly_profile: [f64; 12],
}

/// Seasonal baseline — compares current income to same-period historical,
/// NOT to overall average. This prevents penalizing seasonal workers.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SeasonalBaseline {
    /// Monthly income averages (indexed 0-11)
    pub monthly_baselines: [f64; 12],
    /// Weekly income averages (indexed 0-6, Monday=0)
    pub weekly_baselines: [f64; 7],
    /// Whether this worker has detected seasonal patterns
    pub is_seasonal: bool,
    /// Seasonality strength (0.0 = flat, 1.0 = highly seasonal)
    pub seasonality_strength: f64,
    /// Peak months (1-indexed)
    pub peak_months: Vec<u32>,
    /// Trough months (1-indexed)
    pub trough_months: Vec<u32>,
}

impl SeasonalBaseline {
    /// Build from seasonality detection result
    pub fn from_detection(result: &SeasonalityResult) -> Self {
        Self {
            monthly_baselines: result.monthly_profile,
            weekly_baselines: [0.0; 7], // computed separately if needed
            is_seasonal: result.is_seasonal,
            seasonality_strength: result.primary_period.strength,
            peak_months: result.primary_period.peak_months.clone(),
            trough_months: result.primary_period.trough_months.clone(),
        }
    }

    /// Seasonality-adjusted income stability.
    /// Instead of coefficient of variation (which penalizes seasonality),
    /// compute how well income matches the seasonal pattern.
    ///
    /// For a farmer: "Is this month's income close to what this month usually looks like?"
    /// NOT: "Is this month's income close to the year-round average?"
    pub fn adjusted_stability(&self, monthly_incomes: &[f64; 12]) -> f64 {
        if !self.is_seasonal {
            // Non-seasonal workers: use coefficient of variation (inverted)
            let mean: f64 = monthly_incomes.iter().sum::<f64>() / 12.0;
            if mean < 1e-10 {
                return 0.0;
            }
            let variance: f64 = monthly_incomes
                .iter()
                .map(|v| (v - mean).powi(2))
                .sum::<f64>()
                / 12.0;
            let cv = variance.sqrt() / mean;
            return (1.0 - cv.min(1.0)).max(0.0);
        }

        // Seasonal workers: compare each month to its historical baseline
        let deviations: Vec<f64> = monthly_incomes
            .iter()
            .enumerate()
            .map(|(i, &income)| {
                let baseline = self.monthly_baselines[i];
                if baseline > 0.0 {
                    ((income - baseline) / baseline).abs()
                } else if income > 0.0 {
                    1.0 // no baseline but has income — full deviation
                } else {
                    0.0 // no baseline, no income — no deviation
                }
            })
            .collect();

        let mean_deviation = deviations.iter().sum::<f64>() / deviations.len() as f64;
        (1.0 - mean_deviation).max(0.0)
    }

    /// Check if current month's income is "on track" compared to historical
    pub fn is_on_track(&self, current_month: usize, current_income: f64) -> bool {
        if current_month >= 12 {
            return false;
        }
        let baseline = self.monthly_baselines[current_month];
        if baseline < 1e-10 {
            return current_income < 1e-10; // both zero = on track
        }
        // Within 40% of historical baseline = on track
        (current_income - baseline).abs() / baseline < 0.4
    }

    /// Year-over-year growth rate
    pub fn yoy_growth(
        &self,
        current_year: &[f64; 12],
        previous_year: &[f64; 12],
    ) -> IncomeTrajectory {
        let mut monthly_growth = [0.0; 12];
        let mut valid_months = 0;
        let mut total_growth = 0.0;

        for i in 0..12 {
            if previous_year[i] > 0.0 {
                monthly_growth[i] = (current_year[i] - previous_year[i]) / previous_year[i];
                total_growth += monthly_growth[i];
                valid_months += 1;
            }
        }

        let annual_growth = if valid_months > 0 {
            total_growth / valid_months as f64
        } else {
            0.0
        };

        let trajectory = if valid_months < 3 {
            TrajectoryType::Insufficient
        } else if annual_growth > 0.1 {
            TrajectoryType::Growing
        } else if annual_growth < -0.1 {
            TrajectoryType::Declining
        } else {
            let volatility: f64 = monthly_growth
                .iter()
                .filter(|v| **v != 0.0)
                .map(|v| (*v - annual_growth).powi(2))
                .sum::<f64>()
                / valid_months.max(1) as f64;
            if volatility.sqrt() > 0.3 {
                TrajectoryType::Volatile
            } else {
                TrajectoryType::Stable
            }
        };

        IncomeTrajectory {
            yoy_monthly_growth: monthly_growth,
            annual_growth_rate: annual_growth,
            trajectory,
        }
    }
}

/// Income trajectory analysis
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IncomeTrajectory {
    pub yoy_monthly_growth: [f64; 12],
    pub annual_growth_rate: f64,
    pub trajectory: TrajectoryType,
}

use crate::credit::seasonality_enhanced::TrajectoryType;

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::NaiveDate;

    #[test]
    fn test_detect_weekly_pattern() {
        let mut detector = SeasonalityDetector::new();
        let start = NaiveDate::from_ymd_opt(2025, 1, 1).unwrap();

        // Create weekly pattern: high on weekdays, low on weekends
        for i in 0..56 {
            let date = start + chrono::Duration::days(i);
            let weekday = date.weekday().num_days_from_monday();
            let income = if weekday < 5 { 1000.0 } else { 200.0 };
            detector.record_day(date, income);
        }

        let result = detector.detect();
        assert!(result.is_some());
        let result = result.unwrap();
        assert!(result.is_seasonal);
        assert!(result.primary_period.cycle_length_days == 7);
        assert!(result.primary_period.strength > 0.3);
    }

    #[test]
    fn test_seasonal_baseline_adjustment() {
        // Simulate farmer: high income in months 3-5 (harvest), low rest of year
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

        // Current year follows same pattern (on-track farmer)
        let current = [
            110.0, 90.0, 520.0, 780.0, 610.0, 190.0, 105.0, 95.0, 110.0, 95.0, 210.0, 310.0,
        ];
        let stability = baseline.adjusted_stability(&current);
        assert!(
            stability > 0.7,
            "On-track seasonal farmer should have high stability, got {}",
            stability
        );

        // Non-seasonal worker with same income variation would score worse
        let non_seasonal = SeasonalBaseline {
            monthly_baselines: [0.0; 12],
            weekly_baselines: [0.0; 7],
            is_seasonal: false,
            seasonality_strength: 0.0,
            peak_months: vec![],
            trough_months: vec![],
        };
        let non_seasonal_stability = non_seasonal.adjusted_stability(&current);
        assert!(
            stability > non_seasonal_stability,
            "Seasonal adjustment should give higher stability to on-track seasonal workers"
        );
    }

    #[test]
    fn test_is_on_track() {
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

        // Month 3 (March) baseline is 500 — income of 550 is on track
        assert!(baseline.is_on_track(2, 550.0));
        // Income of 200 in March is NOT on track
        assert!(!baseline.is_on_track(2, 200.0));
    }

    #[test]
    fn test_constant_income_no_seasonality() {
        let mut detector = SeasonalityDetector::new();
        let start = NaiveDate::from_ymd_opt(2025, 1, 1).unwrap();
        for i in 0..365 {
            detector.record_day(start + chrono::Duration::days(i), 1000.0);
        }
        let result = detector.detect();
        assert!(
            result.is_none(),
            "Constant income should not be detected as seasonal"
        );
    }
}
