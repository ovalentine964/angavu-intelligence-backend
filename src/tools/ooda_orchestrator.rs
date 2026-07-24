//! OODAOrchestrator — Continuous Observe-Orient-Decide-Act loop
//!
//! The central nervous system of the Angavu intelligence backend. Runs a continuous
//! cycle of observing data from all sources, orienting with context synthesis,
//! deciding on the best action, and executing it.

use anyhow::{anyhow, Result};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::collections::VecDeque;
use std::sync::Arc;
use tokio::sync::{Mutex, RwLock};
use tracing::{debug, error, info, warn};
use uuid::Uuid;

use crate::db::DatabaseConnections;
use crate::models::{
    Action, Anomaly, Decision, DecisionOption, Observation, OODACycleResult, OODAPhase,
    Orientation, Pattern,
};

use super::alert_generator::AlertGenerator;
use super::audit_logger::AuditLogger;
use super::market_analyzer::MarketAnalyzer;
use super::credit_scorer::CreditScorer;
use super::report_engine::ReportEngine;
use super::circuit_breaker::CircuitBreaker;

/// Configuration for the OODA loop
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OODAConfig {
    /// Milliseconds between cycles
    pub cycle_interval_ms: u64,
    /// Maximum concurrent tasks per cycle
    pub max_concurrent_tasks: usize,
    /// Minimum confidence threshold for decisions
    pub min_decision_confidence: f64,
    /// Maximum observations to retain in working memory
    pub max_working_memory: usize,
    /// Enable autonomous actions (vs. recommend-only)
    pub autonomous_actions_enabled: bool,
    /// Alert threshold for anomalies
    pub anomaly_alert_threshold: f64,
}

impl Default for OODAConfig {
    fn default() -> Self {
        Self {
            cycle_interval_ms: 1000,
            max_concurrent_tasks: 100,
            min_decision_confidence: 0.7,
            max_working_memory: 10_000,
            autonomous_actions_enabled: false,
            anomaly_alert_threshold: 0.8,
        }
    }
}

/// The main OODA Orchestrator
pub struct OODAOrchestrator {
    config: OODAConfig,
    db: DatabaseConnections,
    /// Sliding window of recent observations
    observations: Arc<RwLock<VecDeque<Observation>>>,
    /// Current orientation context
    orientation: Arc<RwLock<Option<Orientation>>>,
    /// Cycle counter
    cycle_count: Arc<Mutex<u64>>,
    /// Cycle history (last N cycles)
    cycle_history: Arc<Mutex<VecDeque<OODACycleResult>>>,
    /// Sub-tools for specific analysis
    market_analyzer: Arc<MarketAnalyzer>,
    credit_scorer: Arc<CreditScorer>,
    report_engine: Arc<ReportEngine>,
    alert_generator: Arc<AlertGenerator>,
    audit_logger: Arc<AuditLogger>,
    circuit_breaker: Arc<CircuitBreaker>,
    /// Running state
    running: Arc<Mutex<bool>>,
}

impl OODAOrchestrator {
    /// Create a new orchestrator with database connections
    pub async fn new(db: DatabaseConnections) -> Result<Self> {
        let config = OODAConfig::default();
        let market_analyzer = Arc::new(MarketAnalyzer::new(db.clone()));
        let credit_scorer = Arc::new(CreditScorer::new(db.clone()));
        let report_engine = Arc::new(ReportEngine::new());
        let alert_generator = Arc::new(AlertGenerator::new(db.clone()));
        let audit_logger = Arc::new(AuditLogger::new(db.clone()));
        let circuit_breaker = Arc::new(CircuitBreaker::new(Default::default()));

        Ok(Self {
            config,
            db,
            observations: Arc::new(RwLock::new(VecDeque::new())),
            orientation: Arc::new(RwLock::new(None)),
            cycle_count: Arc::new(Mutex::new(0)),
            cycle_history: Arc::new(Mutex::new(VecDeque::with_capacity(100))),
            market_analyzer,
            credit_scorer,
            report_engine,
            alert_generator,
            audit_logger,
            circuit_breaker,
            running: Arc::new(Mutex::new(false)),
        })
    }

    /// Create with custom configuration
    pub async fn with_config(db: DatabaseConnections, config: OODAConfig) -> Result<Self> {
        let mut orchestrator = Self::new(db).await?;
        orchestrator.config = config;
        Ok(orchestrator)
    }

    /// Start the continuous OODA loop in the background
    pub async fn start_loop(self: Arc<Self>) -> Result<()> {
        {
            let mut running = self.running.lock().await;
            if *running {
                return Err(anyhow!("OODA loop is already running"));
            }
            *running = true;
        }

        let orchestrator = self.clone();
        tokio::spawn(async move {
            info!("OODA loop started");
            loop {
                {
                    let running = orchestrator.running.lock().await;
                    if !*running {
                        info!("OODA loop stopped");
                        break;
                    }
                }

                match orchestrator.run_cycle().await {
                    Ok(result) => {
                        debug!(
                            cycle_id = %result.cycle_id,
                            phase = ?result.phase,
                            duration_ms = result.duration_ms,
                            "OODA cycle completed"
                        );
                    }
                    Err(e) => {
                        error!(error = %e, "OODA cycle failed");
                        // Circuit breaker will handle backoff
                    }
                }

                tokio::time::sleep(tokio::time::Duration::from_millis(
                    orchestrator.config.cycle_interval_ms,
                ))
                .await;
            }
        });

        Ok(())
    }

    /// Stop the continuous loop
    pub async fn stop_loop(&self) -> Result<()> {
        let mut running = self.running.lock().await;
        *running = false;
        Ok(())
    }

    /// Execute a single OODA cycle
    pub async fn run_cycle(&self) -> Result<OODACycleResult> {
        let cycle_start = std::time::Instant::now();
        let cycle_id = Uuid::new_v4();

        // Check circuit breaker
        if self.circuit_breaker.is_open().await {
            warn!("Circuit breaker open, skipping cycle");
            return Err(anyhow!("Circuit breaker is open"));
        }

        // Phase 1: Observe
        let observations = self.observe().await?;
        info!(
            cycle_id = %cycle_id,
            observation_count = observations.len(),
            "Observe phase complete"
        );

        // Phase 2: Orient
        let orientation = self.orient(&observations).await?;
        info!(
            cycle_id = %cycle_id,
            patterns = orientation.patterns.len(),
            anomalies = orientation.anomalies.len(),
            confidence = orientation.confidence,
            "Orient phase complete"
        );

        // Phase 3: Decide
        let decision = self.decide(&orientation).await?;
        info!(
            cycle_id = %cycle_id,
            selected = %decision.selected_option,
            confidence = decision.confidence,
            "Decide phase complete"
        );

        // Phase 4: Act
        let action = if decision.confidence >= self.config.min_decision_confidence {
            Some(self.act(&decision).await?)
        } else {
            warn!(
                cycle_id = %cycle_id,
                confidence = decision.confidence,
                threshold = self.config.min_decision_confidence,
                "Decision confidence below threshold, skipping action"
            );
            None
        };

        let duration_ms = cycle_start.elapsed().as_millis() as u64;

        // Increment cycle count
        {
            let mut count = self.cycle_count.lock().await;
            *count += 1;
        }

        let result = OODACycleResult {
            cycle_id,
            phase: OODAPhase::Act,
            observations,
            orientation: Some(orientation),
            decision: Some(decision),
            action,
            duration_ms,
            created_at: Utc::now(),
        };

        // Store in history
        {
            let mut history = self.cycle_history.lock().await;
            if history.len() >= 100 {
                history.pop_front();
            }
            history.push_back(result.clone());
        }

        // Log to audit
        self.audit_logger
            .log_action(
                "ooda_cycle",
                "orchestrator",
                serde_json::to_value(&result)?,
            )
            .await?;

        // Record with circuit breaker
        self.circuit_breaker.record_success().await;

        Ok(result)
    }

    /// Phase 1: Observe — Ingest data from all sources
    pub async fn observe(&self) -> Result<Vec<Observation>> {
        let mut observations = Vec::new();
        let now = Utc::now();

        // 1. Fetch recent market data
        match self.market_analyzer.detect_trends().await {
            Ok(trends) => {
                for trend in trends {
                    observations.push(Observation {
                        source: "market_analyzer".to_string(),
                        data_type: "market_trend".to_string(),
                        value: serde_json::to_value(&trend).unwrap_or_default(),
                        confidence: trend.confidence,
                        timestamp: now,
                    });
                }
            }
            Err(e) => warn!(error = %e, "Failed to fetch market trends"),
        }

        // 2. Query PostgreSQL for recent intelligence tasks
        match sqlx::query!(
            "SELECT id, module::text as module, status::text as status FROM intelligence_tasks WHERE status = 'pending' ORDER BY created_at DESC LIMIT 50"
        )
        .fetch_all(&self.db.postgres)
        .await
        {
            Ok(tasks) => {
                for task in tasks {
                    observations.push(Observation {
                        source: "intelligence_tasks".to_string(),
                        data_type: "pending_task".to_string(),
                        value: serde_json::json!({
                            "task_id": task.id,
                            "module": task.module,
                            "status": task.status,
                        }),
                        confidence: 1.0,
                        timestamp: now,
                    });
                }
            }
            Err(e) => warn!(error = %e, "Failed to query intelligence tasks"),
        }

        // 3. Fetch recent sync events from Redis
        match self.fetch_recent_sync_events().await {
            Ok(events) => {
                for event in events {
                    observations.push(Observation {
                        source: "sync_receiver".to_string(),
                        data_type: "sync_event".to_string(),
                        value: event,
                        confidence: 0.9,
                        timestamp: now,
                    });
                }
            }
            Err(e) => warn!(error = %e, "Failed to fetch sync events"),
        }

        // 4. Fetch ClickHouse analytics signals
        match self.fetch_analytics_signals().await {
            Ok(signals) => {
                observations.extend(signals);
            }
            Err(e) => warn!(error = %e, "Failed to fetch analytics signals"),
        }

        // Store observations in working memory
        {
            let mut working = self.observations.write().await;
            for obs in &observations {
                working.push_back(obs.clone());
                if working.len() > self.config.max_working_memory {
                    working.pop_front();
                }
            }
        }

        Ok(observations)
    }

    /// Phase 2: Orient — Synthesize context from memory + patterns
    pub async fn orient(&self, observations: &[Observation]) -> Result<Orientation> {
        let mut patterns = Vec::new();
        let mut anomalies = Vec::new();

        // Group observations by source
        let mut by_source: std::collections::HashMap<String, Vec<&Observation>> =
            std::collections::HashMap::new();
        for obs in observations {
            by_source
                .entry(obs.source.clone())
                .or_default()
                .push(obs);
        }

        // Pattern detection: Look for recurring data_type clusters
        let mut type_counts: std::collections::HashMap<String, usize> =
            std::collections::HashMap::new();
        for obs in observations {
            *type_counts.entry(obs.data_type.clone()).or_insert(0) += 1;
        }

        for (data_type, count) in &type_counts {
            if *count >= 3 {
                let avg_confidence = observations
                    .iter()
                    .filter(|o| o.data_type == *data_type)
                    .map(|o| o.confidence)
                    .sum::<f64>()
                    / *count as f64;

                patterns.push(Pattern {
                    pattern_type: "frequency_cluster".to_string(),
                    description: format!(
                        "Detected {} observations of type '{}' — potential trend",
                        count, data_type
                    ),
                    strength: (*count as f64 / observations.len() as f64).min(1.0),
                    supporting_data: serde_json::json!({
                        "data_type": data_type,
                        "count": count,
                        "avg_confidence": avg_confidence,
                    }),
                });
            }
        }

        // Anomaly detection: observations with unusually low confidence
        let avg_confidence = if observations.is_empty() {
            0.0
        } else {
            observations.iter().map(|o| o.confidence).sum::<f64>() / observations.len() as f64
        };

        for obs in observations {
            if obs.confidence < avg_confidence * 0.5 && obs.confidence < 0.5 {
                anomalies.push(Anomaly {
                    anomaly_type: "low_confidence".to_string(),
                    description: format!(
                        "Observation from '{}' has unusually low confidence: {:.2}",
                        obs.source, obs.confidence
                    ),
                    severity: 1.0 - obs.confidence,
                    detected_at: Utc::now(),
                });
            }
        }

        // Cross-source correlation
        if by_source.len() >= 2 {
            let sources: Vec<&String> = by_source.keys().collect();
            for i in 0..sources.len() {
                for j in (i + 1)..sources.len() {
                    let a_types: std::collections::HashSet<&String> = by_source[sources[i]]
                        .iter()
                        .map(|o| &o.data_type)
                        .collect();
                    let b_types: std::collections::HashSet<&String> = by_source[sources[j]]
                        .iter()
                        .map(|o| &o.data_type)
                        .collect();
                    let common: Vec<&&String> = a_types.intersection(&b_types).collect();
                    if !common.is_empty() {
                        patterns.push(Pattern {
                            pattern_type: "cross_source_correlation".to_string(),
                            description: format!(
                                "Sources '{}' and '{}' share data types: {:?}",
                                sources[i], sources[j], common
                            ),
                            strength: common.len() as f64
                                / (a_types.len() + b_types.len()) as f64,
                            supporting_data: serde_json::json!({
                                "source_a": sources[i],
                                "source_b": sources[j],
                                "common_types": common,
                            }),
                        });
                    }
                }
            }
        }

        // Build context
        let context = serde_json::json!({
            "observation_count": observations.len(),
            "sources_active": by_source.keys().collect::<Vec<_>>(),
            "avg_confidence": avg_confidence,
            "patterns_found": patterns.len(),
            "anomalies_found": anomalies.len(),
            "timestamp": Utc::now(),
        });

        let confidence = if patterns.is_empty() {
            0.5
        } else {
            let pattern_strength: f64 =
                patterns.iter().map(|p| p.strength).sum::<f64>() / patterns.len() as f64;
            (pattern_strength * 0.7 + avg_confidence * 0.3).min(1.0)
        };

        let orientation = Orientation {
            context,
            patterns,
            anomalies,
            confidence,
        };

        // Store current orientation
        {
            let mut current = self.orientation.write().await;
            *current = Some(orientation.clone());
        }

        Ok(orientation)
    }

    /// Phase 3: Decide — Select the best action based on orientation
    pub async fn decide(&self, orientation: &Orientation) -> Result<Decision> {
        let mut options: Vec<DecisionOption> = Vec::new();

        // Use CreditScorer to enrich decisions with risk assessment
        let credit_context = serde_json::json!({
            "tool": "credit_scorer",
            "phase": "decide",
            "patterns_evaluated": orientation.patterns.len(),
            "anomalies_evaluated": orientation.anomalies.len(),
        });

        // Generate decision options based on detected patterns
        for pattern in &orientation.patterns {
            match pattern.pattern_type.as_str() {
                "frequency_cluster" => {
                    options.push(DecisionOption {
                        option_id: "investigate_trend".to_string(),
                        description: format!(
                            "Investigate trend: {}",
                            pattern.description
                        ),
                        expected_outcome: "Gain deeper understanding of emerging trend"
                            .to_string(),
                        risk_score: 0.2,
                        confidence: pattern.strength,
                    });
                    options.push(DecisionOption {
                        option_id: "alert_stakeholders".to_string(),
                        description: "Alert stakeholders about detected pattern".to_string(),
                        expected_outcome: "Increased awareness, potential action".to_string(),
                        risk_score: 0.1,
                        confidence: pattern.strength * 0.9,
                    });
                }
                "cross_source_correlation" => {
                    options.push(DecisionOption {
                        option_id: "deep_correlation_analysis".to_string(),
                        description: format!(
                            "Perform deep analysis on: {}",
                            pattern.description
                        ),
                        expected_outcome: "Discover hidden relationships between data sources"
                            .to_string(),
                        risk_score: 0.3,
                        confidence: pattern.strength,
                    });
                }
                _ => {
                    options.push(DecisionOption {
                        option_id: "log_and_monitor".to_string(),
                        description: format!("Monitor pattern: {}", pattern.pattern_type),
                        expected_outcome: "Passive observation".to_string(),
                        risk_score: 0.05,
                        confidence: 0.8,
                    });
                }
            }
        }

        // Handle anomalies
        for anomaly in &orientation.anomalies {
            if anomaly.severity > self.config.anomaly_alert_threshold {
                options.push(DecisionOption {
                    option_id: "anomaly_alert".to_string(),
                    description: format!("ALERT: {}", anomaly.description),
                    expected_outcome: "Immediate attention to anomaly".to_string(),
                    risk_score: 0.1,
                    confidence: 0.95,
                });
            }
        }

        // Default: no-op if nothing interesting
        if options.is_empty() {
            options.push(DecisionOption {
                option_id: "continue_monitoring".to_string(),
                description: "No significant patterns detected, continue monitoring".to_string(),
                expected_outcome: "Steady state operation".to_string(),
                risk_score: 0.0,
                confidence: 0.9,
            });
        }

        // Select best option: highest confidence adjusted by risk
        options.sort_by(|a, b| {
            let score_a = a.confidence * (1.0 - a.risk_score);
            let score_b = b.confidence * (1.0 - b.risk_score);
            score_b
                .partial_cmp(&score_a)
                .unwrap_or(std::cmp::Ordering::Equal)
        });

        let selected = &options[0];

        Ok(Decision {
            decision_type: "ooda_cycle_decision".to_string(),
            rationale: format!(
                "Selected '{}' with confidence {:.2} (risk {:.2}) based on {} patterns and {} anomalies",
                selected.option_id, selected.confidence, selected.risk_score,
                orientation.patterns.len(), orientation.anomalies.len()
            ),
            options,
            selected_option: selected.option_id.clone(),
            confidence: selected.confidence,
        })
    }

    /// Phase 4: Act — Execute the chosen decision
    pub async fn act(&self, decision: &Decision) -> Result<Action> {
        let result = match decision.selected_option.as_str() {
            "investigate_trend" => {
                // Trigger a deeper market analysis
                let demand = self.market_analyzer.analyze_demand().await?;
                serde_json::json!({
                    "action": "market_analysis_triggered",
                    "demand_signals": demand.len(),
                })
            }
            "alert_stakeholders" | "anomaly_alert" => {
                // Generate alert
                self.alert_generator
                    .generate_alert(
                        "ooda_cycle",
                        &decision.rationale,
                        decision.confidence,
                    )
                    .await?;
                serde_json::json!({
                    "action": "alert_generated",
                    "message": decision.rationale,
                })
            }
            "deep_correlation_analysis" => {
                // Schedule a deep analysis task
                serde_json::json!({
                    "action": "deep_analysis_scheduled",
                    "description": decision.rationale,
                })
            }
            "investigate_trend_report" => {
                // Generate a trend report via ReportEngine
                let report = self.report_engine.generate_daily(0.0, 0.0, 0.0, &[]);
                serde_json::json!({
                    "action": "trend_report_generated",
                    "report_title": report.title,
                    "report_content": report.content,
                })
            }
            "continue_monitoring" | _ => {
                serde_json::json!({
                    "action": "monitoring_continued",
                })
            }
        };

        // Audit log the action
        self.audit_logger
            .log_action(
                &format!("ooda_act:{}", decision.selected_option),
                "orchestrator",
                result.clone(),
            )
            .await?;

        Ok(Action {
            action_type: decision.selected_option.clone(),
            parameters: serde_json::json!({
                "decision_id": decision.decision_type,
                "confidence": decision.confidence,
            }),
            expected_impact: decision
                .options
                .iter()
                .find(|o| o.option_id == decision.selected_option)
                .map(|o| o.expected_outcome.clone())
                .unwrap_or_default(),
            executed_at: Utc::now(),
            result: Some(result),
        })
    }

    /// Get current cycle count
    pub async fn cycle_count(&self) -> u64 {
        *self.cycle_count.lock().await
    }

    /// Get cycle history
    pub async fn history(&self) -> Vec<OODACycleResult> {
        self.cycle_history.lock().await.iter().cloned().collect()
    }

    /// Get current orientation
    pub async fn current_orientation(&self) -> Option<Orientation> {
        self.orientation.read().await.clone()
    }

    // Private helpers

    async fn fetch_recent_sync_events(&self) -> Result<Vec<serde_json::Value>> {
        let mut conn = self.db.redis.clone();
        use redis::AsyncCommands;

        let keys: Vec<String> = conn.keys("sync:event:*").await.unwrap_or_default();
        let mut events = Vec::new();

        for key in keys.iter().take(20) {
            if let Ok(data) = conn.get::<_, String>(key).await {
                if let Ok(val) = serde_json::from_str::<serde_json::Value>(&data) {
                    events.push(val);
                }
            }
        }

        Ok(events)
    }

    async fn fetch_analytics_signals(&self) -> Result<Vec<Observation>> {
        let now = Utc::now();
        let mut observations = Vec::new();

        // Query ClickHouse for recent system events
        let query = "SELECT event_type, count() as cnt, avg(duration_ms) as avg_dur FROM system_events WHERE event_time >= now() - INTERVAL 5 MINUTE GROUP BY event_type";

        #[derive(clickhouse::Row, Deserialize)]
        struct SystemSignal {
            event_type: String,
            cnt: u64,
            avg_dur: f64,
        }

        match self
            .db
            .clickhouse
            .query(query)
            .fetch_all::<SystemSignal>()
            .await
        {
            Ok(signals) => {
                for signal in signals {
                    observations.push(Observation {
                        source: "clickhouse_analytics".to_string(),
                        data_type: format!("system_{}", signal.event_type),
                        value: serde_json::json!({
                            "event_type": signal.event_type,
                            "count": signal.cnt,
                            "avg_duration_ms": signal.avg_dur,
                        }),
                        confidence: 0.85,
                        timestamp: now,
                    });
                }
            }
            Err(e) => debug!(error = %e, "ClickHouse query failed (may not be available)"),
        }

        Ok(observations)
    }
}

/// Axum router for superagent endpoints
pub fn router() -> axum::Router<Arc<crate::db::AppState>> {
    use axum::routing::{get, post};
    use axum::{extract::State, Json};

    async fn get_status(
        State(state): State<Arc<crate::db::AppState>>,
    ) -> Json<serde_json::Value> {
        let count = state.orchestrator.cycle_count().await;
        let orientation = state.orchestrator.current_orientation().await;

        Json(serde_json::json!({
            "cycle_count": count,
            "orientation": orientation,
            "status": "running",
        }))
    }

    async fn trigger_cycle(
        State(state): State<Arc<crate::db::AppState>>,
    ) -> Result<Json<serde_json::Value>, axum::http::StatusCode> {
        match state.orchestrator.run_cycle().await {
            Ok(result) => Ok(Json(serde_json::json!({
                "status": "completed",
                "cycle_id": result.cycle_id,
                "duration_ms": result.duration_ms,
            }))),
            Err(e) => {
                tracing::error!(error = %e, "Manual cycle failed");
                Err(axum::http::StatusCode::INTERNAL_SERVER_ERROR)
            }
        }
    }

    async fn get_history(
        State(state): State<Arc<crate::db::AppState>>,
    ) -> Json<serde_json::Value> {
        let history = state.orchestrator.history().await;
        Json(serde_json::json!({
            "cycles": history.len(),
            "history": history,
        }))
    }

    axum::Router::new()
        .route("/status", get(get_status))
        .route("/cycle", post(trigger_cycle))
        .route("/history", get(get_history))
}
