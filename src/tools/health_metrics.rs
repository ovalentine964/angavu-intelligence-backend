use serde::{Deserialize, Serialize};
use anyhow::Result;

#[derive(Debug, Serialize, Deserialize)]
pub struct HealthMetrics {
    pub worker_id: String,
    pub income_stability: f64,
    pub work_hours_avg: f64,
    pub insurance_eligible: bool,
    pub risk_score: f64,
}

impl HealthMetrics {
    pub fn new() -> Self {
        Self { worker_id: String::new(), income_stability: 0.0, work_hours_avg: 0.0, insurance_eligible: false, risk_score: 0.0 }
    }

    pub fn calculate(&self, daily_incomes: &[f64], work_hours: &[f64]) -> HealthMetrics {
        let avg_income = if daily_incomes.is_empty() { 0.0 } else { daily_incomes.iter().sum::<f64>() / daily_incomes.len() as f64 };
        let std_dev = if daily_incomes.len() < 2 { 0.0 } else {
            let mean = avg_income;
            (daily_incomes.iter().map(|x| (x - mean).powi(2)).sum::<f64>() / (daily_incomes.len() - 1) as f64).sqrt()
        };
        let stability = if avg_income > 0.0 { 1.0 - (std_dev / avg_income).min(1.0) } else { 0.0 };
        let avg_hours = if work_hours.is_empty() { 0.0 } else { work_hours.iter().sum::<f64>() / work_hours.len() as f64 };
        HealthMetrics {
            worker_id: self.worker_id.clone(),
            income_stability: stability,
            work_hours_avg: avg_hours,
            insurance_eligible: stability > 0.6 && avg_income > 500.0,
            risk_score: 1.0 - stability,
        }
    }
}
