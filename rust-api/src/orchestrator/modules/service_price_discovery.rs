use uuid::Uuid;
// src/orchestrator/modules/service_price_discovery.rs
//
// ServicePriceDiscoveryEngine: Processes ServicePriceBroadcast events,
// generates ServiceMarketSignal outputs, persists to PostgreSQL.

use super::*;
use crate::orchestrator::message_bus::*;
use crate::service_pricing::*;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// ServicePriceDiscoveryEngine
///
/// Processes incoming ServicePriceBroadcast events from devices,
/// aggregates them into service market signals, and persists
/// everything to PostgreSQL for cross-restart survival.
///
/// Tables used:
/// - service_price_broadcasts (raw incoming data)
/// - service_prices (aggregated signals)
pub struct ServicePriceDiscoveryEngine {
    /// Pending broadcasts keyed by (category, type, region)
    pending_broadcasts: HashMap<String, Vec<AggregatedBroadcast>>,
    /// Latest computed signals keyed by (category, type, region)
    signals: HashMap<String, ServiceMarketSignal>,
    /// Database pool for persistence
    pool: Option<sqlx::PgPool>,
    /// Minimum broadcasts before generating a signal
    min_broadcasts: u32,
}

#[derive(Serialize, Deserialize, Clone)]
struct AggregatedBroadcast {
    price_midpoint: f64,
    unit: String,
    recorded_at: chrono::DateTime<chrono::Utc>,
}

impl ServicePriceDiscoveryEngine {
    pub fn new() -> Self {
        Self {
            pending_broadcasts: HashMap::new(),
            signals: HashMap::new(),
            pool: None,
            min_broadcasts: 10, // k-anonymity: need ≥10 data points
        }
    }

    /// Create with database pool for persistence.
    pub fn with_pool(pool: sqlx::PgPool) -> Self {
        Self {
            pending_broadcasts: HashMap::new(),
            signals: HashMap::new(),
            pool: Some(pool),
            min_broadcasts: 10,
        }
    }

    /// Load persisted state from PostgreSQL on startup.
    pub async fn load_state(&mut self) -> Result<(), String> {
        let pool = match &self.pool {
            Some(p) => p,
            None => return Ok(()),
        };

        // Load aggregated signals
        let rows = sqlx::query!(
            "SELECT service_category, service_type, region,
                    price_avg, price_min, price_max, price_trend,
                    demand_velocity, volatility, sample_size,
                    factors::text as \"factors!\"
             FROM service_prices"
        )
        .fetch_all(pool)
        .await
        .map_err(|e| format!("Failed to load service_prices: {}", e))?;

        let mut count = 0;
        for row in rows {
            let key = format!(
                "{}:{}:{}",
                row.service_category, row.service_type, row.region
            );
            let factors: Vec<PricingFactor> =
                serde_json::from_str(&row.factors).unwrap_or_default();

            let category = match row.service_category.as_str() {
                "Transport" => ServiceCategory::Transport,
                "Construction" => ServiceCategory::Construction,
                "Beauty" => ServiceCategory::Beauty,
                "Repair" => ServiceCategory::Repair,
                "Entertainment" => ServiceCategory::Entertainment,
                "Cleaning" => ServiceCategory::Cleaning,
                other => ServiceCategory::Other(other.to_string()),
            };

            self.signals.insert(
                key,
                ServiceMarketSignal {
                    signal_id: uuid::Uuid::new_v4(),
                    service_category: category,
                    service_type: row.service_type,
                    region: row.region,
                    price_avg: row.price_avg,
                    price_min: row.price_min,
                    price_max: row.price_max,
                    price_trend: row.price_trend,
                    demand_velocity: row.demand_velocity,
                    volatility: row.volatility,
                    sample_size: row.sample_size as u32,
                    factors,
                    updated_at: chrono::Utc::now(),
                },
            );
            count += 1;
        }

        // Load unprocessed broadcasts for re-aggregation
        let broadcasts = sqlx::query!(
            "SELECT service_category, service_type, region, price_midpoint, unit, recorded_at
             FROM service_price_broadcasts
             WHERE processed = FALSE
             ORDER BY recorded_at DESC
             LIMIT 10000"
        )
        .fetch_all(pool)
        .await
        .map_err(|e| format!("Failed to load unprocessed broadcasts: {}", e))?;

        let mut broadcast_count = 0;
        for row in broadcasts {
            let key = format!(
                "{}:{}:{}",
                row.service_category, row.service_type, row.region
            );
            self.pending_broadcasts
                .entry(key)
                .or_insert_with(Vec::new)
                .push(AggregatedBroadcast {
                    price_midpoint: row.price_midpoint,
                    unit: row.unit,
                    recorded_at: row.recorded_at,
                });
            broadcast_count += 1;
        }

        tracing::info!(
            signals = count,
            pending_broadcasts = broadcast_count,
            "ServicePriceDiscoveryEngine state loaded from PostgreSQL"
        );
        Ok(())
    }

    /// Persist current state to PostgreSQL.
    pub async fn persist_state(&self) -> Result<(), String> {
        let pool = match &self.pool {
            Some(p) => p,
            None => return Ok(()),
        };

        // Upsert all current signals
        for (key, signal) in &self.signals {
            let parts: Vec<&str> = key.splitn(3, ':').collect();
            if parts.len() != 3 {
                continue;
            }

            let factors_json = serde_json::to_string(&signal.factors).unwrap_or_default();
            let category_str = match &signal.service_category {
                ServiceCategory::Transport => "Transport",
                ServiceCategory::Construction => "Construction",
                ServiceCategory::Beauty => "Beauty",
                ServiceCategory::Repair => "Repair",
                ServiceCategory::Entertainment => "Entertainment",
                ServiceCategory::Cleaning => "Cleaning",
                ServiceCategory::Other(s) => s.as_str(),
            };

            sqlx::query!(
                "INSERT INTO service_prices
                    (service_category, service_type, region,
                     price_avg, price_min, price_max, price_trend,
                     demand_velocity, volatility, sample_size, factors,
                     broadcast_count, last_updated)
                 VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb, $12, NOW())
                 ON CONFLICT (service_category, service_type, region) DO UPDATE SET
                    price_avg = EXCLUDED.price_avg,
                    price_min = EXCLUDED.price_min,
                    price_max = EXCLUDED.price_max,
                    price_trend = EXCLUDED.price_trend,
                    demand_velocity = EXCLUDED.demand_velocity,
                    volatility = EXCLUDED.volatility,
                    sample_size = EXCLUDED.sample_size,
                    factors = EXCLUDED.factors,
                    broadcast_count = EXCLUDED.broadcast_count,
                    last_updated = NOW()",
                category_str,
                signal.service_type,
                signal.region,
                signal.price_avg,
                signal.price_min,
                signal.price_max,
                signal.price_trend,
                signal.demand_velocity,
                signal.volatility,
                signal.sample_size as i32,
                factors_json,
                signal.sample_size as i32,
            )
            .execute(pool)
            .await
            .map_err(|e| format!("Failed to persist service_prices: {}", e))?;
        }

        tracing::info!(
            signals = self.signals.len(),
            "ServicePriceDiscoveryEngine state persisted"
        );
        Ok(())
    }

    /// Parse a price bucket string (e.g., "100-200") into a midpoint.
    fn parse_price_bucket(bucket: &str) -> f64 {
        let parts: Vec<&str> = bucket.split('-').collect();
        if parts.len() == 2 {
            let lo: f64 = parts[0].parse().unwrap_or(0.0);
            let hi: f64 = parts[1].parse().unwrap_or(0.0);
            (lo + hi) / 2.0
        } else {
            bucket.parse().unwrap_or(0.0)
        }
    }

    /// Store a raw broadcast to PostgreSQL.
    async fn store_broadcast(
        &self,
        broadcast: &ServicePriceBroadcast,
        price_midpoint: f64,
    ) -> Result<(), String> {
        let pool = match &self.pool {
            Some(p) => p,
            None => return Ok(()),
        };

        let category_str = match &broadcast.service_category {
            ServiceCategory::Transport => "Transport",
            ServiceCategory::Construction => "Construction",
            ServiceCategory::Beauty => "Beauty",
            ServiceCategory::Repair => "Repair",
            ServiceCategory::Entertainment => "Entertainment",
            ServiceCategory::Cleaning => "Cleaning",
            ServiceCategory::Other(s) => s.as_str(),
        };

        sqlx::query!(
            "INSERT INTO service_price_broadcasts
                (broadcast_id, worker_id_hash, service_category, service_type,
                 region, price_bucket, price_midpoint, unit, recorded_at, processed)
             VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, FALSE)
             ON CONFLICT (broadcast_id) DO NOTHING",
            broadcast.broadcast_id,
            broadcast.worker_id,
            category_str,
            broadcast.service_type,
            broadcast.region,
            broadcast.price_bucket,
            price_midpoint,
            broadcast.unit,
            broadcast.timestamp,
        )
        .execute(pool)
        .await
        .map_err(|e| format!("Failed to store broadcast: {}", e))?;

        Ok(())
    }

    /// Compute a ServiceMarketSignal from aggregated broadcasts.
    fn compute_signal(
        &self,
        category: &ServiceCategory,
        service_type: &str,
        region: &str,
        broadcasts: &[AggregatedBroadcast],
    ) -> Option<ServiceMarketSignal> {
        if broadcasts.len() < self.min_broadcasts as usize {
            return None;
        }

        let prices: Vec<f64> = broadcasts.iter().map(|b| b.price_midpoint).collect();
        let n = prices.len() as f64;

        let price_avg = prices.iter().sum::<f64>() / n;
        let price_min = prices.iter().cloned().fold(f64::INFINITY, f64::min);
        let price_max = prices.iter().cloned().fold(f64::NEG_INFINITY, f64::max);

        // Volatility (CV)
        let variance =
            prices.iter().map(|p| (p - price_avg).powi(2)).sum::<f64>() / (n - 1.0).max(1.0);
        let stddev = variance.sqrt();
        let volatility = if price_avg > 0.0 {
            stddev / price_avg
        } else {
            0.0
        };

        // Price trend: compare recent vs older half
        let price_trend = if prices.len() >= 4 {
            let mid = prices.len() / 2;
            let older_avg: f64 = prices[..mid].iter().sum::<f64>() / mid as f64;
            let recent_avg: f64 = prices[mid..].iter().sum::<f64>() / (prices.len() - mid) as f64;
            if older_avg > 0.0 {
                ((recent_avg - older_avg) / older_avg).clamp(-1.0, 1.0)
            } else {
                0.0
            }
        } else {
            0.0
        };

        // Demand velocity: broadcasts per hour (proxy)
        let time_span_hours = if broadcasts.len() >= 2 {
            let newest = broadcasts.iter().map(|b| b.recorded_at).max().unwrap();
            let oldest = broadcasts.iter().map(|b| b.recorded_at).min().unwrap();
            newest.signed_duration_since(oldest).num_hours().max(1) as f64
        } else {
            1.0
        };
        let demand_velocity = n / time_span_hours;

        // Build pricing factors
        let mut factors = Vec::new();
        if volatility > 0.15 {
            factors.push(PricingFactor::DemandSurge {
                reason: "High price volatility detected".to_string(),
                multiplier: 1.0 + volatility,
            });
        }

        Some(ServiceMarketSignal {
            signal_id: uuid::Uuid::new_v4(),
            service_category: category.clone(),
            service_type: service_type.to_string(),
            region: region.to_string(),
            price_avg,
            price_min,
            price_max,
            price_trend,
            demand_velocity,
            volatility,
            sample_size: broadcasts.len() as u32,
            factors,
            updated_at: chrono::Utc::now(),
        })
    }

    /// Mark broadcasts as processed for a given key.
    async fn mark_processed(&self, key: &str) -> Result<(), String> {
        let pool = match &self.pool {
            Some(p) => p,
            None => return Ok(()),
        };

        let parts: Vec<&str> = key.splitn(3, ':').collect();
        if parts.len() != 3 {
            return Ok(());
        }

        sqlx::query!(
            "UPDATE service_price_broadcasts SET processed = TRUE
             WHERE service_category = $1 AND service_type = $2 AND region = $3
               AND processed = FALSE",
            parts[0],
            parts[1],
            parts[2],
        )
        .execute(pool)
        .await
        .map_err(|e| format!("Failed to mark broadcasts processed: {}", e))?;

        Ok(())
    }
}

#[async_trait::async_trait]
impl CapabilityModule for ServicePriceDiscoveryEngine {
    fn id(&self) -> ModuleId {
        // Use a new ModuleId variant; must be added to message_bus.rs
        ModuleId::ServicePriceDiscovery
    }

    async fn process(
        &mut self,
        message: ModuleMessage,
    ) -> Result<Option<ModuleMessage>, ModuleError> {
        match message {
            ModuleMessage::ServicePriceBroadcast {
                trace_id,
                broadcast,
            } => {
                let price_midpoint = Self::parse_price_bucket(&broadcast.price_bucket);

                // Store raw broadcast
                if let Err(e) = self.store_broadcast(&broadcast, price_midpoint).await {
                    tracing::error!("Failed to store broadcast: {}", e);
                }

                // Add to pending aggregation
                let category_str = match &broadcast.service_category {
                    ServiceCategory::Transport => "Transport",
                    ServiceCategory::Construction => "Construction",
                    ServiceCategory::Beauty => "Beauty",
                    ServiceCategory::Repair => "Repair",
                    ServiceCategory::Entertainment => "Entertainment",
                    ServiceCategory::Cleaning => "Cleaning",
                    ServiceCategory::Other(s) => s.as_str(),
                };
                let key = format!(
                    "{}:{}:{}",
                    category_str, broadcast.service_type, broadcast.region
                );

                self.pending_broadcasts
                    .entry(key.clone())
                    .or_insert_with(Vec::new)
                    .push(AggregatedBroadcast {
                        price_midpoint,
                        unit: broadcast.unit.clone(),
                        recorded_at: broadcast.timestamp,
                    });

                // Try to compute a signal
                if let Some(broadcasts) = self.pending_broadcasts.get(&key) {
                    if let Some(signal) = self.compute_signal(
                        &broadcast.service_category,
                        &broadcast.service_type,
                        &broadcast.region,
                        broadcasts,
                    ) {
                        // Mark broadcasts as processed
                        if let Err(e) = self.mark_processed(&key).await {
                            tracing::error!("Failed to mark processed: {}", e);
                        }

                        let result = ModuleMessage::ServiceMarketSignal {
                            trace_id,
                            signal: signal.clone(),
                        };

                        self.signals.insert(key, signal);
                        return Ok(Some(result));
                    }
                }

                Ok(None)
            }
            ModuleMessage::RouteCommand {
                command: ModuleCommand::Recalculate,
                ..
            } => {
                // Recompute all signals from pending broadcasts
                let mut last_signal = None;
                let keys: Vec<String> = self.pending_broadcasts.keys().cloned().collect();
                for key in keys {
                    let parts: Vec<&str> = key.splitn(3, ':').collect();
                    if parts.len() != 3 {
                        continue;
                    }

                    let category = match parts[0] {
                        "Transport" => ServiceCategory::Transport,
                        "Construction" => ServiceCategory::Construction,
                        "Beauty" => ServiceCategory::Beauty,
                        "Repair" => ServiceCategory::Repair,
                        "Entertainment" => ServiceCategory::Entertainment,
                        "Cleaning" => ServiceCategory::Cleaning,
                        other => ServiceCategory::Other(other.to_string()),
                    };

                    if let Some(broadcasts) = self.pending_broadcasts.get(&key) {
                        if let Some(signal) =
                            self.compute_signal(&category, parts[1], parts[2], broadcasts)
                        {
                            if let Err(e) = self.mark_processed(&key).await {
                                tracing::error!("Failed to mark processed: {}", e);
                            }
                            last_signal = Some(ModuleMessage::ServiceMarketSignal {
                                trace_id: uuid::Uuid::new_v4(),
                                signal: signal.clone(),
                            });
                            self.signals.insert(key, signal);
                        }
                    }
                }
                Ok(last_signal)
            }
            _ => Ok(None),
        }
    }

    async fn shutdown(&self) {
        tracing::info!(
            "ServicePriceDiscoveryEngine shutting down, {} signals active",
            self.signals.len()
        );
        if let Err(e) = self.persist_state().await {
            tracing::error!("Failed to persist ServicePriceDiscoveryEngine state: {}", e);
        }
    }

    fn snapshot_state(&self) -> Option<Vec<u8>> {
        #[derive(Serialize)]
        struct Snapshot {
            pending_broadcasts: HashMap<String, Vec<AggregatedBroadcast>>,
            signals: HashMap<String, ServiceMarketSignal>,
        }
        bincode::serialize(&Snapshot {
            pending_broadcasts: self.pending_broadcasts.clone(),
            signals: self.signals.clone(),
        })
        .ok()
    }

    fn restore_state(&mut self, data: &[u8]) {
        #[derive(Deserialize)]
        struct Snapshot {
            pending_broadcasts: HashMap<String, Vec<AggregatedBroadcast>>,
            signals: HashMap<String, ServiceMarketSignal>,
        }
        if let Ok(snap) = bincode::deserialize::<Snapshot>(data) {
            self.pending_broadcasts = snap.pending_broadcasts;
            self.signals = snap.signals;
            tracing::info!(
                signals = self.signals.len(),
                "ServicePriceDiscoveryEngine state restored (fallback bincode)"
            );
        }
    }
}
