// =============================================================================
// Angavu Intelligence — Inequality Tracker
// Computes Gini coefficient, Palma ratio, and Theil index from transaction data.
//
// Addresses B8 P1 gap: InequalityTracker
// - Gini coefficient: Standard measure of income inequality (0=perfect equality, 1=perfect inequality)
// - Palma ratio: Top 10% / Bottom 40% income share (more sensitive to extremes)
// - Theil index: Decomposable entropy-based measure (can decompose by worker type, region)
//
// All computations use k-anonymity-protected cohort data to prevent
// individual income inference.
// =============================================================================

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Income distribution snapshot for a cohort
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IncomeDistribution {
    /// Sorted incomes (ascending) — each entry is a cohort-averaged income
    pub sorted_incomes: Vec<f64>,
    /// Total population weight
    pub total_weight: f64,
    /// Region identifier
    pub region: String,
    /// Time period (e.g., "2026-08")
    pub period: String,
    /// Number of underlying individuals (for k-anonymity)
    pub individual_count: u64,
}

/// Inequality metrics computed from an income distribution
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InequalityMetrics {
    /// Gini coefficient (0.0 = perfect equality, 1.0 = perfect inequality)
    pub gini: f64,
    /// Palma ratio: top 10% share / bottom 40% share
    pub palma_ratio: f64,
    /// Theil index (GE(1) — entropy-based, decomposable)
    pub theil_index: f64,
    /// Theil L (GE(0) — mean log deviation, more sensitive to bottom)
    pub theil_l: f64,
    /// Top 10% income share
    pub top_10_share: f64,
    /// Bottom 40% income share
    pub bottom_40_share: f64,
    /// Median income
    pub median_income: f64,
    /// Mean income
    pub mean_income: f64,
    /// D9/D1 ratio (90th percentile / 10th percentile)
    pub d9_d1_ratio: f64,
    /// Number of income brackets used
    pub brackets: usize,
    /// Region
    pub region: String,
    /// Period
    pub period: String,
}

/// Decomposition of Theil index by subgroup
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TheilDecomposition {
    /// Total Theil index
    pub total_theil: f64,
    /// Within-group inequality component
    pub within_group: f64,
    /// Between-group inequality component
    pub between_group: f64,
    /// Per-group contributions
    pub group_contributions: Vec<GroupContribution>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GroupContribution {
    pub group_name: String,
    pub group_theil: f64,
    pub population_share: f64,
    pub income_share: f64,
    pub contribution_to_total: f64,
}

/// Inequality Tracker — computes inequality metrics from transaction distributions
pub struct InequalityTracker {
    /// Historical metrics by region
    history: HashMap<String, Vec<InequalityMetrics>>,
    /// Maximum history entries per region
    max_history: usize,
}

impl InequalityTracker {
    pub fn new() -> Self {
        Self {
            history: HashMap::new(),
            max_history: 365, // ~1 year of daily snapshots
        }
    }

    /// Compute Gini coefficient from a sorted income distribution.
    ///
    /// Formula: G = (2 * Σ(i * y_i)) / (n * Σ(y_i)) - (n+1)/n
    /// where y_i is the i-th income (sorted ascending) and n is population size.
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

    /// Compute Palma ratio: income share of top 10% / income share of bottom 40%.
    ///
    /// The Palma ratio is more sensitive to changes at the extremes of the
    /// distribution than the Gini coefficient (Cobham & Sumner, 2013).
    pub fn compute_palma(sorted_incomes: &[f64]) -> f64 {
        let n = sorted_incomes.len();
        if n < 10 {
            return 0.0;
        }

        let total: f64 = sorted_incomes.iter().sum();
        if total <= 0.0 {
            return 0.0;
        }

        let bottom_40_end = (n as f64 * 0.4).ceil() as usize;
        let top_10_start = (n as f64 * 0.9).floor() as usize;

        let bottom_40_share: f64 = sorted_incomes[..bottom_40_end].iter().sum::<f64>() / total;
        let top_10_share: f64 = sorted_incomes[top_10_start..].iter().sum::<f64>() / total;

        if bottom_40_share > 0.0 {
            top_10_share / bottom_40_share
        } else {
            f64::INFINITY
        }
    }

    /// Compute Theil index (GE(1)): T = (1/n) * Σ(y_i/μ * ln(y_i/μ))
    ///
    /// The Theil index is decomposable: total inequality = within-group + between-group.
    /// GE(1) is more sensitive to top of distribution.
    pub fn compute_theil(sorted_incomes: &[f64]) -> f64 {
        let n = sorted_incomes.len();
        if n == 0 {
            return 0.0;
        }

        let mean: f64 = sorted_incomes.iter().sum::<f64>() / n as f64;
        if mean <= 0.0 {
            return 0.0;
        }

        sorted_incomes
            .iter()
            .filter(|&&y| y > 0.0)
            .map(|&y| {
                let ratio = y / mean;
                ratio * ratio.ln()
            })
            .sum::<f64>()
            / n as f64
    }

    /// Compute Theil L (GE(0)): L = (1/n) * Σ(ln(μ/y_i))
    ///
    /// Also known as mean log deviation. More sensitive to bottom of distribution.
    pub fn compute_theil_l(sorted_incomes: &[f64]) -> f64 {
        let n = sorted_incomes.len();
        if n == 0 {
            return 0.0;
        }

        let mean: f64 = sorted_incomes.iter().sum::<f64>() / n as f64;
        if mean <= 0.0 {
            return 0.0;
        }

        sorted_incomes
            .iter()
            .filter(|&&y| y > 0.0)
            .map(|&y| (mean / y).ln())
            .sum::<f64>()
            / n as f64
    }

    /// Decompose Theil index by worker type or region groups.
    ///
    /// T_total = T_within + T_between
    /// where T_within = Σ(s_j * T_j) and T_between = Σ(s_j * ln(μ_j/μ))
    pub fn decompose_theil(
        sorted_incomes: &[f64],
        groups: &HashMap<String, Vec<f64>>,
    ) -> TheilDecomposition {
        let total_theil = Self::compute_theil(sorted_incomes);
        let total_mean: f64 = if !sorted_incomes.is_empty() {
            sorted_incomes.iter().sum::<f64>() / sorted_incomes.len() as f64
        } else {
            return TheilDecomposition {
                total_theil: 0.0,
                within_group: 0.0,
                between_group: 0.0,
                group_contributions: Vec::new(),
            };
        };

        let total_n = sorted_incomes.len() as f64;
        let mut within = 0.0;
        let mut between = 0.0;
        let mut contributions = Vec::new();

        for (name, group_incomes) in groups {
            let n_j = group_incomes.len() as f64;
            if n_j == 0.0 || total_n == 0.0 {
                continue;
            }

            let pop_share = n_j / total_n;
            let mean_j: f64 = group_incomes.iter().sum::<f64>() / n_j;
            let income_share = if total_mean > 0.0 && total_n > 0.0 {
                (mean_j * n_j) / (total_mean * total_n)
            } else {
                0.0
            };

            let group_theil = Self::compute_theil(group_incomes);
            within += income_share * group_theil;
            if mean_j > 0.0 && total_mean > 0.0 {
                between += income_share * (mean_j / total_mean).ln();
            }

            contributions.push(GroupContribution {
                group_name: name.clone(),
                group_theil,
                population_share: pop_share,
                income_share,
                contribution_to_total: income_share * group_theil,
            });
        }

        contributions.sort_by(|a, b| {
            b.contribution_to_total
                .partial_cmp(&a.contribution_to_total)
                .unwrap_or(std::cmp::Ordering::Equal)
        });

        TheilDecomposition {
            total_theil,
            within_group: within,
            between_group: between,
            group_contributions: contributions,
        }
    }

    /// Compute all inequality metrics for a distribution
    pub fn compute_all_metrics(dist: &IncomeDistribution) -> InequalityMetrics {
        let sorted = &dist.sorted_incomes;
        let n = sorted.len();

        let mean = if n > 0 {
            sorted.iter().sum::<f64>() / n as f64
        } else {
            0.0
        };

        let median = if n > 0 {
            if n % 2 == 0 {
                (sorted[n / 2 - 1] + sorted[n / 2]) / 2.0
            } else {
                sorted[n / 2]
            }
        } else {
            0.0
        };

        let d9_d1 = if n >= 10 {
            let p10 = sorted[(n as f64 * 0.1).floor() as usize];
            let p90 = sorted[(n as f64 * 0.9).floor() as usize];
            if p10 > 0.0 { p90 / p10 } else { 0.0 }
        } else {
            0.0
        };

        let total: f64 = sorted.iter().sum();
        let top_10_start = (n as f64 * 0.9).floor() as usize;
        let bottom_40_end = (n as f64 * 0.4).ceil() as usize;
        let top_10_share = if total > 0.0 {
            sorted[top_10_start..].iter().sum::<f64>() / total
        } else {
            0.0
        };
        let bottom_40_share = if total > 0.0 {
            sorted[..bottom_40_end].iter().sum::<f64>() / total
        } else {
            0.0
        };

        InequalityMetrics {
            gini: Self::compute_gini(sorted),
            palma_ratio: Self::compute_palma(sorted),
            theil_index: Self::compute_theil(sorted),
            theil_l: Self::compute_theil_l(sorted),
            top_10_share,
            bottom_40_share,
            median_income: median,
            mean_income: mean,
            d9_d1_ratio: d9_d1,
            brackets: n,
            region: dist.region.clone(),
            period: dist.period.clone(),
        }
    }

    /// Record metrics in history
    pub fn record(&mut self, metrics: InequalityMetrics) {
        let entry = self
            .history
            .entry(metrics.region.clone())
            .or_insert_with(Vec::new);
        entry.push(metrics);
        if entry.len() > self.max_history {
            entry.drain(0..entry.len() - self.max_history);
        }
    }

    /// Get trend analysis for a region
    pub fn trend(&self, region: &str) -> Option<InequalityTrend> {
        let history = self.history.get(region)?;
        if history.len() < 2 {
            return None;
        }

        let recent = history.last()?;
        let previous = &history[history.len() - 2];

        Some(InequalityTrend {
            region: region.to_string(),
            gini_change: recent.gini - previous.gini,
            palma_change: recent.palma_ratio - previous.palma_ratio,
            theil_change: recent.theil_index - previous.theil_index,
            direction: if recent.gini > previous.gini + 0.01 {
                TrendDirection::Increasing
            } else if recent.gini < previous.gini - 0.01 {
                TrendDirection::Decreasing
            } else {
                TrendDirection::Stable
            },
        })
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InequalityTrend {
    pub region: String,
    pub gini_change: f64,
    pub palma_change: f64,
    pub theil_change: f64,
    pub direction: TrendDirection,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum TrendDirection {
    Increasing,
    Decreasing,
    Stable,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_gini_perfect_equality() {
        let incomes = vec![100.0, 100.0, 100.0, 100.0];
        let gini = InequalityTracker::compute_gini(&incomes);
        assert!((gini - 0.0).abs() < 1e-10, "Gini should be 0 for equal incomes, got {}", gini);
    }

    #[test]
    fn test_gini_inequality() {
        let incomes = vec![10.0, 20.0, 30.0, 100.0, 500.0];
        let gini = InequalityTracker::compute_gini(&incomes);
        assert!(gini > 0.3 && gini < 0.7, "Gini should be moderate, got {}", gini);
    }

    #[test]
    fn test_palma_ratio() {
        // Bottom 40% = [10, 20] = 30, share = 30/660
        // Top 10% = [500], share = 500/660
        let incomes = vec![10.0, 20.0, 30.0, 100.0, 500.0];
        let palma = InequalityTracker::compute_palma(&incomes);
        assert!(palma > 1.0, "Palma should be > 1 for unequal distribution, got {}", palma);
    }

    #[test]
    fn test_theil_zero_for_equal() {
        let incomes = vec![50.0, 50.0, 50.0, 50.0];
        let theil = InequalityTracker::compute_theil(&incomes);
        assert!((theil - 0.0).abs() < 1e-10, "Theil should be 0 for equal incomes, got {}", theil);
    }

    #[test]
    fn test_theil_decomposition() {
        let all = vec![10.0, 20.0, 30.0, 40.0, 100.0, 200.0];
        let mut groups = HashMap::new();
        groups.insert("low".to_string(), vec![10.0, 20.0, 30.0, 40.0]);
        groups.insert("high".to_string(), vec![100.0, 200.0]);

        let decomp = InequalityTracker::decompose_theil(&all, &groups);
        // within + between should approximately equal total
        let reconstructed = decomp.within_group + decomp.between_group;
        assert!(
            (decomp.total_theil - reconstructed).abs() < 0.01,
            "Within + Between should ≈ Total: {} vs {}",
            decomp.total_theil,
            reconstructed
        );
    }

    #[test]
    fn test_full_metrics() {
        let dist = IncomeDistribution {
            sorted_incomes: vec![500.0, 1000.0, 1500.0, 2000.0, 5000.0, 10000.0, 50000.0],
            total_weight: 7.0,
            region: "nairobi".to_string(),
            period: "2026-08".to_string(),
            individual_count: 700,
        };
        let metrics = InequalityTracker::compute_all_metrics(&dist);
        assert!(metrics.gini > 0.0 && metrics.gini <= 1.0);
        assert!(metrics.theil_index >= 0.0);
        assert!(metrics.median_income > 0.0);
        assert_eq!(metrics.region, "nairobi");
    }
}
