// src/orchestrator/modules/market.rs

use super::*;
use crate::orchestrator::message_bus::*;
use std::collections::HashMap;

/// MarketAnalyzer: Demand pattern analysis, Soko Pulse generation
///
/// Processes transaction batches and produces market signals:
/// - Demand indices per product per region
/// - Price trends and volatility
/// - Seasonal patterns
/// - Market concentration (HHI)
pub struct MarketAnalyzer {
    /// Rolling window of recent aggregates per (region, product) key
    windows: HashMap<String, RollingWindow>,
    /// Minimum sample size for a valid signal
    min_sample_size: u32,
}

struct RollingWindow {
    prices: Vec<f64>,
    volumes: Vec<f64>,
    timestamps: Vec<chrono::DateTime<chrono::Utc>>,
    max_size: usize,
}

impl RollingWindow {
    fn new(max_size: usize) -> Self {
        Self {
            prices: Vec::with_capacity(max_size),
            volumes: Vec::with_capacity(max_size),
            timestamps: Vec::with_capacity(max_size),
            max_size,
        }
    }

    fn push(&mut self, price: f64, volume: f64, ts: chrono::DateTime<chrono::Utc>) {
        if self.prices.len() >= self.max_size {
            self.prices.remove(0);
            self.volumes.remove(0);
            self.timestamps.remove(0);
        }
        self.prices.push(price);
        self.volumes.push(volume);
        self.timestamps.push(ts);
    }

    fn mean_price(&self) -> f64 {
        if self.prices.is_empty() { return 0.0; }
        self.prices.iter().sum::<f64>() / self.prices.len() as f64
    }

    fn price_stddev(&self) -> f64 {
        if self.prices.len() < 2 { return 0.0; }
        let mean = self.mean_price();
        let variance = self.prices.iter()
            .map(|p| (p - mean).powi(2))
            .sum::<f64>() / (self.prices.len() - 1) as f64;
        variance.sqrt()
    }

    fn price_trend(&self) -> PriceTrend {
        if self.prices.len() < 3 {
            return PriceTrend::Stable;
        }

        let n = self.prices.len();
        let recent = &self.prices[n - 3..];
        let older = &self.prices[..n - 3].max(3);

        let recent_avg: f64 = recent.iter().sum::<f64>() / recent.len() as f64;
        let older_avg: f64 = older.iter().sum::<f64>() / older.len() as f64;

        if older_avg == 0.0 {
            return PriceTrend::Stable;
        }

        let change_pct = ((recent_avg - older_avg) / older_avg) * 100.0;
        let volatility = self.price_stddev() / self.mean_price() * 100.0;

        if volatility > 15.0 {
            PriceTrend::Volatile { range_pct: volatility }
        } else if change_pct > 5.0 {
            PriceTrend::Rising { rate_pct: change_pct }
        } else if change_pct < -5.0 {
            PriceTrend::Falling { rate_pct: change_pct.abs() }
        } else {
            PriceTrend::Stable
        }
    }

    /// Herfindahl-Hirschman Index for market concentration
    fn compute_hhi(&self, market_shares: &[f64]) -> f64 {
        market_shares.iter().map(|s| (s * 100.0).powi(2)).sum()
    }
}

impl MarketAnalyzer {
    pub fn new() -> Self {
        Self {
            windows: HashMap::new(),
            min_sample_size: 10,
        }
    }
}

#[async_trait::async_trait]
impl CapabilityModule for MarketAnalyzer {
    fn id(&self) -> ModuleId {
        ModuleId::MarketAnalyzer
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
                // Group transactions by product category
                let mut by_category: HashMap<String, Vec<&TransactionRecord>> = HashMap::new();
                for tx in &transactions {
                    by_category.entry(tx.product_category.clone())
                        .or_default()
                        .push(tx);
                }

                // Generate a market signal for each category with enough data
                let mut signals = Vec::new();
                for (category, txs) in &by_category {
                    if txs.len() < self.min_sample_size as usize {
                        continue;
                    }

                    let key = format!("{}:{}", region, category);
                    let window = self.windows.entry(key.clone())
                        .or_insert_with(|| RollingWindow::new(168)); // 7 days of hourly data

                    // Aggregate this batch
                    let avg_price: f64 = txs.iter().map(|t| t.amount).sum::<f64>() / txs.len() as f64;
                    let total_volume: f64 = txs.iter()
                        .map(|t| t.quantity.unwrap_or(1.0))
                        .sum();

                    window.push(avg_price, total_volume, chrono::Utc::now());

                    // Compute demand index (volume relative to rolling average)
                    let avg_volume = window.volumes.iter().sum::<f64>() / window.volumes.len() as f64;
                    let demand_index = if avg_volume > 0.0 {
                        total_volume / avg_volume
                    } else {
                        1.0
                    };

                    signals.push(ModuleMessage::MarketSignal {
                        trace_id,
                        region: region.clone(),
                        product_category: category.clone(),
                        demand_index,
                        price_trend: window.price_trend(),
                        volatility: window.price_stddev() / window.mean_price().max(0.01),
                        sample_size: txs.len() as u32,
                        confidence: (txs.len() as f64 / 100.0).min(1.0),
                    });
                }

                // Return first signal (in production: return all or batch)
                Ok(signals.into_iter().next())
            }
            ModuleMessage::RouteCommand { command: ModuleCommand::Recalculate, .. } => {
                // Recalculate all windows — used during deep analysis
                Ok(None)
            }
            _ => Ok(None), // Ignore unrelated messages
        }
    }

    async fn shutdown(&self) {
        tracing::info!("MarketAnalyzer shutting down, {} windows active", self.windows.len());
    }
}
