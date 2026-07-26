// src/orchestrator/modules/fmcg.rs

use super::*;
use crate::orchestrator::message_bus::*;
use std::collections::HashMap;

/// FMCGIntelligence: Manufacturer intelligence products
///
/// Generates reports for FMCG companies:
/// - Brand market share tracking
/// - Price elasticity estimation
/// - Demand forecasting
/// - Competitive positioning
pub struct FMCGIntelligence {
    /// Brand market data per (category, region)
    brand_data: HashMap<String, BrandTracker>,
    /// Price-demand pairs for elasticity estimation
    elasticity_data: HashMap<String, Vec<(f64, f64)>>, // (price, quantity)
}

struct BrandTracker {
    brand_volumes: HashMap<String, f64>,
    total_volume: f64,
    last_updated: chrono::DateTime<chrono::Utc>,
}

impl FMCGIntelligence {
    pub fn new() -> Self {
        Self {
            brand_data: HashMap::new(),
            elasticity_data: HashMap::new(),
        }
    }

    /// Estimate price elasticity using log-log regression
    /// Elasticity = % change in quantity / % change in price
    fn estimate_elasticity(&self, data: &[(f64, f64)]) -> f64 {
        if data.len() < 5 {
            return -1.0; // Default assumption: unit elastic
        }

        // Log-log OLS: ln(Q) = a + b * ln(P)
        // b = elasticity
        let n = data.len() as f64;
        let ln_p: Vec<f64> = data.iter().map(|(p, _)| p.ln()).collect();
        let ln_q: Vec<f64> = data.iter().map(|(_, q)| q.ln()).collect();

        let mean_ln_p: f64 = ln_p.iter().sum::<f64>() / n;
        let mean_ln_q: f64 = ln_q.iter().sum::<f64>() / n;

        let numerator: f64 = ln_p.iter().zip(ln_q.iter())
            .map(|(p, q)| (p - mean_ln_p) * (q - mean_ln_q))
            .sum();

        let denominator: f64 = ln_p.iter()
            .map(|p| (p - mean_ln_p).powi(2))
            .sum();

        if denominator.abs() < 1e-10 {
            -1.0
        } else {
            numerator / denominator
        }
    }
}

#[async_trait::async_trait]
impl CapabilityModule for FMCGIntelligence {
    fn id(&self) -> ModuleId {
        ModuleId::FMCGIntelligence
    }

    async fn process(
        &mut self,
        message: ModuleMessage,
    ) -> Result<Option<ModuleMessage>, ModuleError> {
        match message {
            ModuleMessage::TransactionBatch {
                trace_id,
                transactions,
                region,
                ..
            } => {
                // Track brand-level data
                for tx in &transactions {
                    let key = format!("{}:{}", region, tx.product_category);
                    let tracker = self.brand_data.entry(key.clone())
                        .or_insert_with(|| BrandTracker {
                            brand_volumes: HashMap::new(),
                            total_volume: 0.0,
                            last_updated: chrono::Utc::now(),
                        });

                    let brand = tx.product_name.clone().unwrap_or_else(|| "unknown".to_string());
                    let volume = tx.quantity.unwrap_or(1.0);

                    *tracker.brand_volumes.entry(brand).or_insert(0.0) += volume;
                    tracker.total_volume += volume;
                    tracker.last_updated = chrono::Utc::now();
                }

                Ok(None)
            }
            ModuleMessage::MarketSignal {
                trace_id,
                region,
                product_category,
                demand_index,
                price_trend,
                ..
            } => {
                let key = format!("{}:{}", region, product_category);

                // Update elasticity data
                if let PriceTrend::Rising { rate_pct } | PriceTrend::Falling { rate_pct } = &price_trend {
                    let data = self.elasticity_data.entry(key.clone())
                        .or_insert_with(Vec::new);
                    data.push((*rate_pct, demand_index));
                    if data.len() > 100 {
                        data.remove(0);
                    }
                }

                // Generate FMCG report if we have enough brand data
                if let Some(tracker) = self.brand_data.get(&key) {
                    if tracker.total_volume > 100.0 {
                        // Find top brand
                        let top_brand = tracker.brand_volumes.iter()
                            .max_by(|a, b| a.1.partial_cmp(b.1).unwrap())
                            .map(|(b, _)| b.clone())
                            .unwrap_or_else(|| "unknown".to_string());

                        let market_share = tracker.brand_volumes.get(&top_brand)
                            .copied()
                            .unwrap_or(0.0) / tracker.total_volume;

                        let elasticity = self.elasticity_data.get(&key)
                            .map(|d| self.estimate_elasticity(d))
                            .unwrap_or(-1.0);

                        // Build competitor analysis
                        let competitors: Vec<CompetitorData> = tracker.brand_volumes.iter()
                            .filter(|(b, _)| *b != &top_brand)
                            .map(|(brand, volume)| CompetitorData {
                                brand: brand.clone(),
                                market_share: volume / tracker.total_volume,
                                avg_price: 0.0, // Would need price per brand
                            })
                            .collect();

                        return Ok(Some(ModuleMessage::FMCGReport {
                            trace_id,
                            brand: top_brand,
                            category: product_category,
                            market_share,
                            price_elasticity: elasticity,
                            demand_forecast_30d: demand_index * 30.0, // Simplified
                            competitor_analysis: competitors,
                        }));
                    }
                }

                Ok(None)
            }
            _ => Ok(None),
        }
    }
}
