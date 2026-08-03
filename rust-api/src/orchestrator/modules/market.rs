// src/orchestrator/modules/market.rs
//
// MarketAnalyzer: Demand pattern analysis, Soko Pulse generation
// State persisted to PostgreSQL (table: market_windows).

use super::*;
use crate::orchestrator::message_bus::*;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// MarketAnalyzer: Demand pattern analysis, Soko Pulse generation
///
/// Processes transaction batches and produces market signals:
/// - Demand indices per product per region
/// - Price trends and volatility
/// - Seasonal patterns
/// - Market concentration (HHI)
///
/// State is persisted to PostgreSQL (table: market_windows) for
/// survival across process restarts.
pub struct MarketAnalyzer {
    /// Rolling window of recent aggregates per (region, product) key
    windows: HashMap<String, RollingWindow>,
    /// Minimum sample size for a valid signal
    min_sample_size: u32,
    /// Database pool for state persistence
    pool: Option<sqlx::PgPool>,
}

#[derive(Serialize, Deserialize, Clone)]
struct RollingWindow {
    prices: Vec<f64>,
    volumes: Vec<f64>,
    timestamps: Vec<chrono::DateTime<chrono::Utc>>,
    max_size: usize,
}

/// JSONB-serializable window for PostgreSQL storage
#[derive(Serialize, Deserialize)]
struct WindowRow {
    region: String,
    product_category: String,
    prices: Vec<f64>,
    volumes: Vec<f64>,
    timestamps: Vec<chrono::DateTime<chrono::Utc>>,
    max_size: i32,
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
        if self.prices.is_empty() {
            return 0.0;
        }
        self.prices.iter().sum::<f64>() / self.prices.len() as f64
    }

    fn price_stddev(&self) -> f64 {
        if self.prices.len() < 2 {
            return 0.0;
        }
        let mean = self.mean_price();
        let variance = self.prices.iter().map(|p| (p - mean).powi(2)).sum::<f64>()
            / (self.prices.len() - 1) as f64;
        variance.sqrt()
    }

    fn price_trend(&self) -> PriceTrend {
        if self.prices.len() < 3 {
            return PriceTrend::Stable;
        }

        let n = self.prices.len();
        let recent = &self.prices[n - 3..];
        let older_len = n.saturating_sub(3).max(3);
        let older = &self.prices[..older_len.min(n)];

        let recent_avg: f64 = recent.iter().sum::<f64>() / recent.len() as f64;
        let older_avg: f64 = older.iter().sum::<f64>() / older.len() as f64;

        if older_avg == 0.0 {
            return PriceTrend::Stable;
        }

        let change_pct = ((recent_avg - older_avg) / older_avg) * 100.0;
        let volatility = self.price_stddev() / self.mean_price().max(0.01) * 100.0;

        if volatility > 15.0 {
            PriceTrend::Volatile {
                range_pct: volatility,
            }
        } else if change_pct > 5.0 {
            PriceTrend::Rising {
                rate_pct: change_pct,
            }
        } else if change_pct < -5.0 {
            PriceTrend::Falling {
                rate_pct: change_pct.abs(),
            }
        } else {
            PriceTrend::Stable
        }
    }

    /// Herfindahl-Hirschman Index for market concentration
    fn compute_hhi(&self, market_shares: &[f64]) -> f64 {
        market_shares.iter().map(|s| (s * 100.0).powi(2)).sum()
    }

    /// Shannon entropy for market diversity
    fn compute_entropy(&self, market_shares: &[f64]) -> f64 {
        -market_shares
            .iter()
            .filter(|&&s| s > 0.0)
            .map(|&s| s * s.ln())
            .sum::<f64>()
    }
}

impl MarketAnalyzer {
    pub fn new() -> Self {
        Self {
            windows: HashMap::new(),
            min_sample_size: 10,
            pool: None,
        }
    }

    /// Create with database pool for state persistence.
    pub fn with_pool(pool: sqlx::PgPool) -> Self {
        Self {
            windows: HashMap::new(),
            min_sample_size: 10,
            pool: Some(pool),
        }
    }

    /// Load persisted state from PostgreSQL on startup.
    pub async fn load_state(&mut self) -> Result<(), String> {
        let pool = match &self.pool {
            Some(p) => p,
            None => return Ok(()),
        };

        // Use JSONB -> text casting for reliable serde
        let rows = sqlx::query!(
            "SELECT region, product_category,
                    prices::text as \"prices!\",
                    volumes::text as \"volumes!\",
                    timestamps::text as \"timestamps!\",
                    max_size
             FROM market_windows"
        )
        .fetch_all(pool)
        .await
        .map_err(|e| format!("Failed to load market_windows: {}", e))?;

        let mut count = 0;
        for row in rows {
            let key = format!("{}:{}", row.region, row.product_category);
            let prices: Vec<f64> = serde_json::from_str(&row.prices).unwrap_or_default();
            let volumes: Vec<f64> = serde_json::from_str(&row.volumes).unwrap_or_default();
            let timestamps: Vec<chrono::DateTime<chrono::Utc>> =
                serde_json::from_str(&row.timestamps).unwrap_or_default();

            let window = RollingWindow {
                prices,
                volumes,
                timestamps,
                max_size: row.max_size as usize,
            };
            if !window.prices.is_empty() {
                self.windows.insert(key, window);
                count += 1;
            }
        }

        tracing::info!(
            windows = count,
            "MarketAnalyzer state loaded from PostgreSQL"
        );
        Ok(())
    }

    /// Persist current state to PostgreSQL.
    pub async fn persist_state(&self) -> Result<(), String> {
        let pool = match &self.pool {
            Some(p) => p,
            None => return Ok(()),
        };

        for (key, window) in &self.windows {
            let parts: Vec<&str> = key.splitn(2, ':').collect();
            if parts.len() != 2 {
                continue;
            }
            let (region, category) = (parts[0], parts[1]);

            let prices_json = serde_json::to_string(&window.prices).unwrap_or_default();
            let volumes_json = serde_json::to_string(&window.volumes).unwrap_or_default();
            let timestamps_json = serde_json::to_string(&window.timestamps).unwrap_or_default();

            sqlx::query!(
                "INSERT INTO market_windows
                    (region, product_category, prices, volumes, timestamps, max_size,
                     mean_price, price_stddev, last_updated)
                 VALUES ($1, $2, $3::jsonb, $4::jsonb, $5::jsonb, $6, $7, $8, NOW())
                 ON CONFLICT (region, product_category) DO UPDATE SET
                    prices = EXCLUDED.prices,
                    volumes = EXCLUDED.volumes,
                    timestamps = EXCLUDED.timestamps,
                    max_size = EXCLUDED.max_size,
                    mean_price = EXCLUDED.mean_price,
                    price_stddev = EXCLUDED.price_stddev,
                    last_updated = NOW()",
                region,
                category,
                prices_json,
                volumes_json,
                timestamps_json,
                window.max_size as i32,
                window.mean_price(),
                window.price_stddev(),
            )
            .execute(pool)
            .await
            .map_err(|e| format!("Failed to persist market_windows: {}", e))?;
        }

        tracing::info!(
            windows = self.windows.len(),
            "MarketAnalyzer state persisted to PostgreSQL"
        );
        Ok(())
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
                let mut by_category: HashMap<String, Vec<&TransactionRecord>> = HashMap::new();
                for tx in &transactions {
                    by_category
                        .entry(tx.product_category.clone())
                        .or_default()
                        .push(tx);
                }

                let mut signals = Vec::new();
                for (category, txs) in &by_category {
                    if txs.len() < self.min_sample_size as usize {
                        continue;
                    }

                    let key = format!("{}:{}", region, category);
                    let window = self
                        .windows
                        .entry(key.clone())
                        .or_insert_with(|| RollingWindow::new(168));

                    let avg_price: f64 =
                        txs.iter().map(|t| t.amount).sum::<f64>() / txs.len() as f64;
                    let total_volume: f64 = txs.iter().map(|t| t.quantity.unwrap_or(1.0)).sum();

                    window.push(avg_price, total_volume, chrono::Utc::now());

                    let avg_volume =
                        window.volumes.iter().sum::<f64>() / window.volumes.len() as f64;
                    let demand_index = if avg_volume > 0.0 {
                        total_volume / avg_volume
                    } else {
                        1.0
                    };

                    let demand_se = if window.volumes.len() > 1 {
                        let vol_mean =
                            window.volumes.iter().sum::<f64>() / window.volumes.len() as f64;
                        let vol_var = window
                            .volumes
                            .iter()
                            .map(|v| (v - vol_mean).powi(2))
                            .sum::<f64>()
                            / (window.volumes.len() - 1) as f64;
                        vol_var.sqrt() / (window.volumes.len() as f64).sqrt()
                    } else {
                        demand_index * 0.5
                    };
                    let z_95 = 1.96;
                    let demand_ci_lower =
                        (demand_index - z_95 * demand_se / avg_volume.max(0.01)).max(0.0);
                    let demand_ci_upper = demand_index + z_95 * demand_se / avg_volume.max(0.01);

                    signals.push(ModuleMessage::MarketSignal {
                        trace_id,
                        region: region.clone(),
                        product_category: category.clone(),
                        demand_index,
                        price_trend: window.price_trend(),
                        volatility: window.price_stddev() / window.mean_price().max(0.01),
                        sample_size: txs.len() as u32,
                        confidence: (txs.len() as f64 / 100.0).min(1.0),
                        demand_ci_lower,
                        demand_ci_upper,
                    });
                }

                Ok(signals.into_iter().next())
            }
            ModuleMessage::RouteCommand {
                command: ModuleCommand::Recalculate,
                ..
            } => Ok(None),
            _ => Ok(None),
        }
    }

    async fn shutdown(&self) {
        tracing::info!(
            "MarketAnalyzer shutting down, {} windows active",
            self.windows.len()
        );
        if let Err(e) = self.persist_state().await {
            tracing::error!("Failed to persist MarketAnalyzer state on shutdown: {}", e);
        }
    }

    fn snapshot_state(&self) -> Option<Vec<u8>> {
        #[derive(Serialize)]
        struct Snapshot {
            windows: HashMap<String, RollingWindow>,
            min_sample_size: u32,
        }
        let snap = Snapshot {
            windows: self.windows.clone(),
            min_sample_size: self.min_sample_size,
        };
        bincode::serialize(&snap).ok()
    }

    fn restore_state(&mut self, data: &[u8]) {
        #[derive(Deserialize)]
        struct Snapshot {
            windows: HashMap<String, RollingWindow>,
            min_sample_size: u32,
        }
        if let Ok(snap) = bincode::deserialize::<Snapshot>(data) {
            self.windows = snap.windows;
            self.min_sample_size = snap.min_sample_size;
            tracing::info!(
                count = self.windows.len(),
                "MarketAnalyzer state restored (fallback bincode)"
            );
        }
    }
}
