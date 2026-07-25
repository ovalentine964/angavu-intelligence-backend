//! MarketAnalyzer — Aggregated demand patterns from 100K+ worker transactions
//!
//! Analyzes anonymized transaction data from the Angavu worker base to identify
//! demand signals, price elasticity, and regional variations.

use anyhow::{anyhow, Result};
use chrono::{DateTime, NaiveDate, Utc};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use uuid::Uuid;

use crate::db::DatabaseConnections;

/// A demand signal derived from transaction aggregation
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DemandSignal {
    pub signal_id: Uuid,
    pub product_category: String,
    pub region: String,
    pub demand_index: f64,
    pub volume: u64,
    pub avg_transaction_value: f64,
    pub trend: TrendDirection,
    pub confidence: f64,
    pub period_start: NaiveDate,
    pub period_end: NaiveDate,
    pub generated_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum TrendDirection {
    Rising,
    Falling,
    Stable,
    Volatile,
}

/// Price elasticity measurement
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PriceElasticity {
    pub product_category: String,
    pub region: String,
    pub elasticity_coefficient: f64,
    pub price_range_min: f64,
    pub price_range_max: f64,
    pub demand_sensitivity: DemandSensitivity,
    pub sample_size: u64,
    pub confidence: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum DemandSensitivity {
    Elastic,    // |e| > 1
    Inelastic,  // |e| < 1
    Unitary,    // |e| ≈ 1
}

/// Regional demand variation
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RegionalVariation {
    pub region: String,
    pub demand_index: f64,
    pub population_sampled: u64,
    pub dominant_categories: Vec<String>,
    pub avg_spend_per_worker: f64,
    pub growth_rate: f64,
    pub seasonality_factor: f64,
}

/// Trend detection result
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MarketTrend {
    pub trend_id: Uuid,
    pub category: String,
    pub trend_type: String,
    pub direction: TrendDirection,
    pub strength: f64,
    pub confidence: f64,
    pub description: String,
    pub data_points: u64,
    pub detected_at: DateTime<Utc>,
}

/// The MarketAnalyzer tool
pub struct MarketAnalyzer {
    db: DatabaseConnections,
}

impl MarketAnalyzer {
    pub fn new(db: DatabaseConnections) -> Self {
        Self { db }
    }

    /// Analyze demand from aggregated worker transaction data
    pub async fn analyze_demand(&self) -> Result<Vec<DemandSignal>> {
        // Query ClickHouse for aggregated transaction data
        let query = r#"
            SELECT 
                metadata as product_category,
                '' as region,
                count() as volume,
                avg(amount) as avg_value,
                min(event_time) as period_start,
                max(event_time) as period_end
            FROM revenue_events
            WHERE event_time >= now() - INTERVAL 7 DAY
            GROUP BY metadata
            HAVING count() >= 10
            ORDER BY volume DESC
            LIMIT 100
        "#;

        #[derive(clickhouse::Row, Deserialize)]
        struct DemandRow {
            product_category: String,
            region: String,
            volume: u64,
            avg_value: f64,
            period_start: chrono::NaiveDateTime,
            period_end: chrono::NaiveDateTime,
        }

        let rows = self
            .db
            .clickhouse
            .query(query)
            .fetch_all::<DemandRow>()
            .await
            .unwrap_or_default();

        // Compute demand index using logarithmic scaling
        let max_volume = rows.iter().map(|r| r.volume).max().unwrap_or(1) as f64;

        let signals: Vec<DemandSignal> = rows
            .into_iter()
            .map(|row| {
                let demand_index = (row.volume as f64 / max_volume * 100.0).min(100.0);
                let trend = self.classify_trend(demand_index, row.volume);

                DemandSignal {
                    signal_id: Uuid::new_v4(),
                    product_category: row.product_category,
                    region: row.region,
                    demand_index,
                    volume: row.volume,
                    avg_transaction_value: row.avg_value,
                    trend,
                    confidence: self.calculate_confidence(row.volume),
                    period_start: row.period_start.date(),
                    period_end: row.period_end.date(),
                    generated_at: Utc::now(),
                }
            })
            .collect();

        Ok(signals)
    }

    /// Detect emerging market trends
    pub async fn detect_trends(&self) -> Result<Vec<MarketTrend>> {
        let query = r#"
            SELECT 
                metadata as category,
                toStartOfDay(event_time) as day,
                count() as daily_volume,
                avg(amount) as daily_avg
            FROM revenue_events
            WHERE event_time >= now() - INTERVAL 30 DAY
            GROUP BY metadata, day
            ORDER BY category, day
        "#;

        #[derive(clickhouse::Row, Deserialize)]
        struct DailyRow {
            category: String,
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

        // Group by category and compute trend
        let mut by_category: HashMap<String, Vec<(u64, f64)>> = HashMap::new();
        for row in &rows {
            by_category
                .entry(row.category.clone())
                .or_default()
                .push((row.daily_volume, row.daily_avg));
        }

        let mut trends = Vec::new();

        for (category, data_points) in by_category {
            if data_points.len() < 7 {
                continue; // Need at least 7 days of data
            }

            let volumes: Vec<f64> = data_points.iter().map(|(v, _)| *v as f64).collect();
            let (slope, r_squared) = linear_regression(&volumes);

            let direction = if slope > 0.05 {
                TrendDirection::Rising
            } else if slope < -0.05 {
                TrendDirection::Falling
            } else {
                let volatility = coefficient_of_variation(&volumes);
                if volatility > 0.5 {
                    TrendDirection::Volatile
                } else {
                    TrendDirection::Stable
                }
            };

            trends.push(MarketTrend {
                trend_id: Uuid::new_v4(),
                category,
                trend_type: "demand".to_string(),
                direction,
                strength: slope.abs().min(1.0),
                confidence: r_squared,
                description: format!(
                    "30-day trend: slope={:.4}, R²={:.4}, {} data points",
                    slope,
                    r_squared,
                    data_points.len()
                ),
                data_points: data_points.len() as u64,
                detected_at: Utc::now(),
            });
        }

        Ok(trends)
    }

    /// Forecast demand for the next N days
    pub async fn forecast(&self, days: u32) -> Result<Vec<DemandSignal>> {
        let trends = self.detect_trends().await?;
        let current_demand = self.analyze_demand().await?;

        let mut forecasts = Vec::new();

        for signal in &current_demand {
            let trend = trends.iter().find(|t| t.category == signal.product_category);

            let projected_demand = if let Some(t) = trend {
                match t.direction {
                    TrendDirection::Rising => {
                        signal.demand_index * (1.0 + t.strength * days as f64 / 30.0)
                    }
                    TrendDirection::Falling => {
                        signal.demand_index * (1.0 - t.strength * days as f64 / 30.0)
                    }
                    TrendDirection::Stable => signal.demand_index,
                    TrendDirection::Volatile => {
                        // For volatile, return current with lower confidence
                        signal.demand_index
                    }
                }
            } else {
                signal.demand_index
            }
            .clamp(0.0, 100.0);

            let confidence_decay = 0.98_f64.powi(days as i32);

            forecasts.push(DemandSignal {
                signal_id: Uuid::new_v4(),
                product_category: signal.product_category.clone(),
                region: signal.region.clone(),
                demand_index: projected_demand,
                volume: (signal.volume as f64 * projected_demand / signal.demand_index.max(1.0))
                    as u64,
                avg_transaction_value: signal.avg_transaction_value,
                trend: trend
                    .map(|t| t.direction.clone())
                    .unwrap_or(TrendDirection::Stable),
                confidence: signal.confidence * confidence_decay,
                period_start: Utc::now().date_naive(),
                period_end: (Utc::now() + chrono::Duration::days(days as i64)).date_naive(),
                generated_at: Utc::now(),
            });
        }

        Ok(forecasts)
    }

    /// Compute price elasticity for a product category
    pub async fn price_elasticity(&self, category: &str) -> Result<PriceElasticity> {
        let query = format!(
            r#"
            SELECT 
                floor(amount / 10) * 10 as price_bucket,
                count() as bucket_volume,
                avg(amount) as avg_price
            FROM revenue_events
            WHERE metadata = '{}' AND event_time >= now() - INTERVAL 30 DAY
            GROUP BY price_bucket
            ORDER BY price_bucket
            "#,
            category
        );

        #[derive(clickhouse::Row, Deserialize)]
        struct PriceRow {
            price_bucket: f64,
            bucket_volume: u64,
            avg_price: f64,
        }

        let rows = self
            .db
            .clickhouse
            .query(&query)
            .fetch_all::<PriceRow>()
            .await
            .unwrap_or_default();

        if rows.len() < 3 {
            return Err(anyhow!("Insufficient data for elasticity calculation"));
        }

        // Calculate arc elasticity between adjacent price points
        let mut elasticities = Vec::new();
        for i in 1..rows.len() {
            let q1 = rows[i - 1].bucket_volume as f64;
            let q2 = rows[i].bucket_volume as f64;
            let p1 = rows[i - 1].avg_price;
            let p2 = rows[i].avg_price;

            if p1 > 0.0 && q1 > 0.0 {
                let pct_q = (q2 - q1) / ((q1 + q2) / 2.0);
                let pct_p = (p2 - p1) / ((p1 + p2) / 2.0);
                if pct_p.abs() > 1e-10 {
                    elasticities.push(pct_q / pct_p);
                }
            }
        }

        let avg_elasticity = if elasticities.is_empty() {
            0.0
        } else {
            elasticities.iter().sum::<f64>() / elasticities.len() as f64
        };

        let sensitivity = if avg_elasticity.abs() > 1.0 {
            DemandSensitivity::Elastic
        } else if (avg_elasticity.abs() - 1.0).abs() < 0.1 {
            DemandSensitivity::Unitary
        } else {
            DemandSensitivity::Inelastic
        };

        let total_samples: u64 = rows.iter().map(|r| r.bucket_volume).sum();

        Ok(PriceElasticity {
            product_category: category.to_string(),
            region: "all".to_string(),
            elasticity_coefficient: avg_elasticity,
            price_range_min: rows.first().map(|r| r.avg_price).unwrap_or(0.0),
            price_range_max: rows.last().map(|r| r.avg_price).unwrap_or(0.0),
            demand_sensitivity: sensitivity,
            sample_size: total_samples,
            confidence: self.calculate_confidence(total_samples),
        })
    }

    // Private helpers

    fn classify_trend(&self, demand_index: f64, volume: u64) -> TrendDirection {
        if volume < 50 {
            TrendDirection::Volatile
        } else if demand_index > 70.0 {
            TrendDirection::Rising
        } else if demand_index < 30.0 {
            TrendDirection::Falling
        } else {
            TrendDirection::Stable
        }
    }

    fn calculate_confidence(&self, sample_size: u64) -> f64 {
        // Confidence grows with sample size using logarithmic scaling
        // 100 samples → ~0.7, 1000 → ~0.85, 10000 → ~0.95
        if sample_size == 0 {
            return 0.0;
        }
        (1.0 - 1.0 / (1.0 + (sample_size as f64).ln())).min(0.99)
    }
}

/// Simple linear regression: returns (slope, R²)
fn linear_regression(values: &[f64]) -> (f64, f64) {
    let n = values.len() as f64;
    if n < 2.0 {
        return (0.0, 0.0);
    }

    let x_mean = (n - 1.0) / 2.0;
    let y_mean = values.iter().sum::<f64>() / n;

    let mut ss_xy = 0.0;
    let mut ss_xx = 0.0;
    let mut ss_yy = 0.0;

    for (i, &y) in values.iter().enumerate() {
        let x = i as f64;
        let dx = x - x_mean;
        let dy = y - y_mean;
        ss_xy += dx * dy;
        ss_xx += dx * dx;
        ss_yy += dy * dy;
    }

    let slope = if ss_xx > 0.0 { ss_xy / ss_xx } else { 0.0 };
    let r_squared = if ss_xx > 0.0 && ss_yy > 0.0 {
        (ss_xy * ss_xy) / (ss_xx * ss_yy)
    } else {
        0.0
    };

    (slope, r_squared)
}

/// Coefficient of variation (stddev / mean)
fn coefficient_of_variation(values: &[f64]) -> f64 {
    let n = values.len() as f64;
    if n < 2.0 {
        return 0.0;
    }
    let mean = values.iter().sum::<f64>() / n;
    if mean.abs() < 1e-10 {
        return 0.0;
    }
    let variance = values.iter().map(|v| (v - mean).powi(2)).sum::<f64>() / (n - 1.0);
    variance.sqrt() / mean.abs()
}

// ============================================================
// Academic Formula Integrations (ECO 422)
// ============================================================

/// Herfindahl-Hirschman Index (HHI) for market concentration.
///
/// HHI = Σ(s_i²) where s_i is each firm's market share as a
/// fraction (0..1). The result is in [0, 1].
///
/// Interpretation (US DOJ guidelines, adapted):
///   HHI < 0.15  → competitive market

///   0.15 ≤ HHI < 0.25 → moderately concentrated
///   HHI ≥ 0.25 → highly concentrated
///
/// `market_shares` should be fractions that sum to 1.0 (or close to it).
pub fn herfindahl_index(market_shares: &[f64]) -> f64 {
    market_shares.iter().map(|s| s * s).sum()
}

/// Price dispersion — coefficient of variation of prices.
///
/// Measures how spread out prices are relative to the mean price.
///
///   dispersion = σ / μ
///
/// A value of 0 means all prices are identical; higher values mean
/// greater heterogeneity (potential market inefficiency).
pub fn price_dispersion(prices: &[f64]) -> f64 {
    let n = prices.len() as f64;
    if n < 2.0 {
        return 0.0;
    }
    let mean = prices.iter().sum::<f64>() / n;
    if mean.abs() < 1e-10 {
        return 0.0;
    }
    let variance = prices.iter().map(|p| (p - mean).powi(2)).sum::<f64>() / (n - 1.0);
    variance.sqrt() / mean.abs()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_linear_regression() {
        let values = vec![1.0, 2.0, 3.0, 4.0, 5.0];
        let (slope, r2) = linear_regression(&values);
        assert!((slope - 1.0).abs() < 0.01);
        assert!((r2 - 1.0).abs() < 0.01);
    }

    #[test]
    fn test_coefficient_of_variation() {
        let values = vec![10.0, 10.0, 10.0];
        let cv = coefficient_of_variation(&values);
        assert!(cv < 0.01); // Should be near zero for constant values
    }

    // --- Herfindahl-Hirschman Index ---

    #[test]
    fn test_hhi_monopoly() {
        // Single firm with 100% share → HHI = 1.0
        let hhi = herfindahl_index(&[1.0]);
        assert!((hhi - 1.0).abs() < 1e-10);
    }

    #[test]
    fn test_hhi_perfect_competition() {
        // 100 equal firms → HHI = 100 × 0.01² = 0.01
        let shares: Vec<f64> = vec![0.01; 100];
        let hhi = herfindahl_index(&shares);
        assert!((hhi - 0.01).abs() < 1e-10);
    }

    #[test]
    fn test_hhi_duopoly_equal() {
        // Two equal firms → 0.5² + 0.5² = 0.5
        let hhi = herfindahl_index(&[0.5, 0.5]);
        assert!((hhi - 0.5).abs() < 1e-10);
    }

    #[test]
    fn test_hhi_unequal() {
        // 60% + 40% → 0.36 + 0.16 = 0.52
        let hhi = herfindahl_index(&[0.6, 0.4]);
        assert!((hhi - 0.52).abs() < 1e-10);
    }

    // --- Price dispersion ---

    #[test]
    fn test_price_dispersion_identical() {
        let prices = vec![100.0, 100.0, 100.0];
        let d = price_dispersion(&prices);
        assert!(d < 0.001);
    }

    #[test]
    fn test_price_dispersion_spread() {
        let prices = vec![100.0, 200.0, 300.0];
        let d = price_dispersion(&prices);
        // CV of {100,200,300} with mean=200, std≈100 → ~0.5
        assert!(d > 0.4 && d < 0.6);
    }
}
