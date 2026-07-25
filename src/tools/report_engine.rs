use serde::{Deserialize, Serialize};
use anyhow::{Result, Context};
use chrono::{Utc, DateTime, NaiveDate, Datelike};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum ReportType {
    Daily,
    Weekly,
    Monthly,
    Credit,
    Custom,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Report {
    pub report_type: ReportType,
    pub title: String,
    pub content: String,
    pub format: String,
    pub generated_at: String,
    pub metrics: ReportMetrics,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReportMetrics {
    pub revenue: f64,
    pub expenses: f64,
    pub profit: f64,
    pub profit_margin_pct: f64,
    pub revenue_trend: TrendDirection,
    pub expense_trend: TrendDirection,
    pub transaction_count: usize,
    pub avg_transaction_value: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum TrendDirection {
    Rising,
    Falling,
    Stable,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DailyRecord {
    pub date: NaiveDate,
    pub revenue: f64,
    pub expenses: f64,
    pub transaction_count: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CreditFactors {
    pub payment_history_score: f64,
    pub income_stability_score: f64,
    pub debt_ratio: f64,
    pub account_age_months: u32,
    pub defaults: u32,
}

pub struct ReportEngine;

impl ReportEngine {
    pub fn new() -> Self { Self }

    /// Detect trend direction from a sequence of values.
    /// Uses simple linear regression slope with thresholds.
    pub fn detect_trend(values: &[f64]) -> TrendDirection {
        if values.len() < 2 {
            return TrendDirection::Stable;
        }
        let n = values.len() as f64;
        let x_mean = (n - 1.0) / 2.0;
        let y_mean = values.iter().sum::<f64>() / n;

        let mut num = 0.0;
        let mut den = 0.0;
        for (i, &y) in values.iter().enumerate() {
            let x = i as f64;
            num += (x - x_mean) * (y - y_mean);
            den += (x - x_mean).powi(2);
        }
        if den == 0.0 {
            return TrendDirection::Stable;
        }
        let slope = num / den;
        let threshold = y_mean.abs() * 0.05; // 5% of mean as threshold
        if slope > threshold {
            TrendDirection::Rising
        } else if slope < -threshold {
            TrendDirection::Falling
        } else {
            TrendDirection::Stable
        }
    }

    /// Calculate profit margin percentage safely.
    pub fn profit_margin(revenue: f64, expenses: f64) -> f64 {
        if revenue == 0.0 {
            return 0.0;
        }
        ((revenue - expenses) / revenue) * 100.0
    }

    /// Generate a daily business report with trend analysis.
    pub fn generate_daily(
        &self,
        revenue: f64,
        expenses: f64,
        profit: f64,
        top_products: &[String],
        historical_revenues: &[f64],
        historical_expenses: &[f64],
        transaction_count: usize,
    ) -> Report {
        let margin = Self::profit_margin(revenue, expenses);
        let rev_trend = Self::detect_trend(historical_revenues);
        let exp_trend = Self::detect_trend(historical_expenses);
        let avg_txn = if transaction_count > 0 { revenue / transaction_count as f64 } else { 0.0 };

        let trend_icon = |t: &TrendDirection| match t {
            TrendDirection::Rising => "📈",
            TrendDirection::Falling => "📉",
            TrendDirection::Stable => "➡️",
        };

        let content = format!(
            "📊 Msaidizi CFO — Daily Report\n\
             ━━━━━━━━━━━━━━━━\n\
             💰 Revenue: KES {:,.0}  {} {}\n\
             📉 Expenses: KES {:,.0}  {} {}\n\
             ✅ Profit: KES {:,.0}\n\
             📊 Margin: {:.1}%\n\
             🔢 Transactions: {} (avg KES {:,.0})\n\
             🏆 Top: {}\n\
             ━━━━━━━━━━━━━━━━",
            revenue, trend_icon(&rev_trend), format!("{:?}", rev_trend),
            expenses, trend_icon(&exp_trend), format!("{:?}", exp_trend),
            profit, margin,
            transaction_count, avg_txn,
            top_products.join(", "),
        );

        Report {
            report_type: ReportType::Daily,
            title: "Daily Business Report".to_string(),
            content,
            format: "text".to_string(),
            generated_at: Utc::now().to_rfc3339(),
            metrics: ReportMetrics {
                revenue,
                expenses,
                profit,
                profit_margin_pct: margin,
                revenue_trend: rev_trend,
                expense_trend: exp_trend,
                transaction_count,
                avg_transaction_value: avg_txn,
            },
        }
    }

    /// Generate a weekly summary with daily breakdown.
    pub fn generate_weekly(
        &self,
        daily_records: &[DailyRecord],
        best_day: &str,
    ) -> Report {
        let total_revenue: f64 = daily_records.iter().map(|d| d.revenue).sum();
        let total_expenses: f64 = daily_records.iter().map(|d| d.expenses).sum();
        let total_profit = total_revenue - total_expenses;
        let total_txns: usize = daily_records.iter().map(|d| d.transaction_count).sum();
        let margin = Self::profit_margin(total_revenue, total_expenses);

        let daily_revenues: Vec<f64> = daily_records.iter().map(|d| d.revenue).collect();
        let daily_expenses: Vec<f64> = daily_records.iter().map(|d| d.expenses).collect();
        let rev_trend = Self::detect_trend(&daily_revenues);
        let exp_trend = Self::detect_trend(&daily_expenses);

        let avg_daily_rev = if !daily_records.is_empty() { total_revenue / daily_records.len() as f64 } else { 0.0 };

        let content = format!(
            "📊 Msaidizi CFO — Weekly Report\n\
             ━━━━━━━━━━━━━━━━\n\
             💰 Total Revenue: KES {:,.0}\n\
             📉 Total Expenses: KES {:,.0}\n\
             ✅ Total Profit: KES {:,.0}\n\
             📊 Margin: {:.1}%\n\
             📈 Avg Daily Revenue: KES {:,.0}\n\
             🔢 Total Transactions: {}\n\
             🏆 Best Day: {}\n\
             ━━━━━━━━━━━━━━━━",
            total_revenue, total_expenses, total_profit, margin,
            avg_daily_rev, total_txns, best_day,
        );

        Report {
            report_type: ReportType::Weekly,
            title: "Weekly Business Report".to_string(),
            content,
            format: "text".to_string(),
            generated_at: Utc::now().to_rfc3339(),
            metrics: ReportMetrics {
                revenue: total_revenue,
                expenses: total_expenses,
                profit: total_profit,
                profit_margin_pct: margin,
                revenue_trend: rev_trend,
                expense_trend: exp_trend,
                transaction_count: total_txns,
                avg_transaction_value: if total_txns > 0 { total_revenue / total_txns as f64 } else { 0.0 },
            },
        }
    }

    /// Generate monthly report with week-over-week comparison.
    pub fn generate_monthly(
        &self,
        daily_records: &[DailyRecord],
        previous_month_revenue: f64,
    ) -> Report {
        let total_revenue: f64 = daily_records.iter().map(|d| d.revenue).sum();
        let total_expenses: f64 = daily_records.iter().map(|d| d.expenses).sum();
        let total_profit = total_revenue - total_expenses;
        let total_txns: usize = daily_records.iter().map(|d| d.transaction_count).sum();
        let margin = Self::profit_margin(total_revenue, total_expenses);

        let mom_change = if previous_month_revenue > 0.0 {
            ((total_revenue - previous_month_revenue) / previous_month_revenue) * 100.0
        } else {
            0.0
        };

        let daily_revenues: Vec<f64> = daily_records.iter().map(|d| d.revenue).collect();
        let rev_trend = Self::detect_trend(&daily_revenues);
        let daily_expenses: Vec<f64> = daily_records.iter().map(|d| d.expenses).collect();
        let exp_trend = Self::detect_trend(&daily_expenses);

        let best_day = daily_records.iter()
            .max_by(|a, b| a.revenue.partial_cmp(&b.revenue).unwrap_or(std::cmp::Ordering::Equal))
            .map(|d| d.date.to_string())
            .unwrap_or_else(|| "N/A".to_string());

        let mom_icon = if mom_change >= 0.0 { "📈" } else { "📉" };

        let content = format!(
            "📊 Msaidizi CFO — Monthly Report\n\
             ━━━━━━━━━━━━━━━━\n\
             💰 Total Revenue: KES {:,.0}\n\
             📉 Total Expenses: KES {:,.0}\n\
             ✅ Total Profit: KES {:,.0}\n\
             📊 Margin: {:.1}%\n\
             {} MoM Change: {:+.1}%\n\
             🔢 Total Transactions: {}\n\
             🏆 Best Day: {}\n\
             📅 Days Tracked: {}\n\
             ━━━━━━━━━━━━━━━━",
            total_revenue, total_expenses, total_profit, margin,
            mom_icon, mom_change, total_txns, best_day, daily_records.len(),
        );

        Report {
            report_type: ReportType::Monthly,
            title: "Monthly Business Report".to_string(),
            content,
            format: "text".to_string(),
            generated_at: Utc::now().to_rfc3339(),
            metrics: ReportMetrics {
                revenue: total_revenue,
                expenses: total_expenses,
                profit: total_profit,
                profit_margin_pct: margin,
                revenue_trend: rev_trend,
                expense_trend: exp_trend,
                transaction_count: total_txns,
                avg_transaction_value: if total_txns > 0 { total_revenue / total_txns as f64 } else { 0.0 },
            },
        }
    }

    /// Generate credit score report with detailed factors.
    pub fn generate_credit(&self, score: u32, factors: &CreditFactors) -> Report {
        let risk_tier = match score {
            750..=850 => "Excellent — Very Low Risk",
            650..=749 => "Good — Low Risk",
            550..=649 => "Fair — Moderate Risk",
            450..=549 => "Poor — High Risk",
            _ => "Very Poor — Very High Risk",
        };

        let max_score = 850u32;
        let bar_filled = (score as f64 / max_score as f64 * 20.0) as usize;
        let bar: String = "█".repeat(bar_filled) + &"░".repeat(20 - bar_filled);

        let content = format!(
            "🏦 Alama Score Report\n\
             ━━━━━━━━━━━━━━━━\n\
             Score: {}/850  [{bar}]\n\
             Tier: {risk_tier}\n\
             \n\
             📋 Factor Breakdown:\n\
             • Payment History: {:.0}/100\n\
             • Income Stability: {:.0}/100\n\
             • Debt-to-Income: {:.1}%\n\
             • Account Age: {} months\n\
             • Defaults: {}\n\
             ━━━━━━━━━━━━━━━━",
            score, factors.payment_history_score, factors.income_stability_score,
            factors.debt_ratio * 100.0, factors.account_age_months, factors.defaults,
        );

        Report {
            report_type: ReportType::Credit,
            title: "Credit Score Report".to_string(),
            content,
            format: "text".to_string(),
            generated_at: Utc::now().to_rfc3339(),
            metrics: ReportMetrics {
                revenue: 0.0,
                expenses: 0.0,
                profit: 0.0,
                profit_margin_pct: 0.0,
                revenue_trend: TrendDirection::Stable,
                expense_trend: TrendDirection::Stable,
                transaction_count: 0,
                avg_transaction_value: 0.0,
            },
        }
    }

    /// Export a report to JSON format.
    pub fn export_json(report: &Report) -> Result<String> {
        serde_json::to_string_pretty(report)
            .context("Failed to serialize report to JSON")
    }

    /// Export daily records to CSV format.
    pub fn export_csv(records: &[DailyRecord]) -> String {
        let mut csv = String::from("date,revenue,expenses,profit,transaction_count\n");
        for r in records {
            csv.push_str(&format!(
                "{},{:.2},{:.2},{:.2},{}\n",
                r.date, r.revenue, r.expenses, r.revenue - r.expenses, r.transaction_count
            ));
        }
        csv
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::NaiveDate;

    #[test]
    fn test_detect_trend_rising() {
        let values = vec![100.0, 110.0, 120.0, 130.0, 150.0];
        assert_eq!(ReportEngine::detect_trend(&values), TrendDirection::Rising);
    }

    #[test]
    fn test_detect_trend_falling() {
        let values = vec![150.0, 130.0, 110.0, 90.0, 70.0];
        assert_eq!(ReportEngine::detect_trend(&values), TrendDirection::Falling);
    }

    #[test]
    fn test_detect_trend_stable() {
        let values = vec![100.0, 100.0, 101.0, 99.0, 100.0];
        assert_eq!(ReportEngine::detect_trend(&values), TrendDirection::Stable);
    }

    #[test]
    fn test_detect_trend_single_value() {
        assert_eq!(ReportEngine::detect_trend(&[100.0]), TrendDirection::Stable);
    }

    #[test]
    fn test_profit_margin() {
        assert!((ReportEngine::profit_margin(1000.0, 600.0) - 40.0).abs() < 0.01);
        assert!((ReportEngine::profit_margin(0.0, 100.0)).abs() < 0.01);
        assert!((ReportEngine::profit_margin(1000.0, 1200.0) - (-20.0)).abs() < 0.01);
    }

    #[test]
    fn test_generate_daily_report() {
        let engine = ReportEngine::new();
        let products = vec!["Milk".to_string(), "Bread".to_string()];
        let report = engine.generate_daily(
            5000.0, 3000.0, 2000.0, &products,
            &[4000.0, 4500.0, 5000.0], &[2800.0, 2900.0, 3000.0], 25,
        );
        assert_eq!(report.report_type, ReportType::Daily);
        assert!(report.content.contains("Revenue"));
        assert!(report.metrics.profit_margin_pct > 0.0);
        assert_eq!(report.metrics.transaction_count, 25);
    }

    #[test]
    fn test_generate_weekly_report() {
        let engine = ReportEngine::new();
        let records = vec![
            DailyRecord { date: NaiveDate::from_ymd_opt(2024, 1, 1).unwrap(), revenue: 1000.0, expenses: 600.0, transaction_count: 10 },
            DailyRecord { date: NaiveDate::from_ymd_opt(2024, 1, 2).unwrap(), revenue: 1200.0, expenses: 700.0, transaction_count: 15 },
            DailyRecord { date: NaiveDate::from_ymd_opt(2024, 1, 3).unwrap(), revenue: 900.0, expenses: 500.0, transaction_count: 8 },
        ];
        let report = engine.generate_weekly(&records, "2024-01-02");
        assert_eq!(report.report_type, ReportType::Weekly);
        assert!((report.metrics.revenue - 3100.0).abs() < 0.01);
    }

    #[test]
    fn test_generate_monthly_report() {
        let engine = ReportEngine::new();
        let records = vec![
            DailyRecord { date: NaiveDate::from_ymd_opt(2024, 1, 1).unwrap(), revenue: 5000.0, expenses: 3000.0, transaction_count: 20 },
            DailyRecord { date: NaiveDate::from_ymd_opt(2024, 1, 2).unwrap(), revenue: 6000.0, expenses: 3500.0, transaction_count: 25 },
        ];
        let report = engine.generate_monthly(&records, 9000.0);
        assert_eq!(report.report_type, ReportType::Monthly);
        assert!((report.metrics.revenue - 11000.0).abs() < 0.01);
    }

    #[test]
    fn test_generate_credit_report() {
        let engine = ReportEngine::new();
        let factors = CreditFactors {
            payment_history_score: 85.0,
            income_stability_score: 70.0,
            debt_ratio: 0.3,
            account_age_months: 24,
            defaults: 0,
        };
        let report = engine.generate_credit(720, &factors);
        assert_eq!(report.report_type, ReportType::Credit);
        assert!(report.content.contains("720"));
        assert!(report.content.contains("Good"));
    }

    #[test]
    fn test_export_json() {
        let engine = ReportEngine::new();
        let report = engine.generate_daily(
            1000.0, 500.0, 500.0, &["Test".to_string()],
            &[900.0, 1000.0], &[450.0, 500.0], 5,
        );
        let json = ReportEngine::export_json(&report).unwrap();
        assert!(json.contains("Daily"));
        let parsed: serde_json::Value = serde_json::from_str(&json).unwrap();
        assert!(parsed["metrics"]["revenue"].as_f64().unwrap() > 0.0);
    }

    #[test]
    fn test_export_csv() {
        let records = vec![
            DailyRecord { date: NaiveDate::from_ymd_opt(2024, 1, 1).unwrap(), revenue: 1000.0, expenses: 500.0, transaction_count: 10 },
        ];
        let csv = ReportEngine::export_csv(&records);
        assert!(csv.starts_with("date,revenue"));
        assert!(csv.contains("2024-01-01"));
        assert!(csv.contains("1000.00"));
    }
}
