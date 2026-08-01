// src/orchestrator/message_bus.rs

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

/// Unique identifier for tracing a request across all modules
pub type TraceId = Uuid;

/// Module identifiers
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum ModuleId {
    Orchestrator,
    MarketAnalyzer,
    CreditScorer,
    DistributionAnalyzer,
    FMCGIntelligence,
    HealthMetrics,
    EconomicAnalyzer,
    CollectiveIntelligence,
    ApiGateway,
    ServicePriceDiscovery,
}

/// Priority levels for task scheduling
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
pub enum Priority {
    /// System-level: health checks, heartbeats
    Low = 0,
    /// Normal operational: routine analysis, reports
    Normal = 1,
    /// High: buyer API queries, time-sensitive alerts
    High = 2,
    /// Critical: anomaly detection, security events
    Critical = 3,
}

/// Messages flowing between modules
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum ModuleMessage {
    // ── Data Ingestion ──────────────────────────────────────
    /// New transaction batch from a device sync
    TransactionBatch {
        trace_id: TraceId,
        worker_id_hash: String,
        transactions: Vec<TransactionRecord>,
        region: String,
        timestamp: DateTime<Utc>,
    },

    // ── Analysis Results ────────────────────────────────────
    /// MarketAnalyzer output: demand signals
    MarketSignal {
        trace_id: TraceId,
        region: String,
        product_category: String,
        demand_index: f64,
        price_trend: PriceTrend,
        volatility: f64,
        sample_size: u32,
        confidence: f64,
        /// 95% CI for demand_index
        demand_ci_lower: f64,
        demand_ci_upper: f64,
    },

    /// CreditScorer output: Alama Score components
    CreditAssessment {
        trace_id: TraceId,
        worker_id_hash: String,
        alama_score: u32,       // 300-850
        risk_level: RiskLevel,
        factors: Vec<CreditFactor>,
        confidence: f64,
        /// 95% confidence interval lower bound (Alama score units)
        ci_lower: u32,
        /// 95% confidence interval upper bound (Alama score units)
        ci_upper: u32,
        /// Number of observations used for scoring
        n_observations: u32,
    },

    /// DistributionAnalyzer output: distribution gaps
    DistributionGap {
        trace_id: TraceId,
        region: String,
        product_category: String,
        gap_severity: f64,      // 0.0 = no gap, 1.0 = severe
        opportunity_size_usd: f64,
        affected_workers: u32,
    },

    /// FMCGIntelligence output: manufacturer intelligence
    FMCGReport {
        trace_id: TraceId,
        brand: String,
        category: String,
        market_share: f64,
        price_elasticity: f64,
        demand_forecast_30d: f64,
        competitor_analysis: Vec<CompetitorData>,
        /// 95% CI for price_elasticity
        elasticity_ci_lower: f64,
        elasticity_ci_upper: f64,
        /// 95% CI for demand_forecast_30d
        forecast_ci_lower: f64,
        forecast_ci_upper: f64,
    },

    /// HealthMetrics output: worker health economics
    HealthAssessment {
        trace_id: TraceId,
        region: String,
        worker_type: String,
        income_stability_score: f64,
        health_risk_score: f64,
        insurance_eligibility: bool,
    },

    /// EconomicAnalyzer output: macro indicators
    EconomicIndicator {
        trace_id: TraceId,
        region: String,
        gdp_proxy: f64,
        inflation_rate: f64,
        employment_index: f64,
        transaction_volume_index: f64,
        period: String,
        /// 95% CI for gdp_proxy
        gdp_ci_lower: f64,
        gdp_ci_upper: f64,
        /// 95% CI for inflation_rate
        inflation_ci_lower: f64,
        inflation_ci_upper: f64,
    },

    // ── Cross-Module Signals ────────────────────────────────
    /// Anomaly detected by any module
    AnomalyAlert {
        trace_id: TraceId,
        source_module: ModuleId,
        anomaly_type: AnomalyType,
        severity: f64,
        description: String,
        affected_region: Option<String>,
    },

    /// Pattern discovered by CollectiveIntelligence
    EmergentPattern {
        trace_id: TraceId,
        pattern_type: PatternType,
        modules_involved: Vec<ModuleId>,
        correlation_strength: f64,
        description: String,
        actionable: bool,
    },

    /// Orchestrator routing command
    RouteCommand {
        trace_id: TraceId,
        target_module: ModuleId,
        command: ModuleCommand,
        priority: Priority,
    },

    /// Service price broadcast from device
    ServicePriceBroadcast {
        trace_id: TraceId,
        broadcast: crate::service_pricing::ServicePriceBroadcast,
    },

    /// ServicePriceDiscoveryEngine output: aggregated service market signal
    ServiceMarketSignal {
        trace_id: TraceId,
        signal: crate::service_pricing::ServiceMarketSignal,
    },

    /// Module health/heartbeat
    Heartbeat {
        module_id: ModuleId,
        queue_depth: u64,
        processing_rate: f64,   // messages/sec
        last_error: Option<String>,
        uptime_secs: u64,
    },
}

/// Transaction record from device sync
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TransactionRecord {
    pub id: Uuid,
    pub amount: f64,
    pub currency: String,
    pub product_category: String,
    pub product_name: Option<String>,
    pub quantity: Option<f64>,
    pub unit: Option<String>,
    pub payment_method: String,
    pub timestamp: DateTime<Utc>,
    pub confidence_score: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum PriceTrend {
    Rising { rate_pct: f64 },
    Falling { rate_pct: f64 },
    Stable,
    Volatile { range_pct: f64 },
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum RiskLevel {
    Low,
    Medium,
    High,
    VeryHigh,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CreditFactor {
    pub name: String,
    pub weight: f64,
    pub value: f64,
    pub direction: String, // "positive" or "negative"
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CompetitorData {
    pub brand: String,
    pub market_share: f64,
    pub avg_price: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum AnomalyType {
    PriceSpike,
    VolumeDrop,
    UnusualPattern,
    FraudSignal,
    ModelDrift,
    DataQualityIssue,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum PatternType {
    MarketCreditCorrelation,
    HealthEconomicLink,
    DistributionDemandMismatch,
    SeasonalEmergence,
    CrossRegionalTrend,
}

/// Commands the orchestrator can send to modules
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum ModuleCommand {
    /// Process a specific data batch
    ProcessBatch(Vec<TransactionRecord>),
    /// Recalculate using latest data
    Recalculate,
    /// Adjust model parameters
    TuneParameters { param: String, value: f64 },
    /// Pause processing (for backpressure)
    Pause,
    /// Resume processing
    Resume,
    /// Request current status
    StatusRequest,
}

// src/orchestrator/message_bus.rs (continued)

use dashmap::DashMap;
use std::sync::Arc;
use tokio::sync::{broadcast, mpsc, RwLock};
use tracing::{debug, error, info, warn};

/// Configuration for the message bus
#[derive(Debug, Clone)]
pub struct MessageBusConfig {
    /// Broadcast channel capacity (for pub/sub)
    pub broadcast_capacity: usize,
    /// Per-module mpsc queue capacity (for point-to-point)
    pub module_queue_capacity: usize,
    /// Whether to audit-log all messages
    pub audit_enabled: bool,
    /// Queue depth warning threshold (percentage of capacity)
    pub backpressure_threshold_pct: f64,
    /// Whether to drop low-priority messages under pressure
    pub drop_low_priority_on_pressure: bool,
}

impl Default for MessageBusConfig {
    fn default() -> Self {
        Self {
            // 16K messages buffered in broadcast — handles bursts from 100K+ streams
            broadcast_capacity: 16_384,
            // 4K messages per module queue — backpressure kicks in before this
            module_queue_capacity: 4_096,
            audit_enabled: true,
            // Warn when queue depth exceeds 75% of capacity
            backpressure_threshold_pct: 0.75,
            // Drop Low-priority messages when queue is under pressure
            drop_low_priority_on_pressure: true,
        }
    }
}

/// Audit log entry for inter-module communication
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AuditEntry {
    pub timestamp: DateTime<Utc>,
    pub trace_id: TraceId,
    pub message_type: String,
    pub source: ModuleId,
    pub destination: Option<ModuleId>,
    pub priority: Priority,
    pub payload_size_bytes: usize,
}

/// The central message bus connecting all modules
pub struct ModuleMessageBus {
    /// Broadcast sender — all modules subscribe to this for pub/sub
    broadcast_tx: broadcast::Sender<ModuleMessage>,

    /// Per-module mpsc senders — for directed task dispatch
    module_queues: Arc<DashMap<ModuleId, mpsc::Sender<ModuleMessage>>>,

    /// Audit log buffer (flushed periodically to PostgreSQL)
    audit_buffer: Arc<RwLock<Vec<AuditEntry>>>,

    /// Configuration
    config: MessageBusConfig,

    /// Metrics
    messages_published: Arc<std::sync::atomic::AtomicU64>,
    messages_delivered: Arc<std::sync::atomic::AtomicU64>,
    messages_dropped: Arc<std::sync::atomic::AtomicU64>,
    backpressure_events: Arc<std::sync::atomic::AtomicU64>,
}

impl ModuleMessageBus {
    /// Create a new message bus
    pub fn new(config: MessageBusConfig) -> Self {
        let (broadcast_tx, _) = broadcast::channel(config.broadcast_capacity);

        Self {
            broadcast_tx,
            module_queues: Arc::new(DashMap::new()),
            audit_buffer: Arc::new(RwLock::new(Vec::with_capacity(1024))),
            config,
            messages_published: Arc::new(std::sync::atomic::AtomicU64::new(0)),
            messages_delivered: Arc::new(std::sync::atomic::AtomicU64::new(0)),
            messages_dropped: Arc::new(std::sync::atomic::AtomicU64::new(0)),
            backpressure_events: Arc::new(std::sync::atomic::AtomicU64::new(0)),
        }
    }

    /// Register a module's queue. Returns a receiver for point-to-point messages.
    pub fn register_module(
        &self,
        module_id: ModuleId,
    ) -> mpsc::Receiver<ModuleMessage> {
        let (tx, rx) = mpsc::channel(self.config.module_queue_capacity);
        self.module_queues.insert(module_id, tx);
        info!(module = ?module_id, "Module registered on message bus");
        rx
    }

    /// Subscribe to broadcast messages (pub/sub pattern)
    pub fn subscribe(&self) -> broadcast::Receiver<ModuleMessage> {
        self.broadcast_tx.subscribe()
    }

    /// Publish a message to the broadcast channel (all subscribers receive it)
    /// Handles backpressure: if broadcast capacity is near limit, drops low-priority messages.
    pub async fn publish(
        &self,
        message: ModuleMessage,
    ) -> Result<(), BusError> {
        // Check backpressure: if broadcast channel is near capacity
        let receiver_count = self.broadcast_tx.receiver_count();
        let priority = extract_priority(&message);

        // Estimate queue pressure based on subscriber lag
        // broadcast::channel drops oldest when full (LIFO), but we want
        // proactive backpressure before that happens.
        if self.config.drop_low_priority_on_pressure && priority == Priority::Low {
            // Drop low-priority messages proactively under pressure
            // This prevents queue overflow for non-critical messages
            if self.backpressure_active() {
                self.messages_dropped
                    .fetch_add(1, std::sync::atomic::Ordering::Relaxed);
                debug!("Dropped low-priority message due to backpressure");
                return Ok(());
            }
        }

        // Audit log
        if self.config.audit_enabled {
            self.audit_log(&message, None).await;
        }

        // Broadcast to all subscribers
        match self.broadcast_tx.send(message.clone()) {
            Ok(_) => {
                self.messages_published
                    .fetch_add(1, std::sync::atomic::Ordering::Relaxed);
                Ok(())
            }
            Err(e) => {
                // No active subscribers — not necessarily an error
                debug!(error = %e, "No active broadcast subscribers");
                Ok(())
            }
        }
    }

    /// Check if backpressure should be applied.
    /// Returns true if the system is under pressure.
    fn backpressure_active(&self) -> bool {
        // Use dropped message ratio as a proxy for queue pressure
        let published = self.messages_published.load(std::sync::atomic::Ordering::Relaxed);
        let dropped = self.messages_dropped.load(std::sync::atomic::Ordering::Relaxed);
        if published == 0 {
            return false;
        }
        let drop_rate = dropped as f64 / (published + dropped) as f64;
        drop_rate > (1.0 - self.config.backpressure_threshold_pct)
    }

    /// Send a message to a specific module's queue (point-to-point)
    /// Implements backpressure: drops low-priority messages when queue is full.
    pub async fn send_to_module(
        &self,
        target: ModuleId,
        message: ModuleMessage,
    ) -> Result<(), BusError> {
        // Audit log
        if self.config.audit_enabled {
            self.audit_log(&message, Some(target)).await;
        }

        if let Some(tx) = self.module_queues.get(&target) {
            let priority = extract_priority(&message);

            // Try to send; if queue is full, handle based on priority
            match tx.try_send(message.clone()) {
                Ok(()) => {
                    self.messages_delivered
                        .fetch_add(1, std::sync::atomic::Ordering::Relaxed);
                    Ok(())
                }
                Err(tokio::sync::mpsc::error::TrySendError::Full(_)) => {
                    // Queue is full
                    if priority >= Priority::High {
                        // High/Critical: wait for space (blocking)
                        tx.send(message).await
                            .map_err(|_| BusError::ModuleQueueFull(target))?;
                        self.messages_delivered
                            .fetch_add(1, std::sync::atomic::Ordering::Relaxed);
                        self.backpressure_events
                            .fetch_add(1, std::sync::atomic::Ordering::Relaxed);
                        warn!(module = ?target, "Backpressure: high-priority message queued (waiting)");
                        Ok(())
                    } else {
                        // Normal/Low: drop the message
                        self.messages_dropped
                            .fetch_add(1, std::sync::atomic::Ordering::Relaxed);
                        warn!(module = ?target, priority = ?priority, "Backpressure: dropped message (queue full)");
                        Ok(()) // Don't error — message dropped gracefully
                    }
                }
                Err(tokio::sync::mpsc::error::TrySendError::Closed(_)) => {
                    Err(BusError::ModuleNotRegistered(target))
                }
            }
        } else {
            Err(BusError::ModuleNotRegistered(target))
        }
    }

    /// Publish with priority — Critical messages bypass queue depth checks
    pub async fn publish_priority(
        &self,
        message: ModuleMessage,
        priority: Priority,
    ) -> Result<(), BusError> {
        match priority {
            Priority::Critical => {
                // Critical: publish immediately, log prominently
                warn!(priority = ?priority, "CRITICAL message published");
                self.publish(message).await
            }
            _ => self.publish(message).await,
        }
    }

    /// Flush audit buffer to persistent storage
    pub async fn flush_audit(&self) -> Vec<AuditEntry> {
        let mut buffer = self.audit_buffer.write().await;
        std::mem::take(&mut *buffer)
    }

    /// Get current metrics
    pub fn metrics(&self) -> BusMetrics {
        BusMetrics {
            messages_published: self
                .messages_published
                .load(std::sync::atomic::Ordering::Relaxed),
            messages_delivered: self
                .messages_delivered
                .load(std::sync::atomic::Ordering::Relaxed),
            messages_dropped: self
                .messages_dropped
                .load(std::sync::atomic::Ordering::Relaxed),
            backpressure_events: self
                .backpressure_events
                .load(std::sync::atomic::Ordering::Relaxed),
            registered_modules: self.module_queues.len(),
            subscriber_count: self.broadcast_tx.receiver_count(),
        }
    }

    async fn audit_log(&self, message: &ModuleMessage, destination: Option<ModuleId>) {
        let entry = AuditEntry {
            timestamp: Utc::now(),
            trace_id: extract_trace_id(message),
            message_type: message_type_name(message),
            source: extract_source_module(message),
            destination,
            priority: extract_priority(message),
            payload_size_bytes: bincode::serialize(message)
                .map(|b| b.len())
                .unwrap_or(0),
        };

        let mut buffer = self.audit_buffer.write().await;
        buffer.push(entry);

        // Auto-flush at 512 entries
        if buffer.len() >= 512 {
            let entries: Vec<AuditEntry> = std::mem::take(&mut *buffer);
            // In production: write to PostgreSQL audit_log table
            debug!(count = entries.len(), "Audit buffer flushed");
        }
    }
}

#[derive(Debug)]
pub struct BusMetrics {
    pub messages_published: u64,
    pub messages_delivered: u64,
    pub messages_dropped: u64,
    pub backpressure_events: u64,
    pub registered_modules: usize,
    pub subscriber_count: usize,
}

#[derive(Debug, thiserror::Error)]
pub enum BusError {
    #[error("Broadcast failed: {0}")]
    BroadcastFailed(String),
    #[error("Module queue full: {0:?}")]
    ModuleQueueFull(ModuleId),
    #[error("Module not registered: {0:?}")]
    ModuleNotRegistered(ModuleId),
}

// Helper functions
fn extract_trace_id(msg: &ModuleMessage) -> TraceId {
    match msg {
        ModuleMessage::TransactionBatch { trace_id, .. }
        | ModuleMessage::MarketSignal { trace_id, .. }
        | ModuleMessage::CreditAssessment { trace_id, .. }
        | ModuleMessage::DistributionGap { trace_id, .. }
        | ModuleMessage::FMCGReport { trace_id, .. }
        | ModuleMessage::HealthAssessment { trace_id, .. }
        | ModuleMessage::EconomicIndicator { trace_id, .. }
        | ModuleMessage::AnomalyAlert { trace_id, .. }
        | ModuleMessage::EmergentPattern { trace_id, .. }
        | ModuleMessage::RouteCommand { trace_id, .. } => *trace_id,
        | ModuleMessage::ServicePriceBroadcast { trace_id, .. } => *trace_id,
        | ModuleMessage::ServiceMarketSignal { trace_id, .. } => *trace_id,
        ModuleMessage::Heartbeat { .. } => Uuid::nil(),
    }
}

fn message_type_name(msg: &ModuleMessage) -> String {
    match msg {
        ModuleMessage::TransactionBatch { .. } => "TransactionBatch",
        ModuleMessage::MarketSignal { .. } => "MarketSignal",
        ModuleMessage::CreditAssessment { .. } => "CreditAssessment",
        ModuleMessage::DistributionGap { .. } => "DistributionGap",
        ModuleMessage::FMCGReport { .. } => "FMCGReport",
        ModuleMessage::HealthAssessment { .. } => "HealthAssessment",
        ModuleMessage::EconomicIndicator { .. } => "EconomicIndicator",
        ModuleMessage::AnomalyAlert { .. } => "AnomalyAlert",
        ModuleMessage::EmergentPattern { .. } => "EmergentPattern",
        ModuleMessage::RouteCommand { .. } => "RouteCommand",
        ModuleMessage::ServicePriceBroadcast { .. } => "ServicePriceBroadcast",
        ModuleMessage::ServiceMarketSignal { .. } => "ServiceMarketSignal",
        ModuleMessage::Heartbeat { .. } => "Heartbeat",
    }
    .to_string()
}

fn extract_source_module(msg: &ModuleMessage) -> ModuleId {
    match msg {
        ModuleMessage::TransactionBatch { .. } => ModuleId::ApiGateway,
        ModuleMessage::MarketSignal { .. } => ModuleId::MarketAnalyzer,
        ModuleMessage::CreditAssessment { .. } => ModuleId::CreditScorer,
        ModuleMessage::DistributionGap { .. } => ModuleId::DistributionAnalyzer,
        ModuleMessage::FMCGReport { .. } => ModuleId::FMCGIntelligence,
        ModuleMessage::HealthAssessment { .. } => ModuleId::HealthMetrics,
        ModuleMessage::EconomicIndicator { .. } => ModuleId::EconomicAnalyzer,
        ModuleMessage::AnomalyAlert { source_module, .. } => *source_module,
        ModuleMessage::EmergentPattern { .. } => ModuleId::CollectiveIntelligence,
        ModuleMessage::RouteCommand { .. } => ModuleId::Orchestrator,
        ModuleMessage::ServicePriceBroadcast { .. } => ModuleId::ApiGateway,
        ModuleMessage::ServiceMarketSignal { .. } => ModuleId::ServicePriceDiscovery,
        ModuleMessage::Heartbeat { module_id, .. } => *module_id,
    }
}

fn extract_priority(msg: &ModuleMessage) -> Priority {
    match msg {
        ModuleMessage::AnomalyAlert { severity, .. } => {
            if *severity > 0.8 {
                Priority::Critical
            } else if *severity > 0.5 {
                Priority::High
            } else {
                Priority::Normal
            }
        }
        ModuleMessage::RouteCommand { priority, .. } => *priority,
        ModuleMessage::Heartbeat { .. } => Priority::Low,
        _ => Priority::Normal,
    }
}
