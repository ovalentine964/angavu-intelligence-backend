use serde::{Deserialize, Serialize};
use anyhow::Result;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HealthMetrics {
    pub worker_id: String,
    pub income_stability: f64,
    pub work_hours_avg: f64,
    pub insurance_eligible: bool,
    pub risk_score: f64,
    pub income_volatility: f64,
    pub coefficient_of_variation: f64,
    pub trend: IncomeTrend,
    pub percentile_rank: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum IncomeTrend {
    Growing,
    Declining,
    Stable,
    Insufficient,
}

impl HealthMetrics {
    pub fn new() -> Self {
        Self {
            worker_id: String::new(),
            income_stability: 0.0,
            work_hours_avg: 0.0,
            insurance_eligible: false,
            risk_score: 0.0,
            income_volatility: 0.0,
            coefficient_of_variation: 0.0,
            trend: IncomeTrend::Insufficient,
            percentile_rank: 0.0,
        }
    }

    /// Calculate comprehensive health metrics from income and work hour histories.
    pub fn calculate(&self, daily_incomes: &[f64], work_hours: &[f64]) -> HealthMetrics {
        let n = daily_incomes.len();
        let avg_income = if n == 0 {
            0.0
        } else {
            daily_incomes.iter().sum::<f64>() / n as f64
        };

        // Standard deviation (sample std dev)
        let std_dev = if n < 2 {
            0.0
        } else {
            let mean = avg_income;
            (daily_incomes
                .iter()
                .map(|x| (x - mean).powi(2))
                .sum::<f64>()
                / (n - 1) as f64)
                .sqrt()
        };

        // Coefficient of variation (CV): normalized volatility measure
        let cv = if avg_income > 0.0 {
            std_dev / avg_income
        } else {
            0.0
        };

        // Income stability index: 1 - min(CV, 1)
        // CV of 0 = perfect stability (1.0), CV >= 1 = very unstable (0.0)
        let stability = (1.0 - cv.min(1.0)).max(0.0);

        // Income volatility: absolute std dev as percentage of mean
        let volatility = if avg_income > 0.0 {
            (std_dev / avg_income) * 100.0
        } else {
            0.0
        };

        // Trend detection using simple linear regression on income series
        let trend = Self::detect_income_trend(daily_incomes);

        let avg_hours = if work_hours.is_empty() {
            0.0
        } else {
            work_hours.iter().sum::<f64>() / work_hours.len() as f64
        };

        // Risk score: weighted combination of factors
        // Higher CV → higher risk, lower stability → higher risk
        let risk = Self::compute_risk_score(cv, stability, &trend, avg_income);

        // Insurance eligibility: stable income above threshold + consistent work
        let eligible = stability > 0.6 && avg_income > 500.0 && avg_hours > 4.0;

        // Percentile rank among all workers (placeholder — in production this comes from DB)
        let percentile = Self::estimate_percentile(stability);

        HealthMetrics {
            worker_id: self.worker_id.clone(),
            income_stability: (stability * 100.0).round() / 100.0,
            work_hours_avg: (avg_hours * 100.0).round() / 100.0,
            insurance_eligible: eligible,
            risk_score: (risk * 100.0).round() / 100.0,
            income_volatility: (volatility * 100.0).round() / 100.0,
            coefficient_of_variation: (cv * 100.0).round() / 100.0,
            trend,
            percentile_rank: (percentile * 100.0).round() / 100.0,
        }
    }

    /// Detect income trend using linear regression slope.
    fn detect_income_trend(incomes: &[f64]) -> IncomeTrend {
        let n = incomes.len();
        if n < 5 {
            return IncomeTrend::Insufficient;
        }

        let nf = n as f64;
        let x_mean = (nf - 1.0) / 2.0;
        let y_mean = incomes.iter().sum::<f64>() / nf;

        let mut num = 0.0;
        let mut den = 0.0;
        for (i, &y) in incomes.iter().enumerate() {
            let x = i as f64;
            num += (x - x_mean) * (y - y_mean);
            den += (x - x_mean).powi(2);
        }

        if den == 0.0 {
            return IncomeTrend::Stable;
        }

        let slope = num / den;
        let threshold = y_mean.abs() * 0.03; // 3% of mean as significance threshold

        if slope > threshold {
            IncomeTrend::Growing
        } else if slope < -threshold {
            IncomeTrend::Declining
        } else {
            IncomeTrend::Stable
        }
    }

    /// Compute a composite risk score (0.0 = low risk, 1.0 = high risk).
    fn compute_risk_score(cv: f64, stability: f64, trend: &IncomeTrend, avg_income: f64) -> f64 {
        let mut risk = cv.min(1.0); // base risk from volatility

        // Adjust for trend
        match trend {
            IncomeTrend::Growing => risk *= 0.7,      // 30% discount for positive trend
            IncomeTrend::Declining => risk = (risk * 1.3).min(1.0), // 30% penalty
            IncomeTrend::Stable => {}                  // no adjustment
            IncomeTrend::Insufficient => risk = (risk + 0.2).min(1.0), // uncertainty penalty
        }

        // Low absolute income increases risk
        if avg_income < 200.0 {
            risk = (risk + 0.15).min(1.0);
        }

        (1.0 - stability).max(risk)
    }

    /// Estimate percentile rank from stability score.
    /// In production, this queries the distribution from the database.
    fn estimate_percentile(stability: f64) -> f64 {
        // Approximate: stability maps roughly to percentile
        (stability * 100.0).min(99.0).max(1.0)
    }

    /// Batch calculate metrics for multiple workers.
    pub fn calculate_batch(
        workers: &[(String, Vec<f64>, Vec<f64>)], // (worker_id, incomes, hours)
    ) -> Vec<HealthMetrics> {
        workers
            .iter()
            .map(|(id, incomes, hours)| {
                let base = HealthMetrics {
                    worker_id: id.clone(),
                    ..HealthMetrics::new()
                };
                base.calculate(incomes, hours)
            })
            .collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_stable_income() {
        let base = HealthMetrics {
            worker_id: "w1".to_string(),
            ..HealthMetrics::new()
        };
        // Very consistent income → high stability
        let incomes = vec![1000.0; 30];
        let hours = vec![8.0; 30];
        let metrics = base.calculate(&incomes, &hours);
        assert!(metrics.income_stability > 0.95, "Stability should be >0.95, got {}", metrics.income_stability);
        assert!(metrics.income_volatility < 5.0);
        assert!(metrics.insurance_eligible);
    }

    #[test]
    fn test_volatile_income() {
        let base = HealthMetrics {
            worker_id: "w2".to_string(),
            ..HealthMetrics::new()
        };
        // Wildly varying income → low stability
        let incomes = vec![100.0, 2000.0, 50.0, 1500.0, 300.0, 1800.0, 100.0];
        let hours = vec![4.0, 10.0, 2.0, 9.0, 3.0, 8.0, 2.0];
        let metrics = base.calculate(&incomes, &hours);
        assert!(metrics.income_stability < 0.7, "Stability should be <0.7, got {}", metrics.income_stability);
        assert!(metrics.risk_score > 0.3);
    }

    #[test]
    fn test_growing_trend() {
        let base = HealthMetrics {
            worker_id: "w3".to_string(),
            ..HealthMetrics::new()
        };
        let incomes = vec![500.0, 550.0, 600.0, 650.0, 700.0, 750.0, 800.0, 850.0, 900.0, 950.0];
        let hours = vec![8.0; 10];
        let metrics = base.calculate(&incomes, &hours);
        assert_eq!(metrics.trend, IncomeTrend::Growing);
    }

    #[test]
    fn test_declining_trend() {
        let base = HealthMetrics {
            worker_id: "w4".to_string(),
            ..HealthMetrics::new()
        };
        let incomes = vec![1000.0, 950.0, 900.0, 850.0, 800.0, 750.0, 700.0, 650.0, 600.0, 550.0];
        let hours = vec![8.0; 10];
        let metrics = base.calculate(&incomes, &hours);
        assert_eq!(metrics.trend, IncomeTrend::Declining);
    }

    #[test]
    fn test_insufficient_data() {
        let base = HealthMetrics {
            worker_id: "w5".to_string(),
            ..HealthMetrics::new()
        };
        let incomes = vec![100.0, 200.0];
        let hours = vec![4.0, 6.0];
        let metrics = base.calculate(&incomes, &hours);
        assert_eq!(metrics.trend, IncomeTrend::Insufficient);
    }

    #[test]
    fn test_empty_data() {
        let base = HealthMetrics::new();
        let metrics = base.calculate(&[], &[]);
        assert_eq!(metrics.income_stability, 0.0);
        assert_eq!(metrics.work_hours_avg, 0.0);
        assert!(!metrics.insurance_eligible);
    }

    #[test]
    fn test_insurance_eligibility_threshold() {
        let base = HealthMetrics {
            worker_id: "w6".to_string(),
            ..HealthMetrics::new()
        };
        // Stable income above 500 + good hours → eligible
        let incomes = vec![600.0; 20];
        let hours = vec![8.0; 20];
        let metrics = base.calculate(&incomes, &hours);
        assert!(metrics.insurance_eligible);

        // Low income → not eligible
        let low_incomes = vec![200.0; 20];
        let m2 = base.calculate(&low_incomes, &hours);
        assert!(!m2.insurance_eligible);
    }

    #[test]
    fn test_batch_calculation() {
        let workers = vec![
            ("w1".to_string(), vec![1000.0; 10], vec![8.0; 10]),
            ("w2".to_string(), vec![500.0; 10], vec![6.0; 10]),
        ];
        let results = HealthMetrics::calculate_batch(&workers);
        assert_eq!(results.len(), 2);
        assert_eq!(results[0].worker_id, "w1");
        assert_eq!(results[1].worker_id, "w2");
    }

    #[test]
    fn test_risk_score_range() {
        let base = HealthMetrics {
            worker_id: "w7".to_string(),
            ..HealthMetrics::new()
        };
        let incomes = vec![100.0, 3000.0, 50.0, 2500.0, 80.0];
        let hours = vec![2.0, 12.0, 1.0, 10.0, 2.0];
        let metrics = base.calculate(&incomes, &hours);
        assert!(metrics.risk_score >= 0.0 && metrics.risk_score <= 1.0,
            "Risk score should be 0-1, got {}", metrics.risk_score);
    }
}
