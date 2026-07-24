//! DistributionAnalyzer — FMCG distribution gap analysis
//!
//! Analyzes product sales across regions to identify distribution gaps,
//! underserved areas, and opportunities for FMCG manufacturers.

use anyhow::Result;
use chrono::{DateTime, NaiveDate, Utc};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use uuid::Uuid;

use crate::db::DatabaseConnections;

/// A distribution gap identified by the analyzer
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DistributionGap {
    pub gap_id: Uuid,
    pub product_category: String,
    pub region: String,
    pub sub_region: String,
    pub demand_index: f64,
    pub supply_index: f64,
    pub gap_severity: f64,
    pub opportunity_size: f64,
    pub estimated_monthly_revenue: f64,
    pub competitor_presence: Vec<String>,
    pub recommended_actions: Vec<String>,
    pub confidence: f64,
    pub identified_at: DateTime<Utc>,
}

/// Regional distribution health
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RegionalHealth {
    pub region: String,
    pub total_products: u32,
    pub well_distributed: u32,
    pub under_distributed: u32,
    pub over_distributed: u32,
    pub coverage_score: f64,
    pub gini_coefficient: f64,
    pub top_gaps: Vec<String>,
}

/// Product distribution metrics
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProductDistribution {
    pub product_category: String,
    pub regions_present: u32,
    pub regions_total: u32,
    pub coverage_pct: f64,
    pub top_regions: Vec<(String, f64)>,
    pub bottom_regions: Vec<(String, f64)>,
    pub distribution_evenness: f64,
}

/// FMCG distribution report
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DistributionReport {
    pub report_id: Uuid,
    pub period: String,
    pub total_gaps: u32,
    pub critical_gaps: u32,
    pub total_opportunity_revenue: f64,
    pub gaps: Vec<DistributionGap>,
    pub regional_health: Vec<RegionalHealth>,
    pub generated_at: DateTime<Utc>,
}

/// The DistributionAnalyzer tool
pub struct DistributionAnalyzer {
    db: DatabaseConnections,
    min_cohort_size: u32,
}

impl DistributionAnalyzer {
    pub fn new(db: DatabaseConnections) -> Self {
        Self {
            db,
            min_cohort_size: 10,
        }
    }

    /// Analyze distribution gaps across all product categories and regions
    pub async fn analyze_gaps(&self) -> Result<Vec<DistributionGap>> {
        // Fetch aggregated sales data from ClickHouse
        let query = r#"
            SELECT 
                metadata as product_category,
                '' as region,
                count() as sales_volume,
                avg(amount) as avg_price,
                count(DISTINCT customer_id) as unique_sellers
            FROM revenue_events
            WHERE event_time >= now() - INTERVAL 30 DAY
            GROUP BY metadata
            HAVING count() >= 10
            ORDER BY sales_volume DESC
        "#;

        #[derive(clickhouse::Row, Deserialize)]
        struct SalesRow {
            product_category: String,
            region: String,
            sales_volume: u64,
            avg_price: f64,
            unique_sellers: u64,
        }

        let rows = self
            .db
            .clickhouse
            .query(query)
            .fetch_all::<SalesRow>()
            .await
            .unwrap_or_default();

        // Compute supply/demand indices per region
        let max_volume = rows.iter().map(|r| r.sales_volume).max().unwrap_or(1) as f64;
        let max_sellers = rows.iter().map(|r| r.unique_sellers).max().unwrap_or(1) as f64;

        let mut gaps = Vec::new();

        for row in &rows {
            let demand_index = (row.sales_volume as f64 / max_volume * 100.0).min(100.0);
            let supply_index = (row.unique_sellers as f64 / max_sellers * 100.0).min(100.0);

            // Gap = demand exceeds supply
            let gap_severity = if supply_index > 0.0 {
                (demand_index / supply_index - 1.0).max(0.0)
            } else {
                demand_index / 100.0
            };

            if gap_severity > 0.2 {
                // Significant gap threshold
                let opportunity = self
                    .estimate_opportunity(&row.product_category, gap_severity, row.avg_price)
                    .await;

                gaps.push(DistributionGap {
                    gap_id: Uuid::new_v4(),
                    product_category: row.product_category.clone(),
                    region: row.region.clone(),
                    sub_region: "all".to_string(),
                    demand_index,
                    supply_index,
                    gap_severity,
                    opportunity_size: opportunity.0,
                    estimated_monthly_revenue: opportunity.1,
                    competitor_presence: vec![],
                    recommended_actions: self.recommend_actions(gap_severity),
                    confidence: self.calculate_confidence(row.sales_volume),
                    identified_at: Utc::now(),
                });
            }
        }

        // Sort by opportunity size descending
        gaps.sort_by(|a, b| {
            b.estimated_monthly_revenue
                .partial_cmp(&a.estimated_monthly_revenue)
                .unwrap_or(std::cmp::Ordering::Equal)
        });

        Ok(gaps)
    }

    /// Get distribution health for a specific region
    pub async fn regional_health(&self, region: &str) -> Result<RegionalHealth> {
        let query = format!(
            r#"
            SELECT 
                metadata as product_category,
                count() as volume,
                count(DISTINCT customer_id) as sellers
            FROM revenue_events
            WHERE event_time >= now() - INTERVAL 30 DAY
            GROUP BY metadata
            HAVING count() >= {}
            "#,
            self.min_cohort_size
        );

        #[derive(clickhouse::Row, Deserialize)]
        struct ProductRow {
            product_category: String,
            volume: u64,
            sellers: u64,
        }

        let rows = self
            .db
            .clickhouse
            .query(&query)
            .fetch_all::<ProductRow>()
            .await
            .unwrap_or_default();

        let total_products = rows.len() as u32;
        let volumes: Vec<f64> = rows.iter().map(|r| r.volume as f64).collect();
        let gini = self.gini_coefficient(&volumes);

        let mut well_distributed = 0u32;
        let mut under_distributed = 0u32;
        let mut over_distributed = 0u32;
        let mut top_gaps = Vec::new();

        if !volumes.is_empty() {
            let mean: f64 = volumes.iter().sum::<f64>() / volumes.len() as f64;
            for (i, row) in rows.iter().enumerate() {
                let ratio = volumes[i] / mean;
                if ratio > 1.5 {
                    over_distributed += 1;
                } else if ratio < 0.5 {
                    under_distributed += 1;
                    top_gaps.push(row.product_category.clone());
                } else {
                    well_distributed += 1;
                }
            }
        }

        let coverage_score = if total_products > 0 {
            well_distributed as f64 / total_products as f64
        } else {
            0.0
        };

        Ok(RegionalHealth {
            region: region.to_string(),
            total_products,
            well_distributed,
            under_distributed,
            over_distributed,
            coverage_score,
            gini_coefficient: gini,
            top_gaps,
        })
    }

    /// Get distribution metrics for a specific product
    pub async fn product_distribution(&self, category: &str) -> Result<ProductDistribution> {
        let query = format!(
            r#"
            SELECT 
                '' as region,
                count() as volume,
                avg(amount) as avg_price
            FROM revenue_events
            WHERE metadata = '{}' AND event_time >= now() - INTERVAL 30 DAY
            GROUP BY region
            "#,
            category
        );

        #[derive(clickhouse::Row, Deserialize)]
        struct RegionRow {
            region: String,
            volume: u64,
            avg_price: f64,
        }

        let rows = self
            .db
            .clickhouse
            .query(&query)
            .fetch_all::<RegionRow>()
            .await
            .unwrap_or_default();

        let total_volume: u64 = rows.iter().map(|r| r.volume).sum();
        let regions_present = rows.len() as u32;

        let mut top_regions: Vec<(String, f64)> = rows
            .iter()
            .map(|r| {
                (
                    r.region.clone(),
                    r.volume as f64 / total_volume.max(1) as f64,
                )
            })
            .collect();
        top_regions.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));

        let mut bottom_regions = top_regions.clone();
        bottom_regions.reverse();

        let evenness = if !top_regions.is_empty() {
            let shares: Vec<f64> = top_regions.iter().map(|(_, s)| *s).collect();
            1.0 - self.gini_coefficient(&shares)
        } else {
            0.0
        };

        Ok(ProductDistribution {
            product_category: category.to_string(),
            regions_present,
            regions_total: regions_present, // Would be total regions in full implementation
            coverage_pct: 100.0,            // Placeholder
            top_regions: top_regions.into_iter().take(5).collect(),
            bottom_regions: bottom_regions.into_iter().take(5).collect(),
            distribution_evenness: evenness,
        })
    }

    /// Generate a full distribution report
    pub async fn generate_report(&self, period: &str) -> Result<DistributionReport> {
        let gaps = self.analyze_gaps().await?;
        let critical_gaps = gaps.iter().filter(|g| g.gap_severity > 0.5).count() as u32;
        let total_opportunity: f64 = gaps.iter().map(|g| g.estimated_monthly_revenue).sum();

        Ok(DistributionReport {
            report_id: Uuid::new_v4(),
            period: period.to_string(),
            total_gaps: gaps.len() as u32,
            critical_gaps,
            total_opportunity_revenue: total_opportunity,
            gaps,
            regional_health: vec![], // Populated on demand
            generated_at: Utc::now(),
        })
    }

    // Private helpers

    async fn estimate_opportunity(
        &self,
        _category: &str,
        gap_severity: f64,
        avg_price: f64,
    ) -> (f64, f64) {
        // Estimate market opportunity based on gap severity
        let opportunity_size = gap_severity * 1000.0; // Units
        let monthly_revenue = opportunity_size * avg_price;
        (opportunity_size, monthly_revenue)
    }

    fn recommend_actions(&self, gap_severity: f64) -> Vec<String> {
        let mut actions = Vec::new();
        if gap_severity > 0.5 {
            actions.push("Establish new distribution channels immediately".to_string());
            actions.push("Partner with local distributors".to_string());
        } else if gap_severity > 0.3 {
            actions.push("Increase distribution frequency".to_string());
            actions.push("Expand product range in region".to_string());
        } else {
            actions.push("Monitor and optimize existing distribution".to_string());
        }
        actions
    }

    fn gini_coefficient(&self, values: &[f64]) -> f64 {
        if values.is_empty() {
            return 0.0;
        }
        let n = values.len() as f64;
        let mean = values.iter().sum::<f64>() / n;
        if mean.abs() < 1e-10 {
            return 0.0;
        }
        let mut sorted = values.to_vec();
        sorted.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
        let mut sum_diff = 0.0;
        for (i, &v) in sorted.iter().enumerate() {
            for &w in &sorted[i + 1..] {
                sum_diff += (w - v).abs();
            }
        }
        sum_diff / (2.0 * n * n * mean)
    }

    fn calculate_confidence(&self, sample_size: u64) -> f64 {
        if sample_size == 0 {
            return 0.0;
        }
        (1.0 - 1.0 / (1.0 + (sample_size as f64).ln())).min(0.99)
    }
}
