// Continuous OODA Loop — The Superagent's Brain
// Not per-request, but continuous: Observe → Orient → Decide → Act
// Four independent timer-driven loops: fast, medium, slow, deep

use std::sync::Arc;
use std::time::Duration;
use tokio::sync::{broadcast, RwLock};
use tokio::time::interval;
use serde::{Deserialize, Serialize};
use chrono::{DateTime, Utc};
use tracing::{info, warn, error, instrument};
use uuid::Uuid;

use super::metrics::LoopMetrics;
use super::drift_detection::DriftDetector;
use super::pipeline_feedback::PipelineFeedbackChannel;

// ─── OODA Phase Definitions ───────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum OodaPhase {
    Observe,
    Orient,
    Decide,
    Act,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum LoopSpeed {
    Fast,   // Per-sync event (~seconds)
    Medium, // Hourly
    Slow,   // Daily
    Deep,   // Weekly
}

impl LoopSpeed {
    pub fn interval(&self) -> Duration {
        match self {
            LoopSpeed::Fast => Duration::from_secs(1),      // event-driven, poll at 1s
            LoopSpeed::Medium => Duration::from_secs(3600), // 1 hour
            LoopSpeed::Slow => Duration::from_secs(86400),  // 24 hours
            LoopSpeed::Deep => Duration::from_secs(604800), // 7 days
        }
    }

    pub fn name(&self) -> &str {
        match self {
            LoopSpeed::Fast => "fast",
            LoopSpeed::Medium => "medium",
            LoopSpeed::Slow => "slow",
            LoopSpeed::Deep => "deep",
        }
    }
}

// ─── OODA Cycle State ─────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OodaCycle {
    pub cycle_id: Uuid,
    pub loop_speed: LoopSpeed,
    pub phase: OodaPhase,
    pub started_at: DateTime<Utc>,
    pub phase_started_at: DateTime<Utc>,
    pub iteration: u64,
    pub observations: Vec<Observation>,
    pub decision: Option<Decision>,
    pub action_result: Option<ActionResult>,
    pub error_count: u32,
    pub max_iterations: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Observation {
    pub source: String,
    pub data: serde_json::Value,
    pub timestamp: DateTime<Utc>,
    pub confidence: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Decision {
    pub action_type: String,
    pub parameters: serde_json::Value,
    pub confidence: f64,
    pub reasoning: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ActionResult {
    pub success: bool,
    pub output: serde_json::Value,
    pub duration_ms: u64,
    pub error: Option<String>,
}

// ─── Loop Configuration ───────────────────────────────────────────────────

#[derive(Debug, Clone)]
pub struct LoopConfig {
    pub fast_interval: Duration,
    pub medium_interval: Duration,
    pub slow_interval: Duration,
    pub deep_interval: Duration,
    pub max_fast_iterations: u32,
    pub max_medium_iterations: u32,
    pub max_slow_iterations: u32,
    pub max_deep_iterations: u32,
    pub error_threshold: u32,
}

impl Default for LoopConfig {
    fn default() -> Self {
        Self {
            fast_interval: Duration::from_secs(1),
            medium_interval: Duration::from_secs(3600),
            slow_interval: Duration::from_secs(86400),
            deep_interval: Duration::from_secs(604800),
            max_fast_iterations: 100,
            max_medium_iterations: 50,
            max_slow_iterations: 20,
            max_deep_iterations: 10,
            error_threshold: 5,
        }
    }
}

// ─── Sync Event (Fast Loop Input) ─────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SyncEvent {
    pub device_id: String,
    pub worker_id: String,
    pub region: String,
    pub business_type: String,
    pub transactions: Vec<TransactionSummary>,
    pub model_gradients: Option<Vec<f64>>,
    pub error_signals: Vec<String>,
    pub timestamp: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TransactionSummary {
    pub category: String,
    pub amount_bucket: String, // e.g., "100-500" — never exact amount
    pub payment_method: String,
    pub hour_of_day: u8,
    pub count: u32,
}

// ─── Worker Profile Update ────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkerProfileUpdate {
    pub worker_id: String,
    pub region: String,
    pub business_type: String,
    pub active_days_delta: u32,
    pub transaction_volume_bucket: String,
    pub product_categories: Vec<String>,
    pub consistency_score: f64,
    pub last_active: DateTime<Utc>,
}

// ─── Market Signal ────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MarketSignal {
    pub region: String,
    pub product_category: String,
    pub demand_velocity: f64,
    pub price_trend: f64,       // -1.0 to 1.0 (declining to rising)
    pub volatility: f64,
    pub sample_size: u32,
    pub timestamp: DateTime<Utc>,
}

// ─── Intelligence Report ──────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IntelligenceReport {
    pub report_id: Uuid,
    pub report_type: String,
    pub region: String,
    pub generated_at: DateTime<Utc>,
    pub sections: Vec<ReportSection>,
    pub confidence: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReportSection {
    pub title: String,
    pub content: String,
    pub data_points: u32,
    pub confidence: f64,
}

// ─── OODA Loop Supervisor ─────────────────────────────────────────────────

/// The OODA Supervisor runs all four loop speeds independently.
/// Each loop is a tokio task with its own interval timer.
/// Loops do NOT block each other — they share state via Arc<RwLock<>>.
pub struct OodaSupervisor {
    config: LoopConfig,
    metrics: Arc<RwLock<LoopMetrics>>,
    drift_detector: Arc<RwLock<DriftDetector>>,
    pipeline_feedback: Arc<PipelineFeedbackChannel>,
    cycle_history: Arc<RwLock<Vec<OodaCycle>>>,
    sync_event_tx: broadcast::Sender<SyncEvent>,
    shutdown_tx: broadcast::Sender<()>,
}

impl OodaSupervisor {
    pub fn new(
        config: LoopConfig,
        metrics: Arc<RwLock<LoopMetrics>>,
        drift_detector: Arc<RwLock<DriftDetector>>,
        pipeline_feedback: Arc<PipelineFeedbackChannel>,
    ) -> Self {
        let (sync_event_tx, _) = broadcast::channel(10_000);
        let (shutdown_tx, _) = broadcast::channel(1);

        Self {
            config,
            metrics,
            drift_detector,
            pipeline_feedback,
            cycle_history: Arc::new(RwLock::new(Vec::with_capacity(1000))),
            sync_event_tx,
            shutdown_tx,
        }
    }

    /// Get a sender to feed sync events into the fast loop.
    pub fn sync_event_sender(&self) -> broadcast::Sender<SyncEvent> {
        self.sync_event_tx.clone()
    }

    /// Start all four OODA loops. Returns a JoinHandle for each.
    pub fn start(self: Arc<Self>) -> Vec<tokio::task::JoinHandle<()>> {
        let mut handles = Vec::with_capacity(4);

        handles.push(tokio::spawn(self.clone().run_fast_loop()));
        handles.push(tokio::spawn(self.clone().run_medium_loop()));
        handles.push(tokio::spawn(self.clone().run_slow_loop()));
        handles.push(tokio::spawn(self.clone().run_deep_loop()));

        info!("OODA Supervisor: all 4 loops started");
        handles
    }

    /// Signal all loops to shut down gracefully.
    pub fn shutdown(&self) {
        let _ = self.shutdown_tx.send(());
        info!("OODA Supervisor: shutdown signal sent");
    }

    // ─── Fast Loop: Per-Sync Event ────────────────────────────────────────

    #[instrument(skip(self))]
    async fn run_fast_loop(self: Arc<Self>) {
        let mut tick = interval(self.config.fast_interval);
        let mut rx = self.sync_event_tx.subscribe();
        let mut shutdown_rx = self.shutdown_tx.subscribe();
        let mut iteration: u64 = 0;

        info!("OODA Fast Loop: started (per-sync processing)");

        loop {
            tokio::select! {
                _ = shutdown_rx.recv() => {
                    info!("OODA Fast Loop: shutdown received");
                    break;
                }
                _ = tick.tick() => {
                    // Check for pending sync events
                    match rx.try_recv() {
                        Ok(event) => {
                            iteration += 1;
                            let cycle = self.execute_fast_cycle(event, iteration).await;
                            self.record_cycle(cycle).await;

                            // Update metrics
                            let mut m = self.metrics.write().await;
                            m.fast_loop_iterations += 1;
                            m.fast_loop_last_run = Some(Utc::now());
                        }
                        Err(broadcast::error::TryRecvError::Empty) => {
                            // No events — this is normal for fast loop
                        }
                        Err(broadcast::error::TryRecvError::Lagged(n)) => {
                            warn!("OODA Fast Loop: lagged behind {} events", n);
                            let mut m = self.metrics.write().await;
                            m.fast_loop_lag_count += n;
                        }
                        Err(broadcast::error::TryRecvError::Closed) => {
                            error!("OODA Fast Loop: sync channel closed");
                            break;
                        }
                    }
                }
            }
        }
    }

    async fn execute_fast_cycle(&self, event: SyncEvent, iteration: u64) -> OodaCycle {
        let mut cycle = OodaCycle {
            cycle_id: Uuid::new_v4(),
            loop_speed: LoopSpeed::Fast,
            phase: OodaPhase::Observe,
            started_at: Utc::now(),
            phase_started_at: Utc::now(),
            iteration,
            observations: Vec::new(),
            decision: None,
            action_result: None,
            error_count: 0,
            max_iterations: self.config.max_fast_iterations,
        };

        // OBSERVE: Ingest sync event
        cycle.observations.push(Observation {
            source: format!("device:{}", event.device_id),
            data: serde_json::to_value(&event).unwrap_or_default(),
            timestamp: Utc::now(),
            confidence: 1.0,
        });

        // ORIENT: Validate and classify incoming data
        cycle.phase = OodaPhase::Orient;
        let validation = self.validate_sync_event(&event);
        if !validation.is_valid {
            cycle.error_count += 1;
            // Feed error signal back to device via pipeline feedback
            self.pipeline_feedback.send_error(
                &event.device_id,
                &validation.errors,
            ).await;
        }

        // DECIDE: Determine actions based on observations
        cycle.phase = OodaPhase::Decide;
        let actions = self.decide_fast_actions(&event, &validation);
        cycle.decision = Some(Decision {
            action_type: "fast_sync_process".to_string(),
            parameters: serde_json::json!({
                "worker_id": event.worker_id,
                "region": event.region,
                "action_count": actions.len()
            }),
            confidence: if validation.is_valid { 0.95 } else { 0.6 },
            reasoning: format!("{} actions from sync event", actions.len()),
        });

        // ACT: Execute decisions
        cycle.phase = OodaPhase::Act;
        let start = std::time::Instant::now();
        let mut results = Vec::new();
        for action in &actions {
            let result = self.execute_fast_action(action).await;
            results.push(result);
        }
        let duration = start.elapsed().as_millis() as u64;

        let all_success = results.iter().all(|r| r.success);
        cycle.action_result = Some(ActionResult {
            success: all_success,
            output: serde_json::json!({
                "actions_executed": results.len(),
                "successful": results.iter().filter(|r| r.success).count(),
                "worker_profile_updated": results.iter().any(|r| r.output.get("profile_updated").and_then(|v| v.as_bool()).unwrap_or(false)),
            }),
            duration_ms: duration,
            error: if all_success { None } else { Some("Some actions failed".to_string()) },
        });

        cycle
    }

    // ─── Medium Loop: Hourly Market Aggregation ───────────────────────────

    #[instrument(skip(self))]
    async fn run_medium_loop(self: Arc<Self>) {
        let mut tick = interval(self.config.medium_interval);
        let mut shutdown_rx = self.shutdown_tx.subscribe();
        let mut iteration: u64 = 0;

        info!("OODA Medium Loop: started (hourly market signals)");

        loop {
            tokio::select! {
                _ = shutdown_rx.recv() => {
                    info!("OODA Medium Loop: shutdown received");
                    break;
                }
                _ = tick.tick() => {
                    iteration += 1;
                    let cycle = self.execute_medium_cycle(iteration).await;
                    self.record_cycle(cycle).await;

                    let mut m = self.metrics.write().await;
                    m.medium_loop_iterations += 1;
                    m.medium_loop_last_run = Some(Utc::now());
                }
            }
        }
    }

    async fn execute_medium_cycle(&self, iteration: u64) -> OodaCycle {
        let mut cycle = OodaCycle {
            cycle_id: Uuid::new_v4(),
            loop_speed: LoopSpeed::Medium,
            phase: OodaPhase::Observe,
            started_at: Utc::now(),
            phase_started_at: Utc::now(),
            iteration,
            observations: Vec::new(),
            decision: None,
            action_result: None,
            error_count: 0,
            max_iterations: self.config.max_medium_iterations,
        };

        // OBSERVE: Collect hourly market signals
        cycle.observations.push(Observation {
            source: "market_aggregator".to_string(),
            data: serde_json::json!({
                "signal_count": 0, // populated by real aggregator
                "regions_active": 0,
                "hour": Utc::now().format("%H:00").to_string(),
            }),
            timestamp: Utc::now(),
            confidence: 0.85,
        });

        // ORIENT: Detect trends and anomalies
        cycle.phase = OodaPhase::Orient;

        // DECIDE: Update Soko Pulse, adjust aggregation parameters
        cycle.phase = OodaPhase::Decide;
        cycle.decision = Some(Decision {
            action_type: "hourly_aggregation".to_string(),
            parameters: serde_json::json!({
                "update_soko_pulse": true,
                "recalculate_demand_signals": true,
                "check_price_anomalies": true,
            }),
            confidence: 0.8,
            reasoning: "Hourly aggregation cycle".to_string(),
        });

        // ACT: Execute market intelligence update
        cycle.phase = OodaPhase::Act;
        let start = std::time::Instant::now();
        // In production: call into market_aggregator, soko_pulse_updater
        let duration = start.elapsed().as_millis() as u64;

        cycle.action_result = Some(ActionResult {
            success: true,
            output: serde_json::json!({
                "soko_pulse_updated": true,
                "signals_processed": 0,
            }),
            duration_ms: duration,
            error: None,
        });

        cycle
    }

    // ─── Slow Loop: Daily Intelligence ────────────────────────────────────

    #[instrument(skip(self))]
    async fn run_slow_loop(self: Arc<Self>) {
        let mut tick = interval(self.config.slow_interval);
        let mut shutdown_rx = self.shutdown_tx.subscribe();
        let mut iteration: u64 = 0;

        info!("OODA Slow Loop: started (daily intelligence reports)");

        loop {
            tokio::select! {
                _ = shutdown_rx.recv() => {
                    info!("OODA Slow Loop: shutdown received");
                    break;
                }
                _ = tick.tick() => {
                    iteration += 1;
                    let cycle = self.execute_slow_cycle(iteration).await;
                    self.record_cycle(cycle).await;

                    let mut m = self.metrics.write().await;
                    m.slow_loop_iterations += 1;
                    m.slow_loop_last_run = Some(Utc::now());
                }
            }
        }
    }

    async fn execute_slow_cycle(&self, iteration: u64) -> OodaCycle {
        let mut cycle = OodaCycle {
            cycle_id: Uuid::new_v4(),
            loop_speed: LoopSpeed::Slow,
            phase: OodaPhase::Observe,
            started_at: Utc::now(),
            phase_started_at: Utc::now(),
            iteration,
            observations: Vec::new(),
            decision: None,
            action_result: None,
            error_count: 0,
            max_iterations: self.config.max_slow_iterations,
        };

        // OBSERVE: Gather daily aggregates
        cycle.observations.push(Observation {
            source: "daily_aggregator".to_string(),
            data: serde_json::json!({
                "report_type": "daily_intelligence",
                "date": Utc::now().format("%Y-%m-%d").to_string(),
            }),
            timestamp: Utc::now(),
            confidence: 0.9,
        });

        // ORIENT: Check model drift
        cycle.phase = OodaPhase::Orient;
        let drift_report = {
            let detector = self.drift_detector.read().await;
            detector.generate_report().await
        };
        if drift_report.drift_detected {
            warn!("Model drift detected: {:?}", drift_report);
            cycle.observations.push(Observation {
                source: "drift_detector".to_string(),
                data: serde_json::to_value(&drift_report).unwrap_or_default(),
                timestamp: Utc::now(),
                confidence: drift_report.confidence,
            });
        }

        // DECIDE: Generate intelligence reports, trigger retraining if needed
        cycle.phase = OodaPhase::Decide;
        cycle.decision = Some(Decision {
            action_type: "daily_intelligence".to_string(),
            parameters: serde_json::json!({
                "generate_reports": true,
                "check_drift": true,
                "retrain_if_drifted": drift_report.drift_detected,
            }),
            confidence: 0.85,
            reasoning: if drift_report.drift_detected {
                "Drift detected — will trigger retraining".to_string()
            } else {
                "Normal daily cycle".to_string()
            },
        });

        // ACT: Generate reports, optionally trigger retraining
        cycle.phase = OodaPhase::Act;
        let start = std::time::Instant::now();
        // In production: call report_generator, model_retrainer
        let duration = start.elapsed().as_millis() as u64;

        cycle.action_result = Some(ActionResult {
            success: true,
            output: serde_json::json!({
                "reports_generated": 0,
                "retraining_triggered": drift_report.drift_detected,
            }),
            duration_ms: duration,
            error: None,
        });

        cycle
    }

    // ─── Deep Loop: Weekly Federated Learning ─────────────────────────────

    #[instrument(skip(self))]
    async fn run_deep_loop(self: Arc<Self>) {
        let mut tick = interval(self.config.deep_interval);
        let mut shutdown_rx = self.shutdown_tx.subscribe();
        let mut iteration: u64 = 0;

        info!("OODA Deep Loop: started (weekly federated learning)");

        loop {
            tokio::select! {
                _ = shutdown_rx.recv() => {
                    info!("OODA Deep Loop: shutdown received");
                    break;
                }
                _ = tick.tick() => {
                    iteration += 1;
                    let cycle = self.execute_deep_cycle(iteration).await;
                    self.record_cycle(cycle).await;

                    let mut m = self.metrics.write().await;
                    m.deep_loop_iterations += 1;
                    m.deep_loop_last_run = Some(Utc::now());
                }
            }
        }
    }

    async fn execute_deep_cycle(&self, iteration: u64) -> OodaCycle {
        let mut cycle = OodaCycle {
            cycle_id: Uuid::new_v4(),
            loop_speed: LoopSpeed::Deep,
            phase: OodaPhase::Observe,
            started_at: Utc::now(),
            phase_started_at: Utc::now(),
            iteration,
            observations: Vec::new(),
            decision: None,
            action_result: None,
            error_count: 0,
            max_iterations: self.config.max_deep_iterations,
        };

        // OBSERVE: Collect weekly FL gradients and economic indicators
        cycle.observations.push(Observation {
            source: "federated_learning".to_string(),
            data: serde_json::json!({
                "round": iteration,
                "gradient_batches_collected": 0,
                "economic_indicators_stale": true,
            }),
            timestamp: Utc::now(),
            confidence: 0.7,
        });

        // ORIENT: Analyze aggregate patterns, cohort health
        cycle.phase = OodaPhase::Orient;

        // DECIDE: Aggregate FL gradients, recalculate economic indicators
        cycle.phase = OodaPhase::Decide;
        cycle.decision = Some(Decision {
            action_type: "weekly_deep_analysis".to_string(),
            parameters: serde_json::json!({
                "aggregate_federated_gradients": true,
                "recalculate_economic_indicators": true,
                "update_cohort_models": true,
                "recalibrate_alama_score": true,
            }),
            confidence: 0.75,
            reasoning: format!("Weekly deep cycle #{}", iteration),
        });

        // ACT: Execute deep analysis
        cycle.phase = OodaPhase::Act;
        let start = std::time::Instant::now();
        // In production: call fl_aggregator, economic_indicator_engine
        let duration = start.elapsed().as_millis() as u64;

        cycle.action_result = Some(ActionResult {
            success: true,
            output: serde_json::json!({
                "fl_round_completed": true,
                "economic_indicators_updated": true,
                "model_delta_size_bytes": 0,
            }),
            duration_ms: duration,
            error: None,
        });

        cycle
    }

    // ─── Helpers ──────────────────────────────────────────────────────────

    fn validate_sync_event(&self, event: &SyncEvent) -> ValidationResult {
        let mut errors = Vec::new();

        if event.device_id.is_empty() {
            errors.push("missing device_id".to_string());
        }
        if event.worker_id.is_empty() {
            errors.push("missing worker_id".to_string());
        }
        if event.region.is_empty() {
            errors.push("missing region".to_string());
        }
        if event.transactions.is_empty() && event.error_signals.is_empty() {
            errors.push("empty sync event: no transactions and no error signals".to_string());
        }

        // Validate transaction summaries
        for tx in &event.transactions {
            if tx.count == 0 {
                errors.push(format!("zero-count transaction in category '{}'", tx.category));
            }
            if tx.hour_of_day > 23 {
                errors.push(format!("invalid hour_of_day: {}", tx.hour_of_day));
            }
        }

        ValidationResult {
            is_valid: errors.is_empty(),
            errors,
        }
    }

    fn decide_fast_actions(&self, event: &SyncEvent, validation: &ValidationResult) -> Vec<FastAction> {
        let mut actions = Vec::new();

        if validation.is_valid {
            actions.push(FastAction::UpdateWorkerProfile(WorkerProfileUpdate {
                worker_id: event.worker_id.clone(),
                region: event.region.clone(),
                business_type: event.business_type.clone(),
                active_days_delta: 1,
                transaction_volume_bucket: Self::bucket_transaction_volume(event.transactions.len()),
                product_categories: event.transactions.iter().map(|t| t.category.clone()).collect(),
                consistency_score: 1.0, // computed from history
                last_active: Utc::now(),
            }));

            actions.push(FastAction::UpdateDailySummary {
                region: event.region.clone(),
                transactions: event.transactions.clone(),
            });

            // Check for anomalies
            if event.error_signals.len() > 3 {
                actions.push(FastAction::FlagAnomaly {
                    device_id: event.device_id.clone(),
                    error_count: event.error_signals.len(),
                });
            }
        }

        actions
    }

    async fn execute_fast_action(&self, action: &FastAction) -> ActionResult {
        match action {
            FastAction::UpdateWorkerProfile(_profile) => {
                // In production: update worker profile in PostgreSQL
                ActionResult {
                    success: true,
                    output: serde_json::json!({"profile_updated": true}),
                    duration_ms: 0,
                    error: None,
                }
            }
            FastAction::UpdateDailySummary { region, transactions } => {
                // In production: increment daily counters in ClickHouse
                ActionResult {
                    success: true,
                    output: serde_json::json!({
                        "summary_updated": true,
                        "region": region,
                        "tx_count": transactions.len()
                    }),
                    duration_ms: 0,
                    error: None,
                }
            }
            FastAction::FlagAnomaly { device_id, error_count } => {
                warn!("Anomaly flagged: device={}, errors={}", device_id, error_count);
                ActionResult {
                    success: true,
                    output: serde_json::json!({"anomaly_flagged": true}),
                    duration_ms: 0,
                    error: None,
                }
            }
        }
    }

    fn bucket_transaction_volume(count: usize) -> String {
        match count {
            0 => "none".to_string(),
            1..=5 => "low".to_string(),
            6..=20 => "medium".to_string(),
            21..=50 => "high".to_string(),
            _ => "very_high".to_string(),
        }
    }

    async fn record_cycle(&self, cycle: OodaCycle) {
        let mut history = self.cycle_history.write().await;
        // Keep last 1000 cycles
        if history.len() >= 1000 {
            history.remove(0);
        }
        history.push(cycle);
    }
}

// ─── Supporting Types ─────────────────────────────────────────────────────

struct ValidationResult {
    is_valid: bool,
    errors: Vec<String>,
}

enum FastAction {
    UpdateWorkerProfile(WorkerProfileUpdate),
    UpdateDailySummary {
        region: String,
        transactions: Vec<TransactionSummary>,
    },
    FlagAnomaly {
        device_id: String,
        error_count: usize,
    },
}

// ─── Tests ────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_loop_speed_intervals() {
        assert_eq!(LoopSpeed::Fast.interval(), Duration::from_secs(1));
        assert_eq!(LoopSpeed::Medium.interval(), Duration::from_secs(3600));
        assert_eq!(LoopSpeed::Slow.interval(), Duration::from_secs(86400));
        assert_eq!(LoopSpeed::Deep.interval(), Duration::from_secs(604800));
    }

    #[test]
    fn test_transaction_volume_bucketing() {
        assert_eq!(OodaSupervisor::bucket_transaction_volume(0), "none");
        assert_eq!(OodaSupervisor::bucket_transaction_volume(3), "low");
        assert_eq!(OodaSupervisor::bucket_transaction_volume(15), "medium");
        assert_eq!(OodaSupervisor::bucket_transaction_volume(35), "high");
        assert_eq!(OodaSupervisor::bucket_transaction_volume(100), "very_high");
    }

    #[test]
    fn test_default_config() {
        let config = LoopConfig::default();
        assert_eq!(config.error_threshold, 5);
        assert_eq!(config.max_fast_iterations, 100);
    }

    #[test]
    fn test_sync_event_validation() {
        let supervisor = create_test_supervisor();
        let valid_event = SyncEvent {
            device_id: "dev-001".to_string(),
            worker_id: "wrk-001".to_string(),
            region: "nairobi-eastlands".to_string(),
            business_type: "mama_mboga".to_string(),
            transactions: vec![TransactionSummary {
                category: "vegetables".to_string(),
                amount_bucket: "100-500".to_string(),
                payment_method: "mpesa".to_string(),
                hour_of_day: 10,
                count: 5,
            }],
            model_gradients: None,
            error_signals: vec![],
            timestamp: Utc::now(),
        };
        let result = supervisor.validate_sync_event(&valid_event);
        assert!(result.is_valid);

        // Invalid: empty device_id
        let mut invalid_event = valid_event.clone();
        invalid_event.device_id = String::new();
        let result = supervisor.validate_sync_event(&invalid_event);
        assert!(!result.is_valid);
        assert!(result.errors.iter().any(|e| e.contains("device_id")));
    }

    fn create_test_supervisor() -> OodaSupervisor {
        let metrics = Arc::new(RwLock::new(LoopMetrics::default()));
        let drift_detector = Arc::new(RwLock::new(DriftDetector::new(Default::default())));
        let pipeline_feedback = Arc::new(PipelineFeedbackChannel::new());
        OodaSupervisor::new(LoopConfig::default(), metrics, drift_detector, pipeline_feedback)
    }
}
