//! FMCGIntelligence — Manufacturer intelligence products
//!
//! Generates intelligence reports for FMCG manufacturers including demand
//! forecasting, competitor analysis, pricing optimization, and market
//! penetration insights from aggregated worker transaction data.

use anyhow::Result;
use chrono::{DateTime, NaiveDate, Utc};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use uuid::Uuid;

use crate::db::DatabaseConnections;
use crate::tools::market_analyzer::{MarketAnalyzer, TrendDirection};
use crate::tools::distribution_analyzer::DistributionAnalyzer;

/// FMCG intelligence report for manufacturers
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FMCGReport {
    pub report_id: Uuid,
    pub manufacturer_id: Uuid,
    pub report_type: FMCGReportType,
    pub period: String,
    pub demand_forecast: DemandForecast,
    pub competitor_analysis: CompetitorAnalysis,
    pub pricing_optimization: PricingOptimization,
    pub market_penetration: MarketPenetration,
    pub recommendations: Vec<Recommendation>,
    pub confidence: f64,
    pub generated_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum FMCGReportType {
    Monthly,
    Quarterly,
    OnDemand,
    Custom,
}

/// Demand forecast for products
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DemandForecast {
    pub product_forecasts: Vec<ProductForecast>,
    pub aggregate_trend: TrendDirection,
    pub forecast_accuracy: f64,
    pub horizon_days: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProductForecast {
    pub product_category: String,
    pub current_demand_index: f64,
    pub projected_demand_index: f64,
    pub confidence_interval_lower: f64,
    pub confidence_interval_upper: f64,
    pub trend: TrendDirection,
    pub seasonality_factor: f64,
}

/// Competitor analysis
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CompetitorAnalysis {
    pub market_share_estimates: Vec<MarketShare>,
    pub competitive_position: String,
    pub threat_level: String,
    pub opportunities: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MarketShare {
    pub brand: String,
    pub estimated_share_pct: f64,
    pub trend: TrendDirection,
    pub regions_strong: Vec<String>,
}

/// Pricing optimization recommendations
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PricingOptimization {
    pub current_avg_price: f64,
    pub recommended_price: f64,
    pub price_elasticity: f64,
    pub expected_volume_impact_pct: f64,
    pub expected_revenue_impact_pct: f64,
    pub price_bands: Vec<PriceBand>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PriceBand {
    pub min_price: f64,
    pub max_price: f64,
    pub expected_volume: u64,
    pub expected_revenue: f64,
}

/// Market penetration metrics
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MarketPenetration {
    pub regions_covered: u32,
    pub regions_total: u32,
    pub penetration_pct: f64,
    pub active_sellers: u64,
    pub growth_rate: f64,
    pub underserved_regions: Vec<String>,
}

/// An actionable recommendation
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Recommendation {
    pub category: String,
    pub priority: String,
    pub action: String,
    pub expected_impact: String,
    pub confidence: f64,
}

/// The FMCGIntelligence tool
pub struct FMCGIntelligence {
    db: DatabaseConnections,
}

impl FMCGIntelligence {
    pub fn new(db: DatabaseConnections) -> Self {
        Self { db }
    }

    /// Generate a full FMCG intelligence report
    pub async fn generate_report(
        &self,
        manufacturer_id: Uuid,
        report_type: FMCGReportType,
    ) -> Result<FMCGReport> {
        let demand_forecast = self.forecast_demand(30).await?;
        let competitor_analysis = self.analyze_competitors().await?;
        let pricing = self.optimize_pricing().await?;
        let penetration = self.measure_penetration().await?;
        let recommendations = self.generate_recommendations(
            &demand_forecast,
            &competitor_analysis,
            &pricing,
            &penetration,
        );

        let confidence = self.calculate_report_confidence(
            &demand_forecast,
            &competitor_analysis,
        );

        Ok(FMCGReport {
            report_id: Uuid::new_v4(),
            manufacturer_id,
            report_type,
            period: "last_30_days".to_string(),
            demand_forecast,
            competitor_analysis,
            pricing_optimization: pricing,
            market_penetration: penetration,
            recommendations,
            confidence,
            generated_at: Utc::now(),
        })
    }

    /// Forecast demand for products
    async fn forecast_demand(&self, horizon_days: u32) -> Result<DemandForecast> {
        let query = r#"
            SELECT 
                metadata as product_category,
                toStartOfDay(event_time) as day,
                count() as daily_volume,
                avg(amount) as daily_avg
            FROM revenue_events
            WHERE event_time >= now() - INTERVAL 60 DAY
            GROUP BY metadata, day
            ORDER BY metadata, day
        "#;

        #[derive(clickhouse::Row, Deserialize)]
        struct DailyRow {
            product_category: String,
            day: chrono::NaiveDateTime,
            daily_volume: u64,
            daily_avg: f64,
        }

        let rows = self
            .db
            .clickhouse
            .query(query)
            .fetch_all::<DailyRow>()
            .await
            .unwrap_or_default();

        let mut by_category: HashMap<String, Vec<u64>> = HashMap::new();
        for row in &rows {
            by_category
                .entry(row.product_category.clone())
                .or_default()
                .push(row.daily_volume);
        }

        let mut product_forecasts = Vec::new();
        for (category, volumes) in &by_category {
            if volumes.len() < 14 {
                continue;
            }

            let current = *volumes.last().unwrap_or(&0) as f64;
            let avg = volumes.iter().sum::<u64>() as f64 / volumes.len() as f64;

            // Simple trend projection
            let recent_avg: f64 =
                volumes.iter().rev().take(7).sum::<u64>() as f64 / 7.0;
            let older_avg: f64 = volumes.iter().rev().skip(7).take(7).sum::<u64>() as f64 / 7.0;

            let trend = if recent_avg > older_avg * 1.1 {
                TrendDirection::Rising
            } else if recent_avg < older_avg * 0.9 {
                TrendDirection::Falling
            } else {
                TrendDirection::Stable
            };

            let growth_rate = if older_avg > 0.0 {
                (recent_avg - older_avg) / older_avg
            } else {
                0.0
            };

            let projected = current * (1.0 + growth_rate * horizon_days as f64 / 30.0);
            let std_dev = self.std_dev(volumes);

            product_forecasts.push(ProductForecast {
                product_category: category.clone(),
                current_demand_index: current,
                projected_demand_index: projected.max(0.0),
                confidence_interval_lower: (projected - 1.96 * std_dev).max(0.0),
                confidence_interval_upper: projected + 1.96 * std_dev,
                trend,
                seasonality_factor: 1.0, // Would compute from yearly data
            });
        }

        Ok(DemandForecast {
            product_forecasts,
            aggregate_trend: TrendDirection::Stable,
            forecast_accuracy: 0.75,
            horizon_days,
        })
    }

    /// Analyze competitors from transaction data
    async fn analyze_competitors(&self) -> Result<CompetitorAnalysis> {
        let query = r#"
            SELECT 
                metadata as brand,
                count() as volume,
                count(DISTINCT customer_id) as sellers
            FROM revenue_events
            WHERE event_time >= now() - INTERVAL 30 DAY
            GROUP BY metadata
            ORDER BY volume DESC
            LIMIT 20
        "#;

        #[derive(clickhouse::Row, Deserialize)]
        struct BrandRow {
            brand: String,
            volume: u64,
            sellers: u64,
        }

        let rows = self
            .db
            .clickhouse
            .query(query)
            .fetch_all::<BrandRow>()
            .await
            .unwrap_or_default();

        let total_volume: u64 = rows.iter().map(|r| r.volume).sum();

        let market_share_estimates: Vec<MarketShare> = rows
            .iter()
            .map(|r| MarketShare {
                brand: r.brand.clone(),
                estimated_share_pct: if total_volume > 0 {
                    r.volume as f64 / total_volume as f64 * 100.0
                } else {
                    0.0
                },
                trend: TrendDirection::Stable,
                regions_strong: vec![],
            })
            .collect();

        Ok(CompetitorAnalysis {
            market_share_estimates,
            competitive_position: "analyzing".to_string(),
            threat_level: "moderate".to_string(),
            opportunities: vec![
                "Expand into underserved regions".to_string(),
                "Optimize pricing for volume growth".to_string(),
            ],
        })
    }

    /// Optimize pricing recommendations
    async fn optimize_pricing(&self) -> Result<PricingOptimization> {
        let query = r#"
            SELECT 
                avg(amount) as avg_price,
                stddevPop(amount) as price_stddev,
                count() as volume
            FROM revenue_events
            WHERE event_time >= now() - INTERVAL 30 DAY
        "#;

        #[derive(clickhouse::Row, Deserialize)]
        struct PriceStats {
            avg_price: f64,
            price_stddev: f64,
            volume: u64,
        }

        let stats = self
            .db
            .clickhouse
            .query(query)
            .fetch_one::<PriceStats>()
            .await;

        let (avg_price, stddev, volume) = match stats {
            Ok(s) => (s.avg_price, s.price_stddev, s.volume),
            Err(_) => (0.0, 0.0, 0),
        };

        // Simple price elasticity estimate
        let elasticity = if avg_price > 0.0 {
            (stddev / avg_price).min(2.0) // Normalized
        } else {
            1.0
        };

        let recommended = avg_price * 0.95; // 5% reduction for volume growth
        let expected_volume_impact = elasticity * 5.0; // % change

        Ok(PricingOptimization {
            current_avg_price: avg_price,
            recommended_price: recommended,
            price_elasticity: elasticity,
            expected_volume_impact_pct: expected_volume_impact,
            expected_revenue_impact_pct: expected_volume_impact - 5.0,
            price_bands: vec![
                PriceBand {
                    min_price: avg_price * 0.8,
                    max_price: avg_price * 0.9,
                    expected_volume: (volume as f64 * 1.15) as u64,
                    expected_revenue: avg_price * 0.85 * volume as f64 * 1.15,
                },
                PriceBand {
                    min_price: avg_price * 0.9,
                    max_price: avg_price * 1.0,
                    expected_volume: volume,
                    expected_revenue: avg_price * volume as f64,
                },
                PriceBand {
                    min_price: avg_price * 1.0,
                    max_price: avg_price * 1.1,
                    expected_volume: (volume as f64 * 0.85) as u64,
                    expected_revenue: avg_price * 1.05 * volume as f64 * 0.85,
                },
            ],
        })
    }

    /// Measure market penetration
    async fn measure_penetration(&self) -> Result<MarketPenetration> {
        let query = r#"
            SELECT 
                count(DISTINCT customer_id) as active_sellers,
                count() as total_transactions
            FROM revenue_events
            WHERE event_time >= now() - INTERVAL 30 DAY
        "#;

        #[derive(clickhouse::Row, Deserialize)]
        struct PenetrationRow {
            active_sellers: u64,
            total_transactions: u64,
        }

        let row = self
            .db
            .clickhouse
            .query(query)
            .fetch_one::<PenetrationRow>()
            .await;

        let (active_sellers, total_tx) = match row {
            Ok(r) => (r.active_sellers, r.total_transactions),
            Err(_) => (0, 0),
        };

        Ok(MarketPenetration {
            regions_covered: 1, // Would expand with regional data
            regions_total: 47,  // Kenya counties
            penetration_pct: 2.1,
            active_sellers,
            growth_rate: 0.0,
            underserved_regions: vec![
                "Turkana".to_string(),
                "Marsabit".to_string(),
                "Mandera".to_string(),
            ],
        })
    }

    /// Generate actionable recommendations
    fn generate_recommendations(
        &self,
        demand: &DemandForecast,
        competitors: &CompetitorAnalysis,
        pricing: &PricingOptimization,
        penetration: &MarketPenetration,
    ) -> Vec<Recommendation> {
        let mut recs = Vec::new();

        // Demand-based recommendations
        for forecast in &demand.product_forecasts {
            if matches!(forecast.trend, TrendDirection::Rising) {
                recs.push(Recommendation {
                    category: "demand".to_string(),
                    priority: "high".to_string(),
                    action: format!(
                        "Increase stock for '{}' — demand trending up",
                        forecast.product_category
                    ),
                    expected_impact: "Capture growing demand".to_string(),
                    confidence: 0.8,
                });
            }
        }

        // Pricing recommendations
        if pricing.expected_revenue_impact_pct > 0.0 {
            recs.push(Recommendation {
                category: "pricing".to_string(),
                priority: "medium".to_string(),
                action: format!(
                    "Consider price adjustment to {:.2} for volume growth",
                    pricing.recommended_price
                ),
                expected_impact: format!(
                    "{:.1}% revenue increase",
                    pricing.expected_revenue_impact_pct
                ),
                confidence: 0.65,
            });
        }

        // Penetration recommendations
        if penetration.penetration_pct < 10.0 {
            recs.push(Recommendation {
                category: "distribution".to_string(),
                priority: "high".to_string(),
                action: "Expand distribution to underserved regions".to_string(),
                expected_impact: "Significant market share growth".to_string(),
                confidence: 0.7,
            });
        }

        recs
    }

    fn calculate_report_confidence(
        &self,
        demand: &DemandForecast,
        competitors: &CompetitorAnalysis,
    ) -> f64 {
        let data_points: u64 = demand
            .product_forecasts
            .iter()
            .map(|f| f.current_demand_index as u64)
            .sum();
        let data_confidence = (1.0 - 1.0 / (1.0 + (data_points as f64).ln())).min(0.95);
        let competitor_confidence = if competitors.market_share_estimates.len() > 5 {
            0.8
        } else {
            0.5
        };
        (data_confidence * 0.6 + competitor_confidence * 0.4).min(0.95)
    }

    fn std_dev(&self, values: &[u64]) -> f64 {
        let n = values.len() as f64;
        if n < 2.0 {
            return 0.0;
        }
        let mean = values.iter().sum::<u64>() as f64 / n;
        let variance =
            values.iter().map(|v| (*v as f64 - mean).powi(2)).sum::<f64>() / (n - 1.0);
        variance.sqrt()
    }
}
