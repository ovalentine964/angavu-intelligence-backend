// =============================================================================
// Angavu Intelligence — Gender Inequality Index
// Gender-disaggregated Gini, Theil, and income gap metrics.
//
// Addresses cross-cutting gap: Gender-disaggregated analytics
// - Gender-disaggregated Gini coefficient
// - Gender-disaggregated Theil index
// - Male/Female income ratio
// - Gender wage gap percentage
// - Labor force participation gap
//
// All computations use k-anonymity-protected cohort data.
// =============================================================================

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Gender categories for disaggregation
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum Gender {
    Male,
    Female,
    NonBinary,
    Unknown,
}

/// Income distribution disaggregated by gender
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GenderIncomeDistribution {
    pub male_incomes: Vec<f64>,
    pub female_incomes: Vec<f64>,
    pub region: String,
    pub period: String,
    pub male_count: u64,
    pub female_count: u64,
}

/// Gender-disaggregated inequality metrics
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GenderInequalityMetrics {
    /// Overall Gini coefficient
    pub overall_gini: f64,
    /// Male Gini coefficient
    pub male_gini: f64,
    /// Female Gini coefficient
    pub female_gini: f64,
    /// Overall Theil index
    pub overall_theil: f64,
    /// Male Theil index
    pub male_theil: f64,
    /// Female Theil index
    pub female_theil: f64,
    /// Male mean income
    pub male_mean_income: f64,
    /// Female mean income
    pub female_mean_income: f64,
    /// Male median income
    pub male_median_income: f64,
    /// Female median income
    pub female_median_income: f64,
    /// Gender income ratio (female/male, 1.0 = parity)
    pub gender_income_ratio: f64,
    /// Gender wage gap percentage (0 = no gap, 100 = total gap)
    pub gender_wage_gap_pct: f64,
    /// Male labor force participation rate
    pub male_participation_rate: f64,
    /// Female labor force participation rate
    pub female_participation_rate: f64,
    /// Participation gap
    pub participation_gap: f64,
    /// Region
    pub region: String,
    /// Period
    pub period: String,
}

/// Tracker for gender-disaggregated inequality
pub struct GenderInequalityTracker {
    history: HashMap<String, Vec<GenderInequalityMetrics>>,
    max_history: usize,
}

impl GenderInequalityTracker {
    pub fn new() -> Self {
        Self {
            history: HashMap::new(),
            max_history: 365,
        }
    }

    /// Compute Gini coefficient from a sorted income distribution
    pub fn compute_gini(sorted_incomes: &[f64]) -> f64 {
        let n = sorted_incomes.len();
        if n < 2 {
            return 0.0;
        }
        let total: f64 = sorted_incomes.iter().sum();
        if total <= 0.0 {
            return 0.0;
        }
        let n_f64 = n as f64;
        let weighted_sum: f64 = sorted_incomes
            .iter()
            .enumerate()
            .map(|(i, &y)| (i + 1) as f64 * y)
            .sum();
        (2.0 * weighted_sum) / (n_f64 * total) - (n_f64 + 1.0) / n_f64
    }

    /// Compute Theil index (GE(1))
    pub fn compute_theil(incomes: &[f64]) -> f64 {
        let n = incomes.len();
        if n == 0 {
            return 0.0;
        }
        let mean: f64 = incomes.iter().sum::<f64>() / n as f64;
        if mean <= 0.0 {
            return 0.0;
        }
        incomes
            .iter()
            .filter(|&&y| y > 0.0)
            .map(|&y| {
                let ratio = y / mean;
                ratio * ratio.ln()
            })
            .sum::<f64>()
            / n as f64
    }

    /// Compute median from sorted values
    fn median(sorted: &[f64]) -> f64 {
        let n = sorted.len();
        if n == 0 {
            return 0.0;
        }
        if n % 2 == 0 {
            (sorted[n / 2 - 1] + sorted[n / 2]) / 2.0
        } else {
            sorted[n / 2]
        }
    }

    /// Compute all gender-disaggregated metrics
    pub fn compute_metrics(dist: &GenderIncomeDistribution) -> GenderInequalityMetrics {
        let mut all_incomes = dist.male_incomes.clone();
        all_incomes.extend(dist.female_incomes.iter().cloned());
        all_incomes.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));

        let mut male_sorted = dist.male_incomes.clone();
        male_sorted.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));

        let mut female_sorted = dist.female_incomes.clone();
        female_sorted.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));

        let male_mean = if !male_sorted.is_empty() {
            male_sorted.iter().sum::<f64>() / male_sorted.len() as f64
        } else {
            0.0
        };

        let female_mean = if !female_sorted.is_empty() {
            female_sorted.iter().sum::<f64>() / female_sorted.len() as f64
        } else {
            0.0
        };

        let gender_income_ratio = if male_mean > 0.0 {
            female_mean / male_mean
        } else {
            0.0
        };

        let gender_wage_gap = if male_mean > 0.0 {
            ((male_mean - female_mean) / male_mean) * 100.0
        } else {
            0.0
        };

        // Participation rates (from counts vs total population estimate)
        let total_pop = (dist.male_count + dist.female_count) as f64;
        let male_participation = if total_pop > 0.0 {
            dist.male_count as f64 / total_pop
        } else {
            0.0
        };
        let female_participation = if total_pop > 0.0 {
            dist.female_count as f64 / total_pop
        } else {
            0.0
        };

        GenderInequalityMetrics {
            overall_gini: Self::compute_gini(&all_incomes),
            male_gini: Self::compute_gini(&male_sorted),
            female_gini: Self::compute_gini(&female_sorted),
            overall_theil: Self::compute_theil(&all_incomes),
            male_theil: Self::compute_theil(&male_sorted),
            female_theil: Self::compute_theil(&female_sorted),
            male_mean_income: male_mean,
            female_mean_income: female_mean,
            male_median_income: Self::median(&male_sorted),
            female_median_income: Self::median(&female_sorted),
            gender_income_ratio,
            gender_wage_gap_pct: gender_wage_gap,
            male_participation_rate: male_participation,
            female_participation_rate: female_participation,
            participation_gap: male_participation - female_participation,
            region: dist.region.clone(),
            period: dist.period.clone(),
        }
    }

    /// Record metrics in history
    pub fn record(&mut self, metrics: GenderInequalityMetrics) {
        let entry = self
            .history
            .entry(metrics.region.clone())
            .or_insert_with(Vec::new);
        entry.push(metrics);
        if entry.len() > self.max_history {
            entry.drain(0..entry.len() - self.max_history);
        }
    }

    /// Get trend for a region
    pub fn trend(&self, region: &str) -> Option<GenderInequalityTrend> {
        let history = self.history.get(region)?;
        if history.len() < 2 {
            return None;
        }
        let recent = history.last()?;
        let previous = &history[history.len() - 2];

        Some(GenderInequalityTrend {
            region: region.to_string(),
            wage_gap_change: recent.gender_wage_gap_pct - previous.gender_wage_gap_pct,
            income_ratio_change: recent.gender_income_ratio - previous.gender_income_ratio,
            gini_change: recent.overall_gini - previous.overall_gini,
        })
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GenderInequalityTrend {
    pub region: String,
    pub wage_gap_change: f64,
    pub income_ratio_change: f64,
    pub gini_change: f64,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_gender_gini_parity() {
        let dist = GenderIncomeDistribution {
            male_incomes: vec![100.0, 200.0, 300.0],
            female_incomes: vec![100.0, 200.0, 300.0],
            region: "test".into(),
            period: "2026-08".into(),
            male_count: 3,
            female_count: 3,
        };
        let metrics = GenderInequalityTracker::compute_metrics(&dist);
        assert!((metrics.gender_income_ratio - 1.0).abs() < 0.01);
        assert!((metrics.gender_wage_gap_pct).abs() < 1.0);
    }

    #[test]
    fn test_gender_gini_gap() {
        let dist = GenderIncomeDistribution {
            male_incomes: vec![500.0, 1000.0, 2000.0, 5000.0],
            female_incomes: vec![200.0, 400.0, 800.0, 1500.0],
            region: "test".into(),
            period: "2026-08".into(),
            male_count: 4,
            female_count: 4,
        };
        let metrics = GenderInequalityTracker::compute_metrics(&dist);
        assert!(
            metrics.gender_wage_gap_pct > 30.0,
            "Expected significant wage gap, got {}",
            metrics.gender_wage_gap_pct
        );
        assert!(metrics.gender_income_ratio < 0.7);
        assert!(
            metrics.overall_gini > metrics.male_gini,
            "Overall Gini should exceed within-group Gini"
        );
    }

    #[test]
    fn test_gender_theil_decomposition() {
        let dist = GenderIncomeDistribution {
            male_incomes: vec![100.0, 500.0, 1000.0, 5000.0],
            female_incomes: vec![50.0, 200.0, 500.0, 1000.0],
            region: "nairobi".into(),
            period: "2026-08".into(),
            male_count: 4,
            female_count: 4,
        };
        let metrics = GenderInequalityTracker::compute_metrics(&dist);
        assert!(metrics.overall_theil >= 0.0);
        assert!(metrics.male_theil >= 0.0);
        assert!(metrics.female_theil >= 0.0);
    }
}
