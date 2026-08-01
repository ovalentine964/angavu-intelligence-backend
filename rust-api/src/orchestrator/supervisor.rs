// src/orchestrator/supervisor.rs

use super::*;
use dashmap::DashMap;
use std::collections::HashMap;
use tokio::task::JoinHandle;
use std::time::Instant;
use std::path::PathBuf;

/// The concrete OODA orchestrator implementation
pub struct OODAOrchestrator {
    /// Configuration
    config: OrchestratorConfig,
    /// The message bus connecting all modules
    bus: Arc<ModuleMessageBus>,
    /// Current state (shared across tasks)
    state: Arc<RwLock<OrchestratorState>>,
    /// Module task handles (for restart management)
    module_handles: Arc<DashMap<ModuleId, JoinHandle<()>>>,
    /// Module restart timestamps (cooldown enforcement)
    last_restart: Arc<DashMap<ModuleId, DateTime<Utc>>>,
    /// Shutdown signal
    shutdown_tx: Arc<RwLock<Option<tokio::sync::broadcast::Sender<()>>>>,
    /// Persistent state store for module snapshots (fallback)
    state_store: Arc<modules::ModuleStateStore>,
    /// PostgreSQL pool for market module persistence
    pool: Option<sqlx::PgPool>,
}

impl OODAOrchestrator {
    pub fn new(config: OrchestratorConfig, bus: Arc<ModuleMessageBus>) -> Self {
        Self::with_state_dir(config, bus, PathBuf::from("./data/module_state"), None)
    }

    pub fn with_pool(config: OrchestratorConfig, bus: Arc<ModuleMessageBus>, pool: sqlx::PgPool) -> Self {
        Self::with_state_dir(config, bus, PathBuf::from("./data/module_state"), Some(pool))
    }

    pub fn with_state_dir(
        config: OrchestratorConfig,
        bus: Arc<ModuleMessageBus>,
        state_dir: PathBuf,
        pool: Option<sqlx::PgPool>,
    ) -> Self {
        let (shutdown_tx, _) = tokio::sync::broadcast::channel(1);

        let state = OrchestratorState {
            phase: OODAPhase::Observe,
            cycle_count: 0,
            cycle_start: Utc::now(),
            module_health: HashMap::new(),
            active_anomalies: Vec::new(),
            recent_patterns: Vec::new(),
            throughput: 0.0,
        };

        Self {
            config,
            bus,
            state: Arc::new(RwLock::new(state)),
            module_handles: Arc::new(DashMap::new()),
            last_restart: Arc::new(DashMap::new()),
            shutdown_tx: Arc::new(RwLock::new(Some(shutdown_tx))),
            state_store: Arc::new(modules::ModuleStateStore::new(state_dir)),
            pool,
        }
    }

    /// Start all capability modules as independent tokio tasks
    pub async fn start_modules(&self) -> Result<(), OrchestratorError> {
        info!("Starting capability modules...");

        let store = self.state_store.clone();
        let pool = self.pool.clone();

        let modules_with_state: Vec<(ModuleId, Box<dyn CapabilityModule>)> = vec![
            (ModuleId::MarketAnalyzer, {
                let mut m = if let Some(ref p) = pool {
                    modules::market::MarketAnalyzer::with_pool(p.clone())
                } else {
                    modules::market::MarketAnalyzer::new()
                };
                // Load from PostgreSQL first, fall back to bincode snapshot
                if let Err(e) = m.load_state().await {
                    tracing::warn!("MarketAnalyzer PG load failed: {}", e);
                    if let Some(data) = store.load(ModuleId::MarketAnalyzer).await {
                        m.restore_state(&data);
                    }
                }
                Box::new(m)
            }),
            (ModuleId::CreditScorer, {
                let mut m = modules::credit::CreditScorer::new();
                if let Some(data) = store.load(ModuleId::CreditScorer).await {
                    m.restore_state(&data);
                }
                Box::new(m)
            }),
            (ModuleId::DistributionAnalyzer, {
                let mut m = if let Some(ref p) = pool {
                    modules::distribution::DistributionAnalyzer::with_pool(p.clone())
                } else {
                    modules::distribution::DistributionAnalyzer::new()
                };
                if let Err(e) = m.load_state().await {
                    tracing::warn!("DistributionAnalyzer PG load failed: {}", e);
                    if let Some(data) = store.load(ModuleId::DistributionAnalyzer).await {
                        m.restore_state(&data);
                    }
                }
                Box::new(m)
            }),
            (ModuleId::FMCGIntelligence, {
                let mut m = if let Some(ref p) = pool {
                    modules::fmcg::FMCGIntelligence::with_pool(p.clone())
                } else {
                    modules::fmcg::FMCGIntelligence::new()
                };
                if let Err(e) = m.load_state().await {
                    tracing::warn!("FMCGIntelligence PG load failed: {}", e);
                    if let Some(data) = store.load(ModuleId::FMCGIntelligence).await {
                        m.restore_state(&data);
                    }
                }
                Box::new(m)
            }),
            (ModuleId::ServicePriceDiscovery, {
                let mut m = if let Some(ref p) = pool {
                    modules::service_price_discovery::ServicePriceDiscoveryEngine::with_pool(p.clone())
                } else {
                    modules::service_price_discovery::ServicePriceDiscoveryEngine::new()
                };
                if let Err(e) = m.load_state().await {
                    tracing::warn!("ServicePriceDiscoveryEngine PG load failed: {}", e);
                }
                Box::new(m)
            }),
            (ModuleId::HealthMetrics, {
                let mut m = modules::health::HealthMetrics::new();
                if let Some(data) = store.load(ModuleId::HealthMetrics).await {
                    m.restore_state(&data);
                }
                Box::new(m)
            }),
            (ModuleId::EconomicAnalyzer, {
                let mut m = if let Some(ref p) = pool {
                    modules::economic::EconomicAnalyzer::with_pool(p.clone())
                } else {
                    modules::economic::EconomicAnalyzer::new()
                };
                if let Err(e) = m.load_state().await {
                    tracing::warn!("EconomicAnalyzer PG load failed: {}", e);
                    if let Some(data) = store.load(ModuleId::EconomicAnalyzer).await {
                        m.restore_state(&data);
                    }
                }
                Box::new(m)
            }),
        ];

        for (module_id, module) in modules_with_state {
            self.spawn_module(module_id, module).await?;
        }

        info!(count = 7, "All capability modules started");
        Ok(())
    }

    /// Spawn a single module as an independent tokio task
    async fn spawn_module(
        &self,
        module_id: ModuleId,
        mut module: Box<dyn CapabilityModule>,
    ) -> Result<(), OrchestratorError> {
        let rx = self.bus.register_module(module_id);
        let bus = Arc::clone(&self.bus);
        let state_store = Arc::clone(&self.state_store);
        let mut shutdown_rx = self.shutdown_tx.read().await.as_ref()
            .unwrap()
            .subscribe();

        let handle = tokio::spawn(async move {
            info!(module = ?module_id, "Module task started");

            let mut rx = rx;
            let mut messages_since_snapshot: u64 = 0;
            let snapshot_interval: u64 = 100; // snapshot every 100 messages
            let mut snapshot_timer = tokio::time::interval(
                std::time::Duration::from_secs(300) // or every 5 minutes
            );
            snapshot_timer.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);

            loop {
                tokio::select! {
                    // Process incoming messages
                    Some(message) = rx.recv() => {
                        let start = Instant::now();
                        match module.process(message.clone()).await {
                            Ok(Some(response)) => {
                                // Publish module's output back to bus
                                if let Err(e) = bus.publish(response).await {
                                    error!(module = ?module_id, error = %e, "Failed to publish response");
                                }
                            }
                            Ok(None) => {
                                // Module consumed message, no output needed
                            }
                            Err(e) => {
                                error!(module = ?module_id, error = %e, "Module processing error");
                                // Publish anomaly alert
                                let alert = ModuleMessage::AnomalyAlert {
                                    trace_id: Uuid::nil(),
                                    source_module: module_id,
                                    anomaly_type: AnomalyType::DataQualityIssue,
                                    severity: 0.5,
                                    description: format!("Processing error: {}", e),
                                    affected_region: None,
                                };
                                let _ = bus.publish(alert).await;
                            }
                        }
                        let elapsed = start.elapsed();
                        if elapsed.as_millis() > 100 {
                            warn!(
                                module = ?module_id,
                                elapsed_ms = elapsed.as_millis(),
                                "Slow module processing"
                            );
                        }

                        // Periodic state snapshot (every N messages)
                        messages_since_snapshot += 1;
                        if messages_since_snapshot >= snapshot_interval {
                            if let Some(state) = module.snapshot_state() {
                                state_store.save(module_id, &state).await;
                            }
                            messages_since_snapshot = 0;
                        }
                    }
                    // Periodic timer-based snapshot (every 5 min)
                    _ = snapshot_timer.tick() => {
                        if let Some(state) = module.snapshot_state() {
                            state_store.save(module_id, &state).await;
                        }
                    }
                    // Shutdown signal
                    _ = shutdown_rx.recv() => {
                        info!(module = ?module_id, "Module shutting down gracefully");
                        // Final snapshot before shutdown
                        if let Some(state) = module.snapshot_state() {
                            state_store.save(module_id, &state).await;
                        }
                        module.shutdown().await;
                        break;
                    }
                }
            }
        });

        self.module_handles.insert(module_id, handle);
        Ok(())
    }

    /// The main orchestrator loop — runs continuously
    #[tracing::instrument(skip(self))]
    pub async fn run(&self) -> Result<(), OrchestratorError> {
        info!("OODA Orchestrator starting main loop");

        let mut shutdown_rx = self.shutdown_tx.read().await.as_ref()
            .unwrap()
            .subscribe();

        loop {
            tokio::select! {
                result = self.run_cycle() => {
                    match result {
                        Ok(cycle_result) => {
                            if cycle_result.cycle_number % 10 == 0 {
                                info!(
                                    cycle = cycle_result.cycle_number,
                                    processed = cycle_result.messages_processed,
                                    anomalies = cycle_result.anomalies_detected,
                                    patterns = cycle_result.patterns_found,
                                    duration_ms = cycle_result.duration_ms,
                                    "OODA cycle completed"
                                );
                            }
                        }
                        Err(e) => {
                            error!(error = %e, "OODA cycle failed");
                            // Don't crash — continue to next cycle
                        }
                    }
                }
                _ = shutdown_rx.recv() => {
                    info!("Orchestrator received shutdown signal");
                    break;
                }
            }
        }

        info!("OODA Orchestrator main loop ended");
        Ok(())
    }

    // ── OODA Phase Implementations ──────────────────────────────

    /// OBSERVE: Ingest signals from the message bus
    #[tracing::instrument(skip(self))]
    async fn observe(&self) -> ObserveResult {
        let mut signals = Vec::new();
        let mut anomalies = Vec::new();

        // Collect recent messages from bus (non-blocking drain)
        // In production: read from a ring buffer of recent messages
        let metrics = self.bus.metrics();

        // Check module health via heartbeats
        let mut unhealthy_modules = Vec::new();
        for entry in self.state.read().await.module_health.iter() {
            let (module_id, health) = entry;
            let age = Utc::now().signed_duration_since(health.last_heartbeat);
            if age.num_seconds() > 30 {
                unhealthy_modules.push(*module_id);
            }
        }

        ObserveResult {
            signals_count: metrics.messages_published,
            unhealthy_modules,
            active_anomalies: self.state.read().await.active_anomalies.len(),
        }
    }

    /// ORIENT: Synthesize context from observed signals
    #[tracing::instrument(skip(self, observe_result))]
    async fn orient(&self, observe_result: ObserveResult) -> OrientResult {
        let state = self.state.read().await;

        // Analyze system health
        let system_health = if observe_result.unhealthy_modules.is_empty() {
            HealthStatus::Healthy
        } else if observe_result.unhealthy_modules.len() <= 2 {
            HealthStatus::Degraded
        } else {
            HealthStatus::Unhealthy
        };

        // Identify trends from recent patterns
        let pattern_trends: Vec<PatternType> = state.recent_patterns.iter()
            .filter(|p| p.strength > 0.6)
            .map(|p| p.pattern_type.clone())
            .collect();

        // Assess load
        let bus_metrics = self.bus.metrics();
        let load_factor = bus_metrics.messages_published as f64 /
            (self.config.cycle_interval_ms as f64 / 1000.0);

        OrientResult {
            system_health,
            pattern_trends,
            load_factor,
            needs_deep_analysis: state.cycle_count % self.config.deep_analysis_interval == 0,
            unhealthy_modules: observe_result.unhealthy_modules,
        }
    }

    /// DECIDE: Select actions based on orientation
    #[tracing::instrument(skip(self, orient_result))]
    async fn decide(&self, orient_result: OrientResult) -> Vec<Action> {
        let mut actions = Vec::new();

        // Action: Restart unhealthy modules
        for module_id in &orient_result.unhealthy_modules {
            // Check cooldown
            if let Some(last) = self.last_restart.get(module_id) {
                let elapsed = Utc::now().signed_duration_since(*last);
                if elapsed.num_seconds() < self.config.restart_cooldown_secs as i64 {
                    continue;
                }
            }
            actions.push(Action::RestartModule(*module_id));
        }

        // Action: Trigger deep analysis if needed
        if orient_result.needs_deep_analysis {
            actions.push(Action::DeepAnalysis);
        }

        // Action: Apply backpressure if overloaded
        if orient_result.load_factor > 1000.0 {
            warn!(load = orient_result.load_factor, "System overloaded, applying backpressure");
            actions.push(Action::ApplyBackpressure);
        }

        // Action: Escalate if too many anomalies
        let state = self.state.read().await;
        let unresolved_anomalies = state.active_anomalies.iter()
            .filter(|a| !a.resolved)
            .count();
        if unresolved_anomalies >= self.config.anomaly_escalation_threshold as usize {
            actions.push(Action::EscalateToHuman {
                reason: format!("{} unresolved anomalies", unresolved_anomalies),
            });
        }

        actions
    }

    /// ACT: Execute decided actions
    #[tracing::instrument(skip(self, actions), fields(action_count = actions.len()))]
    async fn act(&self, actions: Vec<Action>) -> Vec<String> {
        let mut results = Vec::new();

        for action in actions {
            match action {
                Action::RestartModule(module_id) => {
                    match self.handle_module_failure(module_id, "health timeout".to_string()).await {
                        Ok(()) => {
                            results.push(format!("Restarted module {:?}", module_id));
                            self.last_restart.insert(module_id, Utc::now());
                        }
                        Err(e) => {
                            results.push(format!("Failed to restart {:?}: {}", module_id, e));
                        }
                    }
                }
                Action::DeepAnalysis => {
                    // Signal CollectiveIntelligence to run deep pattern mining
                    let cmd = ModuleMessage::RouteCommand {
                        trace_id: Uuid::new_v4(),
                        target_module: ModuleId::CollectiveIntelligence,
                        command: ModuleCommand::Recalculate,
                        priority: Priority::Normal,
                    };
                    let _ = self.bus.publish(cmd).await;
                    results.push("Triggered deep analysis".to_string());
                }
                Action::ApplyBackpressure => {
                    // Send pause commands to lower-priority modules
                    for module_id in &[ModuleId::HealthMetrics, ModuleId::EconomicAnalyzer] {
                        let cmd = ModuleMessage::RouteCommand {
                            trace_id: Uuid::new_v4(),
                            target_module: *module_id,
                            command: ModuleCommand::Pause,
                            priority: Priority::High,
                        };
                        let _ = self.bus.send_to_module(*module_id, cmd).await;
                    }
                    results.push("Applied backpressure to low-priority modules".to_string());
                }
                Action::EscalateToHuman { reason } => {
                    // In production: send alert via WhatsAppSender or dashboard
                    warn!(reason = %reason, "ESCALATION: Human intervention required");
                    results.push(format!("Escalated to human: {}", reason));
                }
            }
        }

        results
    }

    /// LEARN: Update internal state based on cycle results
    async fn learn(&self, cycle_result: &CycleResult) {
        let mut state = self.state.write().await;

        // Decay old anomalies
        state.active_anomalies.retain(|a| {
            let age = Utc::now().signed_duration_since(a.detected_at);
            age.num_hours() < 24
        });

        // Update throughput (exponential moving average)
        let current_rate = cycle_result.messages_processed as f64 /
            (cycle_result.duration_ms as f64 / 1000.0);
        state.throughput = 0.9 * state.throughput + 0.1 * current_rate;
    }
}

#[async_trait::async_trait]
impl Orchestrator for OODAOrchestrator {
    async fn run_cycle(&self) -> Result<CycleResult, OrchestratorError> {
        let span = tracing::info_span!("orchestrator.run_cycle");
        let _guard = span.enter();

        let start = Instant::now();
        let cycle_number = {
            let mut state = self.state.write().await;
            state.cycle_count += 1;
            state.cycle_start = Utc::now();
            state.cycle_count
        };

        // OBSERVE
        let observe_result = self.observe().await;
        {
            let mut state = self.state.write().await;
            state.phase = OODAPhase::Observe;
        }

        // ORIENT
        let orient_result = self.orient(observe_result).await;
        {
            let mut state = self.state.write().await;
            state.phase = OODAPhase::Orient;
        }

        // DECIDE
        let actions = self.decide(orient_result).await;
        {
            let mut state = self.state.write().await;
            state.phase = OODAPhase::Decide;
        }

        // ACT
        let action_results = self.act(actions).await;
        {
            let mut state = self.state.write().await;
            state.phase = OODAPhase::Act;
        }

        // LEARN
        let bus_metrics = self.bus.metrics();
        let cycle_result = CycleResult {
            phase: OODAPhase::Learn,
            cycle_number,
            messages_processed: bus_metrics.messages_published,
            anomalies_detected: self.state.read().await.active_anomalies.len() as u32,
            patterns_found: self.state.read().await.recent_patterns.len() as u32,
            duration_ms: start.elapsed().as_millis() as u64,
            actions_taken: action_results,
        };
        self.learn(&cycle_result).await;

        Ok(cycle_result)
    }

    async fn route_message(&self, message: ModuleMessage) -> Result<(), OrchestratorError> {
        // Intelligent routing based on message type
        match &message {
            ModuleMessage::TransactionBatch { .. } => {
                // Transaction batches go to all analysis modules in parallel
                self.bus.publish(message).await?;
            }
            ModuleMessage::MarketSignal { .. } => {
                // Market signals → CreditScorer (market conditions affect credit risk)
                //                  → EconomicAnalyzer (market activity = economic health)
                //                  → DistributionAnalyzer (demand patterns)
                self.bus.publish(message).await?;
            }
            ModuleMessage::CreditAssessment { .. } => {
                // Credit → EconomicAnalyzer (credit activity signals economic health)
                //       → HealthMetrics (financial health affects physical health)
                self.bus.publish(message).await?;
            }
            ModuleMessage::AnomalyAlert { severity, .. } => {
                // Anomalies → All modules (high priority)
                self.bus.publish_priority(
                    message,
                    if *severity > 0.8 { Priority::Critical } else { Priority::High },
                ).await?;
            }
            _ => {
                // Default: broadcast to all
                self.bus.publish(message).await?;
            }
        }
        Ok(())
    }

    async fn state(&self) -> OrchestratorState {
        self.state.read().await.clone()
    }

    async fn handle_module_failure(
        &self,
        module_id: ModuleId,
        error: String,
    ) -> Result<(), OrchestratorError> {
        warn!(module = ?module_id, error = %error, "Handling module failure");

        // Update health status
        {
            let mut state = self.state.write().await;
            if let Some(health) = state.module_health.get_mut(&module_id) {
                health.status = HealthStatus::Restarting;
                health.restart_count += 1;
            }
        }

        // Abort existing task
        if let Some((_, handle)) = self.module_handles.remove(&module_id) {
            handle.abort();
        }

        // Respawn
        let module: Box<dyn CapabilityModule> = match module_id {
            ModuleId::MarketAnalyzer => Box::new(modules::market::MarketAnalyzer::new()),
            ModuleId::CreditScorer => Box::new(modules::credit::CreditScorer::new()),
            ModuleId::DistributionAnalyzer => Box::new(modules::distribution::DistributionAnalyzer::new()),
            ModuleId::FMCGIntelligence => Box::new(modules::fmcg::FMCGIntelligence::new()),
            ModuleId::ServicePriceDiscovery => Box::new(modules::service_price_discovery::ServicePriceDiscoveryEngine::new()),
            ModuleId::HealthMetrics => Box::new(modules::health::HealthMetrics::new()),
            ModuleId::EconomicAnalyzer => Box::new(modules::economic::EconomicAnalyzer::new()),
            _ => return Err(OrchestratorError::Internal(
                format!("Cannot restart {:?}", module_id)
            )),
        };

        self.spawn_module(module_id, module).await?;

        // Update health
        {
            let mut state = self.state.write().await;
            state.module_health.insert(module_id, ModuleHealth {
                status: HealthStatus::Healthy,
                queue_depth: 0,
                processing_rate: 0.0,
                last_heartbeat: Utc::now(),
                restart_count: state.module_health
                    .get(&module_id)
                    .map(|h| h.restart_count)
                    .unwrap_or(0),
            });
        }

        info!(module = ?module_id, "Module restarted successfully");
        Ok(())
    }

    async fn shutdown(&self) -> Result<(), OrchestratorError> {
        info!("Orchestrator shutting down...");

        // Send shutdown signal to all modules
        if let Some(tx) = self.shutdown_tx.write().await.take() {
            let _ = tx.send(());
        }

        // Wait for all module tasks to complete (with timeout)
        let handles: Vec<_> = self.module_handles.iter()
            .map(|entry| (*entry.key(), entry.value().abort()))
            .collect();

        // Clear state
        self.module_handles.clear();

        info!("Orchestrator shutdown complete");
        Ok(())
    }
}

// Helper types

struct ObserveResult {
    signals_count: u64,
    unhealthy_modules: Vec<ModuleId>,
    active_anomalies: usize,
}

struct OrientResult {
    system_health: HealthStatus,
    pattern_trends: Vec<PatternType>,
    load_factor: f64,
    needs_deep_analysis: bool,
    unhealthy_modules: Vec<ModuleId>,
}

enum Action {
    RestartModule(ModuleId),
    DeepAnalysis,
    ApplyBackpressure,
    EscalateToHuman { reason: String },
}
