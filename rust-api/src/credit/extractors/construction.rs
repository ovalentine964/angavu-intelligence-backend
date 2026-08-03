// Credit Scoring — Construction Worker Feature Extractor

use super::{Transaction, TransactionCategory, WorkerContext, WorkerTypeFeatureExtractor};
use crate::credit::types::{SkillLevel, TypeFeatures, WorkerType};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConstructionFeatures {
    pub skill_level: SkillLevel,
    pub contractor_count: u8,
    pub project_frequency_days: u32,
    pub wage_regularity: f64,
    pub wage_trajectory: f64,
    pub geographic_mobility: u8,
    pub tool_investment: f64,
    pub weekend_work_ratio: f64,
    pub mpesa_payment_ratio: f64,
    pub relative_wage_percentile: f64,
}

pub struct ConstructionFeatureExtractor;

impl ConstructionFeatureExtractor {
    pub fn new() -> Self {
        Self
    }

    fn detect_skill_level(&self, transactions: &[Transaction]) -> SkillLevel {
        let wages: Vec<f64> = transactions
            .iter()
            .filter(|tx| {
                tx.category == TransactionCategory::Wage || tx.category == TransactionCategory::Sale
            })
            .map(|tx| tx.amount)
            .collect();
        if wages.is_empty() {
            return SkillLevel::Helper;
        }
        let avg = wages.iter().sum::<f64>() / wages.len() as f64;
        if avg > 20_000.0 {
            SkillLevel::Contractor
        } else if avg > 8_000.0 {
            SkillLevel::Supervisor
        } else if avg > 3_000.0 {
            SkillLevel::Fundi
        } else {
            SkillLevel::Helper
        }
    }

    fn contractor_count(&self, transactions: &[Transaction]) -> u8 {
        let employers: std::collections::HashSet<String> = transactions
            .iter()
            .filter(|tx| {
                matches!(
                    tx.category,
                    TransactionCategory::Wage | TransactionCategory::Sale
                )
            })
            .filter_map(|tx| tx.counterparty_id.clone())
            .collect();
        employers.len() as u8
    }

    fn wage_regularity(&self, transactions: &[Transaction]) -> f64 {
        let wages: Vec<i64> = transactions
            .iter()
            .filter(|tx| {
                tx.category == TransactionCategory::Wage || tx.category == TransactionCategory::Sale
            })
            .map(|tx| tx.timestamp / 86400)
            .collect();
        if wages.len() < 3 {
            return 0.0;
        }
        let mut sorted = wages.clone();
        sorted.sort();
        sorted.dedup();
        let gaps: Vec<f64> = sorted.windows(2).map(|w| (w[1] - w[0]) as f64).collect();
        let mean = gaps.iter().sum::<f64>() / gaps.len() as f64;
        if mean < 1.0 {
            return 0.0;
        }
        let var = gaps.iter().map(|g| (g - mean).powi(2)).sum::<f64>() / gaps.len() as f64;
        (1.0 - (var.sqrt() / mean).min(1.0)).max(0.0)
    }

    fn tool_investment(&self, transactions: &[Transaction]) -> f64 {
        transactions
            .iter()
            .filter(|tx| {
                tx.category == TransactionCategory::Expense
                    && tx.product.as_ref().map_or(false, |p| {
                        let l = p.to_lowercase();
                        l.contains("tool")
                            || l.contains("jembe")
                            || l.contains("panga")
                            || l.contains("hammer")
                            || l.contains("drill")
                    })
            })
            .map(|tx| tx.amount)
            .sum()
    }

    fn weekend_work_ratio(&self, transactions: &[Transaction]) -> f64 {
        let total = transactions.len() as f64;
        if total < 1.0 {
            return 0.0;
        }
        let weekend = transactions
            .iter()
            .filter(|tx| {
                let day = ((tx.timestamp / 86400 + 4) % 7) as u32;
                day == 0 || day == 6
            })
            .count();
        weekend as f64 / total
    }
}

impl WorkerTypeFeatureExtractor for ConstructionFeatureExtractor {
    fn extract(&self, transactions: &[Transaction], _ctx: &WorkerContext) -> TypeFeatures {
        let skill = self.detect_skill_level(transactions);
        let contractors = self.contractor_count(transactions);
        let regularity = self.wage_regularity(transactions);
        let tool_inv = self.tool_investment(transactions);
        let weekend = self.weekend_work_ratio(transactions);
        let locations: u8 = transactions
            .iter()
            .filter_map(|tx| tx.location.clone())
            .collect::<std::collections::HashSet<_>>()
            .len() as u8;
        let mpesa_ratio = {
            let total = transactions.len() as f64;
            if total < 1.0 {
                0.0
            } else {
                transactions
                    .iter()
                    .filter(|tx| tx.payment_method == super::PaymentMethod::MPesa)
                    .count() as f64
                    / total
            }
        };

        let features = ConstructionFeatures {
            skill_level: skill,
            contractor_count: contractors,
            project_frequency_days: 7,
            wage_regularity: regularity,
            wage_trajectory: 0.0,
            geographic_mobility: locations,
            tool_investment: tool_inv,
            weekend_work_ratio: weekend,
            mpesa_payment_ratio: mpesa_ratio,
            relative_wage_percentile: 0.5,
        };

        let fv = vec![
            skill.normalize(),
            (contractors as f64 / 5.0).min(1.0),
            0.5,
            regularity,
            0.5,
            (locations as f64 / 3.0).min(1.0),
            (tool_inv / 50_000.0).min(1.0),
            weekend,
            mpesa_ratio,
            0.5,
        ];

        TypeFeatures::from_features(
            WorkerType::ConstructionWorker,
            &features,
            fv,
            self.feature_names(),
        )
    }

    fn worker_type(&self) -> WorkerType {
        WorkerType::ConstructionWorker
    }
    fn min_transactions(&self) -> usize {
        30
    }
    fn feature_names(&self) -> Vec<&'static str> {
        vec![
            "skill_level",
            "contractor_count",
            "project_frequency",
            "wage_regularity",
            "wage_trajectory",
            "geographic_mobility",
            "tool_investment",
            "weekend_work",
            "mpesa_ratio",
            "wage_percentile",
        ]
    }
}
