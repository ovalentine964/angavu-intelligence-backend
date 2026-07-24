use serde::{Deserialize, Serialize};
use anyhow::Result;

#[derive(Debug, Serialize, Deserialize)]
pub enum ReportType {
    Daily,
    Weekly,
    Monthly,
    Credit,
    Custom,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct Report {
    pub report_type: ReportType,
    pub title: String,
    pub content: String,
    pub format: String,
    pub generated_at: String,
}

pub struct ReportEngine;

impl ReportEngine {
    pub fn new() -> Self { Self }

    pub fn generate_daily(&self, revenue: f64, expenses: f64, profit: f64, top_products: &[String]) -> Report {
        let content = format!(
            "📊 Msaidizi CFO — Daily Report\n━━━━━━━━━━━━━━━━\n💰 Revenue: KES {:,.0}\n📉 Expenses: KES {:,.0}\n✅ Profit: KES {:,.0}\n🏆 Top: {}\n━━━━━━━━━━━━━━━━",
            revenue, expenses, profit, top_products.join(", ")
        );
        Report {
            report_type: ReportType::Daily,
            title: "Daily Business Report".to_string(),
            content,
            format: "text".to_string(),
            generated_at: chrono::Utc::now().to_rfc3339(),
        }
    }

    pub fn generate_weekly(&self, total_revenue: f64, total_expenses: f64, total_profit: f64, best_day: &str) -> Report {
        let content = format!(
            "📊 Msaidizi CFO — Weekly Report\n━━━━━━━━━━━━━━━━\n💰 Total Revenue: KES {:,.0}\n📉 Total Expenses: KES {:,.0}\n✅ Total Profit: KES {:,.0}\n🏆 Best Day: {}\n━━━━━━━━━━━━━━━━",
            total_revenue, total_expenses, total_profit, best_day
        );
        Report {
            report_type: ReportType::Weekly,
            title: "Weekly Business Report".to_string(),
            content,
            format: "text".to_string(),
            generated_at: chrono::Utc::now().to_rfc3339(),
        }
    }

    pub fn generate_credit(&self, score: u32, factors: &[String]) -> Report {
        let content = format!(
            "🏦 Alama Score Report\n━━━━━━━━━━━━━━━━\nScore: {}/850\nFactors:\n{}\n━━━━━━━━━━━━━━━━",
            score,
            factors.iter().map(|f| format!("• {}", f)).collect::<Vec<_>>().join("\n")
        );
        Report {
            report_type: ReportType::Credit,
            title: "Credit Score Report".to_string(),
            content,
            format: "text".to_string(),
            generated_at: chrono::Utc::now().to_rfc3339(),
        }
    }
}
