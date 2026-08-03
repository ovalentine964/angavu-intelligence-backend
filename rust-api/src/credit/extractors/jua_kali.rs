// Credit Scoring — Jua Kali Artisan Feature Extractor

use super::{Transaction, TransactionCategory, WorkerContext, WorkerTypeFeatureExtractor};
use crate::credit::types::{AssetValueBucket, SkillType, TypeFeatures, WorkerType};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct JuaKaliFeatures {
    pub skill_type: SkillType,
    pub equipment_investment_bucket: AssetValueBucket,
    pub client_repeat_rate: f64,
    pub project_completion_signal: f64,
    pub income_irregularity_cv: f64,
    pub material_cost_ratio: f64,
    pub avg_project_value: f64,
    pub geographic_reach: u8,
    pub inter_project_savings_rate: f64,
    pub years_active: f64,
}

pub struct JuaKaliFeatureExtractor;

impl JuaKaliFeatureExtractor {
    pub fn new() -> Self {
        Self
    }

    fn detect_skill(&self, transactions: &[Transaction]) -> SkillType {
        let mut skill_scores: std::collections::HashMap<&str, u32> =
            std::collections::HashMap::new();
        for tx in transactions {
            if let Some(ref product) = tx.product {
                let l = product.to_lowercase();
                if l.contains("weld") || l.contains("metal") || l.contains("chuma") {
                    *skill_scores.entry("welding").or_insert(0) += 1;
                }
                if l.contains("wood") || l.contains("furniture") || l.contains("mbao") {
                    *skill_scores.entry("carpentry").or_insert(0) += 1;
                }
                if l.contains("sew") || l.contains("cloth") || l.contains("shona") {
                    *skill_scores.entry("tailoring").or_insert(0) += 1;
                }
                if l.contains("motor") || l.contains("engine") || l.contains("gari") {
                    *skill_scores.entry("mechanics").or_insert(0) += 1;
                }
                if l.contains("pipe") || l.contains("plumb") {
                    *skill_scores.entry("plumbing").or_insert(0) += 1;
                }
                if l.contains("electric") || l.contains("wire") || l.contains("strom") {
                    *skill_scores.entry("electrical").or_insert(0) += 1;
                }
                if l.contains("cement") || l.contains("brick") || l.contains("tofali") {
                    *skill_scores.entry("masonry").or_insert(0) += 1;
                }
                if l.contains("paint") || l.contains("rang") {
                    *skill_scores.entry("painting").or_insert(0) += 1;
                }
            }
        }
        match skill_scores.iter().max_by_key(|(_, &v)| v) {
            Some((&"welding", _)) => SkillType::Welding,
            Some((&"carpentry", _)) => SkillType::Carpentry,
            Some((&"tailoring", _)) => SkillType::Tailoring,
            Some((&"mechanics", _)) => SkillType::Mechanics,
            Some((&"plumbing", _)) => SkillType::Plumbing,
            Some((&"electrical", _)) => SkillType::Electrical,
            Some((&"masonry", _)) => SkillType::Masonry,
            Some((&"painting", _)) => SkillType::Painting,
            _ => SkillType::Other,
        }
    }

    fn client_repeat_rate(&self, transactions: &[Transaction]) -> f64 {
        let mut client_counts: std::collections::HashMap<String, u32> =
            std::collections::HashMap::new();
        for tx in transactions {
            if tx.category == TransactionCategory::Sale {
                if let Some(ref cp) = tx.counterparty_id {
                    *client_counts.entry(cp.clone()).or_insert(0) += 1;
                }
            }
        }
        if client_counts.is_empty() {
            return 0.0;
        }
        let repeat = client_counts.values().filter(|&&c| c > 1).count();
        repeat as f64 / client_counts.len() as f64
    }

    fn material_cost_ratio(&self, transactions: &[Transaction]) -> f64 {
        let revenue: f64 = transactions
            .iter()
            .filter(|tx| tx.category == TransactionCategory::Sale)
            .map(|tx| tx.amount)
            .sum();
        let materials: f64 = transactions
            .iter()
            .filter(|tx| tx.category == TransactionCategory::Purchase)
            .map(|tx| tx.amount)
            .sum();
        if revenue > 0.0 {
            (materials / revenue).min(1.0)
        } else {
            0.0
        }
    }

    fn inter_project_savings(&self, transactions: &[Transaction]) -> f64 {
        let income: f64 = transactions
            .iter()
            .filter(|tx| tx.category == TransactionCategory::Sale)
            .map(|tx| tx.amount)
            .sum();
        let savings: f64 = transactions
            .iter()
            .filter(|tx| tx.category == TransactionCategory::Savings)
            .map(|tx| tx.amount)
            .sum();
        if income > 0.0 {
            (savings / income).min(1.0)
        } else {
            0.0
        }
    }
}

impl WorkerTypeFeatureExtractor for JuaKaliFeatureExtractor {
    fn extract(&self, transactions: &[Transaction], ctx: &WorkerContext) -> TypeFeatures {
        let skill = self.detect_skill(transactions);
        let repeat = self.client_repeat_rate(transactions);
        let material_ratio = self.material_cost_ratio(transactions);
        let savings = self.inter_project_savings(transactions);
        let years = ctx.first_transaction_days_ago as f64 / 365.0;
        let avg_project = {
            let sales: Vec<f64> = transactions
                .iter()
                .filter(|tx| tx.category == TransactionCategory::Sale)
                .map(|tx| tx.amount)
                .collect();
            if sales.is_empty() {
                0.0
            } else {
                sales.iter().sum::<f64>() / sales.len() as f64
            }
        };
        let cv = {
            let sales: Vec<f64> = transactions
                .iter()
                .filter(|tx| tx.category == TransactionCategory::Sale)
                .map(|tx| tx.amount)
                .collect();
            if sales.len() < 2 {
                0.0
            } else {
                let mean = sales.iter().sum::<f64>() / sales.len() as f64;
                if mean < 1.0 {
                    0.0
                } else {
                    let var =
                        sales.iter().map(|s| (s - mean).powi(2)).sum::<f64>() / sales.len() as f64;
                    var.sqrt() / mean
                }
            }
        };
        let locations: u8 = transactions
            .iter()
            .filter_map(|tx| tx.location.clone())
            .collect::<std::collections::HashSet<_>>()
            .len() as u8;

        let features = JuaKaliFeatures {
            skill_type: skill,
            equipment_investment_bucket: AssetValueBucket::Medium,
            client_repeat_rate: repeat,
            project_completion_signal: 0.7,
            income_irregularity_cv: cv,
            material_cost_ratio: material_ratio,
            avg_project_value: avg_project,
            geographic_reach: locations,
            inter_project_savings_rate: savings,
            years_active: years,
        };

        let fv = vec![
            skill.normalize(),
            0.5,
            repeat,
            0.7,
            1.0 - cv.min(1.0),
            material_ratio,
            (avg_project / 50_000.0).min(1.0),
            (locations as f64 / 5.0).min(1.0),
            savings,
            (years / 10.0).min(1.0),
        ];

        TypeFeatures::from_features(
            WorkerType::JuaKaliArtisan,
            &features,
            fv,
            self.feature_names(),
        )
    }

    fn worker_type(&self) -> WorkerType {
        WorkerType::JuaKaliArtisan
    }
    fn min_transactions(&self) -> usize {
        20
    }
    fn feature_names(&self) -> Vec<&'static str> {
        vec![
            "skill_type",
            "equipment_value",
            "client_repeat_rate",
            "completion_signal",
            "income_stability",
            "material_cost_ratio",
            "avg_project_value",
            "geographic_reach",
            "savings_rate",
            "years_active",
        ]
    }
}
