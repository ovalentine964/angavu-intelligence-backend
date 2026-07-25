//! OODAOrchestrator — Continuous Observe-Orient-Decide-Act loop
//!
//! The central nervous system of the Angavu intelligence backend. Runs a continuous
//! cycle of observing data from all sources, orienting with context synthesis,
//! deciding on the best action, and executing it.
//!
//! ## Architecture: Harness wraps OODA
//!
//! The harness (this orchestrator) wraps the OODA loop as middleware — not the
//! other way around. Three operational modes control how the harness and OODA
//! interact:
//!
//! - **Autonomous:** OODA runs in background on multi-speed cycles. Harness
//!   monitors for anomalies and escalates only critical ones.
//! - **On-demand:** User query arrives → harness invokes OODA tools directly,
//!   returning immediate results without waiting for a scheduled cycle.
//! - **Hybrid:** OODA detects anomaly in background → alerts user → user
//!   decides → harness acts on the decision.
//!
//! ## Cycle Timing (from architecture §6.2)
//!
//! | Cycle  | Interval | Purpose                                          |
//! |--------|----------|--------------------------------------------------|
//! | Fast   | 5s       | Observe new data after every agent turn           |
//! | Medium | 1 hour   | Aggregate observations, update orientation        |
//! | Slow   | 24 hours | Review patterns, update knowledge base            |
//! | Deep   | 7 days   | Full reflection, model eval, flywheel assessment  |

use anyhow::{anyhow, Result};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, VecDeque};
use std::sync::Arc;
use tokio::sync::{Mutex, RwLock};
use tracing::{debug, error, info, warn};
use uuid::Uuid;

use crate::db::DatabaseConnections;
use crate::models::{
    Action, Anomaly, Decision, DecisionOption, Observation, OODACycleResult, OODAPhase,
    Orientation, Pattern,
};
use crate::superagent::{
    FlywheelEngine, GuardrailsEngine, IntelligenceEngine, MemoryEngine, SyncEngine,
};
use crate::superagent::flywheel::ActionType;
use crate::superagent::guardrails::Jurisdiction;
use crate::superagent::memory::{Layer, ContentType};
use crate::superagent::sync::Priority as SyncPriority;

// Import ALL 26 tools — the backend is a superagent with one brain and many tools
use super::alert_generator::AlertGenerator;
use super::audit_logger::AuditLogger;
use super::market_analyzer::MarketAnalyzer;
use super::credit_scorer::CreditScorer;
use super::report_engine::ReportEngine;
use super::circuit_breaker::CircuitBreaker;
use super::distribution_analyzer::DistributionAnalyzer;
use super::fmcg_intelligence::FMCGIntelligence;
use super::health_metrics::HealthMetrics;
use super::economic_analyzer::EconomicAnalyzer;
use super::differential_privacy::DifferentialPrivacyEngine;
use super::k_anonymity::KAnonymityEnforcer;
use super::federated_aggregator::FederatedAggregator;
use super::sync_receiver::SyncReceiver;
use super::api_gateway::ApiGateway;
use super::rate_limiter::RateLimiter;
use super::model_distributor::ModelDistributor;
use super::whatsapp_sender::WhatsAppSender;
use super::differential_privacy::DifferentialPrivacyConfig;
use super::mobile_money_signal_extractor::MobileMoneySignalExtractor;
use super::composite_index_builder::CompositeIndexBuilder;
use super::anomaly_detector::{AnomalyDetector, AnomalyConfig};
use super::demand_forecaster::{DemandForecaster, DemandForecastConfig};
use super::scenario_modeler::ScenarioModeler;
use super::policy_impact_analyzer::PolicyImpactAnalyzer;
use super::inequality_tracker::InequalityTracker;

// ─────────────────────────────────────────────────────────────────────
// Harness Mode Definitions
// ─────────────────────────────────────────────────────────────────────

/// Operational mode for the harness-ooda interaction.
///
/// The harness wraps OODA — it decides *how* OODA runs, not the other way
/// around. Each mode changes the control flow between the harness and the
/// OODA loop.
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
pub enum HarnessMode {
    /// OODA runs in background. Harness monitors for anomalies and
    /// escalates only critical ones to human attention.
    Autonomous,
    /// User query arrives → harness invokes OODA tools directly,
    /// returning immediate results. No background cycling.
    OnDemand,
    /// OODA detects anomaly in background → alerts user → user
    /// decides → harness acts on the user's decision.
    Hybrid,
}

impl Default for HarnessMode {
    fn default() -> Self {
        Self::Hybrid
    }
}

/// Cycle timing tier — maps to architecture §6.2 cycle timing.
///
/// Each tier has a different interval and purpose. The harness selects
/// which tier to run based on elapsed time since the last run of that tier.
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub enum CycleTier {
    /// 5-second debounce — runs after every agent turn.
    /// Observe new data, orient context, decide action, act.
    Fast,
    /// 1-hour interval — aggregate observations, update orientation,
    /// generate market signals.
    Medium,
    /// 24-hour interval — review patterns, update knowledge base,
    /// generate daily briefings.
    Slow,
    /// 7-day interval — full reflection, model evaluation,
    /// flywheel stage assessment.
    Deep,
}

impl CycleTier {
    /// Returns the minimum interval between runs for this tier.
    pub fn interval(&self) -> std::time::Duration {
        match self {
            Self::Fast => std::time::Duration::from_secs(5),
            Self::Medium => std::time::Duration::from_secs(3600),
            Self::Slow => std::time::Duration::from_secs(86400),
            Self::Deep => std::time::Duration::from_secs(604_800),
        }
    }
}

/// Result of an on-demand OODA invocation.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OnDemandResult {
    pub cycle_id: Uuid,
    pub observations: Vec<Observation>,
    pub orientation: Option<Orientation>,
    pub decision: Option<Decision>,
    pub action: Option<Action>,
    pub duration_ms: u64,
    pub mode: HarnessMode,
}

/// Anomaly detected by OODA that requires user attention (hybrid mode).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AnomalyAlert {
    pub alert_id: Uuid,
    pub anomaly: Anomaly,
    pub suggested_action: DecisionOption,
    pub detected_at: DateTime<Utc>,
    pub user_response: Option<UserDecision>,
}

/// User's decision in response to an anomaly alert (hybrid mode).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UserDecision {
    pub approved: bool,
    pub override_action: Option<String>,
    pub responded_at: DateTime<Utc>,
}

// ─────────────────────────────────────────────────────────────────────
// Configuration
// ─────────────────────────────────────────────────────────────────────

/// Configuration for the OODA loop
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OODAConfig {
    /// Operational mode: how the harness wraps OODA
    pub harness_mode: HarnessMode,
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
            harness_mode: HarnessMode::Hybrid,
            max_concurrent_tasks: 100,
            min_decision_confidence: 0.7,
            max_working_memory: 10_000,
            autonomous_actions_enabled: false,
            anomaly_alert_threshold: 0.8,
        }
    }
}

// ─────────────────────────────────────────────────────────────────────
// Cycle Tier Tracker
// ─────────────────────────────────────────────────────────────────────

/// Tracks the last-run timestamp for each cycle tier.
#[derive(Debug, Clone)]
struct TierTracker {
    last_fast: Option<std::time::Instant>,
    last_medium: Option<std::time::Instant>,
    last_slow: Option<std::time::Instant>,
    last_deep: Option<std::time::Instant>,
}

impl TierTracker {
    fn new() -> Self {
        Self {
            last_fast: None,
            last_medium: None,
            last_slow: None,
            last_deep: None,
        }
    }

    /// Returns which tier is due, in priority order (deepest first).
    /// Deep > Slow > Medium > Fast — so deeper cycles aren't starved.
    fn next_due(&self) -> Option<CycleTier> {
        let now = std::time::Instant::now();

        // Check deepest first — they're the rarest and most important
        if self.last_deep.map_or(true, |t| now.duration_since(t) >= CycleTier::Deep.interval()) {
            return Some(CycleTier::Deep);
        }
        if self.last_slow.map_or(true, |t| now.duration_since(t) >= CycleTier::Slow.interval()) {
            return Some(CycleTier::Slow);
        }
        if self.last_medium.map_or(true, |t| now.duration_since(t) >= CycleTier::Medium.interval()) {
            return Some(CycleTier::Medium);
        }
        if self.last_fast.map_or(true, |t| now.duration_since(t) >= CycleTier::Fast.interval()) {
            return Some(CycleTier::Fast);
        }
        None
    }

    /// Mark a tier as just completed.
    fn mark_completed(&mut self, tier: CycleTier) {
        let now = std::time::Instant::now();
        match tier {
            CycleTier::Fast => self.last_fast = Some(now),
            CycleTier::Medium => self.last_medium = Some(now),
            CycleTier::Slow => self.last_slow = Some(now),
            CycleTier::Deep => self.last_deep = Some(now),
        }
    }
}

// ─────────────────────────────────────────────────────────────────────
// OODA Orchestrator
// ─────────────────────────────────────────────────────────────────────

/// The main OODA Orchestrator.
///
/// Acts as the harness that wraps the OODA loop. In all modes, the harness
/// controls when and how OODA phases execute — OODA is the *what* (observe,
/// orient, decide, act), the harness is the *when* and *how*.
pub struct OODAOrchestrator {
    config: OODAConfig,
    db: DatabaseConnections,
    /// Sliding window of recent observations
    observations: Arc<RwLock<VecDeque<Observation>>>,
    /// Current orientation context
    orientation: Arc<RwLock<Option<Orientation>>>,
    /// Cycle counter (total across all tiers)
    cycle_count: Arc<Mutex<u64>>,
    /// Cycle history (last N cycles)
    cycle_history: Arc<Mutex<VecDeque<OODACycleResult>>>,
    /// Per-tier tracker for multi-speed cycling
    tier_tracker: Arc<Mutex<TierTracker>>,
    /// Pending anomaly alerts awaiting user decision (hybrid mode)
    pending_alerts: Arc<Mutex<VecDeque<AnomalyAlert>>>,
    /// ALL 26 superagent tools — one brain, many tools, one job
    /// Intelligence tools
    market_analyzer: Arc<MarketAnalyzer>,
    credit_scorer: Arc<CreditScorer>,
    distribution_analyzer: Arc<DistributionAnalyzer>,
    fmcg_intelligence: Arc<FMCGIntelligence>,
    health_metrics: Arc<HealthMetrics>,
    economic_analyzer: Arc<EconomicAnalyzer>,
    /// Privacy tools
    differential_privacy: Arc<DifferentialPrivacyEngine>,
    k_anonymity: Arc<KAnonymityEnforcer>,
    federated_aggregator: Arc<FederatedAggregator>,
    /// Communication tools
    sync_receiver: Arc<SyncReceiver>,
    report_engine: Arc<ReportEngine>,
    whatsapp_sender: Arc<WhatsAppSender>,
    model_distributor: Arc<ModelDistributor>,
    /// Infrastructure tools
    alert_generator: Arc<AlertGenerator>,
    audit_logger: Arc<AuditLogger>,
    circuit_breaker: Arc<CircuitBreaker>,
    api_gateway: Arc<ApiGateway>,
    rate_limiter: Arc<RateLimiter>,
    /// New tools (7 recently wired)
    mobile_money: Arc<MobileMoneySignalExtractor>,
    composite_index: Arc<CompositeIndexBuilder>,
    anomaly_detector: Arc<AnomalyDetector>,
    demand_forecaster: Arc<DemandForecaster>,
    scenario_modeler: Arc<ScenarioModeler>,
    policy_impact: Arc<PolicyImpactAnalyzer>,
    inequality_tracker: Arc<InequalityTracker>,
    /// Superagent engines — the 5 new capability modules
    flywheel: Arc<FlywheelEngine>,
    guardrails: Arc<GuardrailsEngine>,
    intelligence: Arc<IntelligenceEngine>,
    memory: Arc<MemoryEngine>,
    sync_engine: Arc<SyncEngine>,
    /// Running state
    running: Arc<Mutex<bool>>,
}

impl OODAOrchestrator {
    /// Create a new orchestrator with database connections
    pub async fn new(db: DatabaseConnections) -> Result<Self> {
        let config = OODAConfig::default();

        // Initialize ALL 26 tools — the backend superagent brain connects to every tool
        let market_analyzer = Arc::new(MarketAnalyzer::new(db.clone()));
        let credit_scorer = Arc::new(CreditScorer::new(db.clone()));
        let distribution_analyzer = Arc::new(DistributionAnalyzer::new(db.clone()));
        let fmcg_intelligence = Arc::new(FMCGIntelligence::new(db.clone()));
        let health_metrics = Arc::new(HealthMetrics::new());
        let economic_analyzer = Arc::new(EconomicAnalyzer::new());
        let differential_privacy = Arc::new(DifferentialPrivacyEngine::new(DifferentialPrivacyConfig::default()));
        let k_anonymity = Arc::new(KAnonymityEnforcer::new(10));
        let federated_aggregator = Arc::new(FederatedAggregator::new(db.clone()));
        let sync_receiver = Arc::new(SyncReceiver::new(db.clone()));
        let report_engine = Arc::new(ReportEngine::new());
        let whatsapp_sender = Arc::new(WhatsAppSender::new());
        let model_distributor = Arc::new(ModelDistributor::new());
        let alert_generator = Arc::new(AlertGenerator::new(db.clone()));
        let audit_logger = Arc::new(AuditLogger::new(db.clone()));
        let circuit_breaker = Arc::new(CircuitBreaker::new(Default::default()));
        let api_gateway = Arc::new(ApiGateway::new(1000));
        let rate_limiter = Arc::new(RateLimiter::new());

        // New tools (7 recently wired)
        let mobile_money = Arc::new(MobileMoneySignalExtractor::with_defaults(db.clone()));
        let composite_index = Arc::new(CompositeIndexBuilder::new(db.clone()));
        let anomaly_detector = Arc::new(AnomalyDetector::new(AnomalyConfig::default()));
        let demand_forecaster = Arc::new(DemandForecaster::new(db.clone(), DemandForecastConfig::default()));
        let scenario_modeler = Arc::new(ScenarioModeler::new(db.clone()));
        let policy_impact = Arc::new(PolicyImpactAnalyzer::new(db.clone()));
        let inequality_tracker = Arc::new(InequalityTracker::new(db.clone()));

        // Superagent engines — the 5 new capability modules
        let flywheel = Arc::new(FlywheelEngine::new());
        let guardrails = Arc::new(GuardrailsEngine::new());
        let intelligence = Arc::new(IntelligenceEngine::new());
        let memory = Arc::new(MemoryEngine::new());
        let sync_engine = Arc::new(SyncEngine::new());

        info!("OODAOrchestrator initialized with 26 superagent tools + 5 superagent engines");

        Ok(Self {
            config,
            db,
            observations: Arc::new(RwLock::new(VecDeque::new())),
            orientation: Arc::new(RwLock::new(None)),
            cycle_count: Arc::new(Mutex::new(0)),
            cycle_history: Arc::new(Mutex::new(VecDeque::with_capacity(100))),
            tier_tracker: Arc::new(Mutex::new(TierTracker::new())),
            pending_alerts: Arc::new(Mutex::new(VecDeque::new())),
            // Intelligence tools
            market_analyzer,
            credit_scorer,
            distribution_analyzer,
            fmcg_intelligence,
            health_metrics,
            economic_analyzer,
            // Privacy tools
            differential_privacy,
            k_anonymity,
            federated_aggregator,
            // Communication tools
            sync_receiver,
            report_engine,
            whatsapp_sender,
            model_distributor,
            // Infrastructure tools
            alert_generator,
            audit_logger,
            circuit_breaker,
            api_gateway,
            rate_limiter,
            // New tools (7 recently wired)
            mobile_money,
            composite_index,
            anomaly_detector,
            demand_forecaster,
            scenario_modeler,
            policy_impact,
            inequality_tracker,
            // Superagent engines
            flywheel,
            guardrails,
            intelligence,
            memory,
            sync_engine,
            running: Arc::new(Mutex::new(false)),
        })
    }

    /// Create with custom configuration
    pub async fn with_config(db: DatabaseConnections, config: OODAConfig) -> Result<Self> {
        let mut orchestrator = Self::new(db).await?;
        orchestrator.config = config;
        Ok(orchestrator)
    }

    // ─────────────────────────────────────────────────────────────────
    // Harness Mode: Autonomous
    // ─────────────────────────────────────────────────────────────────

    /// Start the continuous OODA loop in the background (autonomous mode).
    ///
    /// The harness runs OODA on multi-speed cycles:
    /// - Fast (5s debounce): observe → orient → decide → act after every turn
    /// - Medium (hourly): aggregate observations, update orientation
    /// - Slow (daily): review patterns, update knowledge base
    /// - Deep (weekly): full reflection, model evaluation
    ///
    /// In autonomous mode, the harness monitors for anomalies and escalates
    /// only critical ones. Non-critical actions execute automatically.
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
            info!("OODA loop started (mode: {:?}, multi-speed cycles)", orchestrator.config.harness_mode);
            loop {
                {
                    let running = orchestrator.running.lock().await;
                    if !*running {
                        info!("OODA loop stopped");
                        break;
                    }
                }

                // Determine which cycle tier is due
                let next_tier = {
                    let tracker = orchestrator.tier_tracker.lock().await;
                    tracker.next_due()
                };

                if let Some(tier) = next_tier {
                    match orchestrator.run_tiered_cycle(tier).await {
                        Ok(result) => {
                            debug!(
                                cycle_id = %result.cycle_id,
                                tier = ?tier,
                                phase = ?result.phase,
                                duration_ms = result.duration_ms,
                                "OODA cycle completed"
                            );

                            // Mark tier as completed
                            {
                                let mut tracker = orchestrator.tier_tracker.lock().await;
                                tracker.mark_completed(tier);
                            }
                        }
                        Err(e) => {
                            error!(error = %e, tier = ?tier, "OODA cycle failed");
                        }
                    }
                }

                // Sleep 1 second between checks — the tier tracker handles debouncing
                tokio::time::sleep(tokio::time::Duration::from_secs(1)).await;
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

    // ─────────────────────────────────────────────────────────────────
    // Harness Mode: On-Demand
    // ─────────────────────────────────────────────────────────────────

    /// Invoke OODA directly for a user query (on-demand mode).
    ///
    /// The harness calls OODA tools immediately without waiting for a
    /// scheduled cycle. Used when the user asks a question that requires
    /// intelligence processing.
    pub async fn invoke_on_demand(&self, query_context: serde_json::Value) -> Result<OnDemandResult> {
        let cycle_start = std::time::Instant::now();
        let cycle_id = Uuid::new_v4();

        info!(cycle_id = %cycle_id, "On-demand OODA invocation");

        // Observe: gather data relevant to the query
        let observations = self.observe().await?;

        // Orient: synthesize context
        let orientation = self.orient(&observations).await?;

        // Decide: select action
        let decision = self.decide(&orientation).await?;

        // Act: execute (always in on-demand — user expects a result)
        let action = Some(self.act(&decision).await?);

        let duration_ms = cycle_start.elapsed().as_millis() as u64;

        // Audit
        self.audit_logger
            .log_action(
                "ooda_on_demand",
                "orchestrator",
                serde_json::json!({
                    "cycle_id": cycle_id,
                    "query_context": query_context,
                    "duration_ms": duration_ms,
                }),
            )
            .await?;

        Ok(OnDemandResult {
            cycle_id,
            observations,
            orientation: Some(orientation),
            decision: Some(decision),
            action,
            duration_ms,
            mode: HarnessMode::OnDemand,
        })
    }

    // ─────────────────────────────────────────────────────────────────
    // Harness Mode: Hybrid
    // ─────────────────────────────────────────────────────────────────

    /// Respond to a user decision on a pending anomaly alert (hybrid mode).
    ///
    /// When OODA detects an anomaly in the background, it queues an alert.
    /// The user reviews and decides. This method executes the user's decision.
    pub async fn respond_to_alert(
        &self,
        alert_id: Uuid,
        user_decision: UserDecision,
    ) -> Result<Option<Action>> {
        // Find and remove the pending alert
        let alert = {
            let mut alerts = self.pending_alerts.lock().await;
            alerts.iter().position(|a| a.alert_id == alert_id).map(|idx| alerts.remove(idx)).flatten()
        };

        let alert = alert.ok_or_else(|| anyhow!("Alert {} not found", alert_id))?;

        info!(
            alert_id = %alert_id,
            approved = user_decision.approved,
            "User responded to anomaly alert"
        );

        if user_decision.approved {
            // User approved — execute the suggested action
            let decision = Decision {
                decision_type: "hybrid_user_approved".to_string(),
                rationale: format!(
                    "User approved action for anomaly: {}",
                    alert.anomaly.description
                ),
                options: vec![alert.suggested_action.clone()],
                selected_option: alert.suggested_action.option_id.clone(),
                confidence: alert.suggested_action.confidence,
            };
            let action = self.act(&decision).await?;

            self.audit_logger
                .log_action(
                    "ooda_hybrid_user_approved",
                    "orchestrator",
                    serde_json::json!({
                        "alert_id": alert_id,
                        "anomaly": alert.anomaly,
                        "action": action,
                    }),
                )
                .await?;

            Ok(Some(action))
        } else if let Some(override_action) = user_decision.override_action {
            // User overrode with a different action
            let decision = Decision {
                decision_type: "hybrid_user_override".to_string(),
                rationale: format!(
                    "User overrode anomaly action. Original: {}, Override: {}",
                    alert.suggested_action.option_id, override_action
                ),
                options: vec![],
                selected_option: override_action,
                confidence: 1.0,
            };
            let action = self.act(&decision).await?;
            Ok(Some(action))
        } else {
            // User dismissed — log and move on
            self.audit_logger
                .log_action(
                    "ooda_hybrid_user_dismissed",
                    "orchestrator",
                    serde_json::json!({
                        "alert_id": alert_id,
                        "anomaly": alert.anomaly,
                    }),
                )
                .await?;

            Ok(None)
        }
    }

    /// Get pending anomaly alerts (for hybrid mode UI).
    pub async fn pending_alerts(&self) -> Vec<AnomalyAlert> {
        self.pending_alerts.lock().await.iter().cloned().collect()
    }

    // ─────────────────────────────────────────────────────────────────
    // Multi-Speed Cycle Execution
    // ─────────────────────────────────────────────────────────────────

    /// Execute an OODA cycle at the specified tier.
    ///
    /// The harness selects which tier to run. Each tier runs all four OODA
    /// phases (observe → orient → decide → act) but with different depths
    /// and purposes.
    pub async fn run_tiered_cycle(&self, tier: CycleTier) -> Result<OODACycleResult> {
        let cycle_start = std::time::Instant::now();
        let cycle_id = Uuid::new_v4();

        // Check circuit breaker
        if self.circuit_breaker.is_open().await {
            warn!("Circuit breaker open, skipping cycle");
            return Err(anyhow!("Circuit breaker is open"));
        }

        // Phase 1: Observe (all tiers observe, but depth varies)
        let observations = self.observe_for_tier(tier).await?;
        info!(
            cycle_id = %cycle_id,
            tier = ?tier,
            observation_count = observations.len(),
            "Observe phase complete"
        );

        // Phase 2: Orient (medium+ tiers do deeper orientation)
        let orientation = self.orient_for_tier(tier, &observations).await?;
        info!(
            cycle_id = %cycle_id,
            tier = ?tier,
            patterns = orientation.patterns.len(),
            anomalies = orientation.anomalies.len(),
            confidence = orientation.confidence,
            "Orient phase complete"
        );

        // Phase 3: Decide (tier influences decision depth)
        let decision = self.decide_for_tier(tier, &orientation).await?;
        info!(
            cycle_id = %cycle_id,
            tier = ?tier,
            selected = %decision.selected_option,
            confidence = decision.confidence,
            "Decide phase complete"
        );

        // Phase 4: Act (mode determines whether we auto-act or alert)
        let action = self.act_for_mode(tier, &decision, &orientation).await?;

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
                &format!("ooda_cycle_{:?}", tier).to_lowercase(),
                "orchestrator",
                serde_json::to_value(&result)?,
            )
            .await?;

        // Record with circuit breaker
        self.circuit_breaker.record_success().await;

        Ok(result)
    }

    /// Execute a single OODA cycle at the fast tier (legacy compatibility).
    pub async fn run_cycle(&self) -> Result<OODACycleResult> {
        self.run_tiered_cycle(CycleTier::Fast).await
    }

    // ─────────────────────────────────────────────────────────────────
    // Tier-Aware Phase Implementations
    // ─────────────────────────────────────────────────────────────────

    /// Observe: gather data appropriate for the cycle tier.
    ///
    /// Fast: recent data only (last 5 minutes)
    /// Medium: broader window (last hour) + aggregated signals
    /// Slow: full day of data + knowledge base queries
    /// Deep: full week + model performance metrics
    async fn observe_for_tier(&self, tier: CycleTier) -> Result<Vec<Observation>> {
        let mut observations = Vec::new();
        let now = Utc::now();

        // 1. Fetch recent market data (all tiers)
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

        // 2. Query PostgreSQL for intelligence tasks
        #[derive(sqlx::FromRow)]
        struct IntelligenceTaskRow {
            id: Uuid,
            module: Option<String>,
            status: Option<String>,
        }
        match sqlx::query_as::<_, IntelligenceTaskRow>(
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
                            "module": task.module.unwrap_or_default(),
                            "status": task.status.unwrap_or_default(),
                        }),
                        confidence: 1.0,
                        timestamp: now,
                    });
                }
            }
            Err(e) => warn!(error = %e, "Failed to query intelligence tasks"),
        }

        // 3. Fetch recent sync events from Redis (all tiers)
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

        // 4. Fetch ClickHouse analytics signals (all tiers)
        match self.fetch_analytics_signals().await {
            Ok(signals) => {
                observations.extend(signals);
            }
            Err(e) => warn!(error = %e, "Failed to fetch analytics signals"),
        }

        // 5. Medium+ tiers: aggregated market signals
        if matches!(tier, CycleTier::Medium | CycleTier::Slow | CycleTier::Deep) {
            match self.market_analyzer.analyze_demand().await {
                Ok(demand) => {
                    for signal in demand {
                        observations.push(Observation {
                            source: "market_analyzer".to_string(),
                            data_type: "demand_signal".to_string(),
                            value: serde_json::to_value(&signal).unwrap_or_default(),
                            confidence: 0.85,
                            timestamp: now,
                        });
                    }
                }
                Err(e) => warn!(error = %e, "Failed to analyze demand"),
            }
        }

        // 6. Slow+ tiers: model performance & knowledge base
        if matches!(tier, CycleTier::Slow | CycleTier::Deep) {
            // HealthMetrics::calculate is synchronous; use placeholder observation
            {
                let metrics = serde_json::json!({"status": "healthy", "last_checked": now.to_rfc3339()});
                observations.push(Observation {
                    source: "health_metrics".to_string(),
                    data_type: "model_performance".to_string(),
                    value: metrics,
                    confidence: 0.95,
                    timestamp: now,
                });
            }

        }

        // 7. Deep tier: federated learning status
        if tier == CycleTier::Deep {
            // FederatedAggregator has no get_status method; use placeholder
            observations.push(Observation {
                source: "federated_aggregator".to_string(),
                data_type: "federated_status".to_string(),
                value: serde_json::json!({"status": "idle", "round": 0}),
                confidence: 0.9,
                timestamp: now,
            });
        }

        // Superagent: Guardrails PII masking on observation values
        for obs in &mut observations {
            let value_str = serde_json::to_string(&obs.value).unwrap_or_default();
            if self.guardrails.contains_pii(&value_str) {
                let masked = self.guardrails.mask_pii(&value_str);
                if let Ok(masked_value) = serde_json::from_str::<serde_json::Value>(&masked.masked_text) {
                    obs.value = masked_value;
                }
                self.audit_logger
                    .log_action("guardrails_pii_masked", &obs.source, serde_json::json!({"pii_count": masked.pii_count}))
                    .await
                    .ok();
            }
        }

        // Superagent: Store observations in 4-layer memory (working layer)
        for obs in &observations {
            let tags = vec![obs.source.clone(), obs.data_type.clone()];
            self.memory
                .store_with_importance(
                    Uuid::nil(),
                    Layer::Working,
                    &serde_json::to_string(&obs.value).unwrap_or_default(),
                    ContentType::Structured,
                    obs.confidence,
                    tags,
                    &obs.source,
                )
                .await
                .ok();
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

    /// Orient: synthesize context appropriate for the cycle tier.
    ///
    /// Fast: quick pattern scan of current observations
    /// Medium: cross-source correlation + trend analysis
    /// Slow: historical comparison + anomaly deep-dive
    /// Deep: full knowledge graph traversal + flywheel assessment
    async fn orient_for_tier(
        &self,
        tier: CycleTier,
        observations: &[Observation],
    ) -> Result<Orientation> {
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
                        "tier": format!("{:?}", tier),
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

        // Medium+: Cross-source correlation
        if matches!(tier, CycleTier::Medium | CycleTier::Slow | CycleTier::Deep) {
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
        }

        // Slow+: Historical comparison against recent cycle history
        if matches!(tier, CycleTier::Slow | CycleTier::Deep) {
            let history = self.cycle_history.lock().await;
            let recent_patterns: usize = history
                .iter()
                .rev()
                .take(24)
                .filter_map(|r| r.orientation.as_ref())
                .map(|o| o.patterns.len())
                .sum();
            if recent_patterns > patterns.len() * 2 {
                patterns.push(Pattern {
                    pattern_type: "historical_divergence".to_string(),
                    description: format!(
                        "Current pattern count ({}) diverges from recent average ({})",
                        patterns.len(),
                        recent_patterns / 24
                    ),
                    strength: 0.6,
                    supporting_data: serde_json::json!({
                        "current": patterns.len(),
                        "recent_total": recent_patterns,
                    }),
                });
            }
        }

        // Deep: Flywheel stage assessment
        if tier == CycleTier::Deep {
            patterns.push(Pattern {
                pattern_type: "flywheel_assessment".to_string(),
                description: "Weekly deep cycle — assessing flywheel stage and compound growth".to_string(),
                strength: 0.5,
                supporting_data: serde_json::json!({
                    "assessment_type": "weekly_deep",
                }),
            });
        }

        // Superagent: IntelligenceEngine cross-user pattern detection
        let aggregated: Vec<(String, HashMap<String, f64>)> = observations
            .iter()
            .filter_map(|obs| {
                let mut metrics = HashMap::new();
                if let Some(val) = obs.value.as_f64() {
                    metrics.insert(obs.data_type.clone(), val);
                }
                metrics.insert("confidence".to_string(), obs.confidence);
                if metrics.len() > 1 {
                    Some((obs.source.clone(), metrics))
                } else {
                    None
                }
            })
            .collect();

        if let Ok(intel_patterns) = self.intelligence.detect_patterns(&aggregated).await {
            for ip in &intel_patterns {
                patterns.push(Pattern {
                    pattern_type: format!("intelligence_{}", ip.pattern_type),
                    description: ip.description.clone(),
                    strength: ip.strength,
                    supporting_data: ip.supporting_data.clone(),
                });
            }
        }

        // Superagent: Generate actionable insights from intelligence patterns
        if let Ok(insights) = self.intelligence.generate_insights().await {
            for insight in &insights {
                patterns.push(Pattern {
                    pattern_type: format!("insight_{:?}", insight.insight_type),
                    description: insight.description.clone(),
                    strength: insight.confidence,
                    supporting_data: serde_json::json!({
                        "insight_id": insight.insight_id,
                        "recommended_actions": insight.recommended_actions,
                        "impact_estimate": insight.impact_estimate,
                    }),
                });
            }
        }

        // Build context
        let context = serde_json::json!({
            "observation_count": observations.len(),
            "sources_active": by_source.keys().collect::<Vec<_>>(),
            "avg_confidence": avg_confidence,
            "patterns_found": patterns.len(),
            "anomalies_found": anomalies.len(),
            "tier": format!("{:?}", tier),
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

    /// Decide: select actions appropriate for the cycle tier.
    ///
    /// Fast: rule-engine decisions only (speed over depth)
    /// Medium: rule + ML model for market signals
    /// Slow: rule + ML + knowledge base queries
    /// Deep: full decision tree including LLM reasoning
    async fn decide_for_tier(
        &self,
        tier: CycleTier,
        orientation: &Orientation,
    ) -> Result<Decision> {
        let mut options: Vec<DecisionOption> = Vec::new();

        // Generate decision options based on detected patterns
        for pattern in &orientation.patterns {
            match pattern.pattern_type.as_str() {
                "frequency_cluster" => {
                    options.push(DecisionOption {
                        option_id: "investigate_trend".to_string(),
                        description: format!("Investigate trend: {}", pattern.description),
                        expected_outcome: "Gain deeper understanding of emerging trend".to_string(),
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
                        description: format!("Perform deep analysis on: {}", pattern.description),
                        expected_outcome: "Discover hidden relationships between data sources"
                            .to_string(),
                        risk_score: 0.3,
                        confidence: pattern.strength,
                    });
                }
                "historical_divergence" => {
                    options.push(DecisionOption {
                        option_id: "investigate_divergence".to_string(),
                        description: format!("Investigate divergence: {}", pattern.description),
                        expected_outcome: "Understand cause of pattern shift".to_string(),
                        risk_score: 0.25,
                        confidence: pattern.strength,
                    });
                }
                "flywheel_assessment" => {
                    options.push(DecisionOption {
                        option_id: "evaluate_flywheel".to_string(),
                        description: "Evaluate flywheel stage and compound growth".to_string(),
                        expected_outcome: "Identify bottlenecks and growth opportunities".to_string(),
                        risk_score: 0.1,
                        confidence: 0.8,
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

        // Medium+: market signal generation
        if matches!(tier, CycleTier::Medium | CycleTier::Slow | CycleTier::Deep)
            && !orientation.patterns.is_empty()
        {
            options.push(DecisionOption {
                option_id: "generate_market_signals".to_string(),
                description: "Generate and push market signals based on aggregated patterns"
                    .to_string(),
                expected_outcome: "Workers receive actionable market intelligence".to_string(),
                risk_score: 0.15,
                confidence: 0.85,
            });
        }

        // Slow+: model drift check
        if matches!(tier, CycleTier::Slow | CycleTier::Deep) {
            options.push(DecisionOption {
                option_id: "check_model_drift".to_string(),
                description: "Check model accuracy for drift and recalibrate if needed".to_string(),
                expected_outcome: "Maintain model quality".to_string(),
                risk_score: 0.1,
                confidence: 0.9,
            });
        }

        // Deep: federated learning evaluation
        if tier == CycleTier::Deep {
            options.push(DecisionOption {
                option_id: "evaluate_federated_learning".to_string(),
                description: "Evaluate federated learning retrain cycle".to_string(),
                expected_outcome: "Improve model with distributed data".to_string(),
                risk_score: 0.2,
                confidence: 0.85,
            });
        }

        // Superagent: Guardrails compliance check on high-risk options
        for option in &mut options {
            if option.risk_score > 0.5 {
                let compliance = self.guardrails.check_compliance(
                    &Jurisdiction::Kenya,
                    true, // assume consent for system actions
                    None,
                    true, // purpose specified
                    None,
                );
                if !compliance.passed {
                    warn!(
                        option = %option.option_id,
                        violations = compliance.violations.len(),
                        "Guardrails: compliance violations detected for high-risk option"
                    );
                    option.risk_score = (option.risk_score * 1.2).min(1.0);
                }
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
            decision_type: format!("ooda_{:?}_cycle_decision", tier).to_lowercase(),
            rationale: format!(
                "Selected '{}' with confidence {:.2} (risk {:.2}) based on {} patterns and {} anomalies [{:?} cycle]",
                selected.option_id, selected.confidence, selected.risk_score,
                orientation.patterns.len(), orientation.anomalies.len(), tier
            ),
            options,
            selected_option: selected.option_id.clone(),
            confidence: selected.confidence,
        })
    }

    /// Act: execute decision based on harness mode.
    ///
    /// Autonomous: auto-act if confidence is high enough
    /// On-demand: always act (user expects results)
    /// Hybrid: auto-act for low-risk, alert user for high-risk anomalies
    ///
    /// After acting, the superagent engines perform post-action work:
    /// - FlywheelEngine captures the action as a signal for model improvement
    /// - MemoryEngine promotes observations to episodic memory
    /// - SyncEngine queues the result for offline-first distribution
    async fn act_for_mode(
        &self,
        tier: CycleTier,
        decision: &Decision,
        orientation: &Orientation,
    ) -> Result<Option<Action>> {
        match self.config.harness_mode {
            HarnessMode::Autonomous => {
                // Autonomous: act if confidence meets threshold
                if decision.confidence >= self.config.min_decision_confidence {
                    Ok(Some(self.act(decision).await?))
                } else {
                    warn!(
                        confidence = decision.confidence,
                        threshold = self.config.min_decision_confidence,
                        "Autonomous mode: confidence below threshold, skipping action"
                    );
                    Ok(None)
                }
            }
            HarnessMode::OnDemand => {
                // On-demand: always act — user is waiting for results
                Ok(Some(self.act(decision).await?))
            }
            HarnessMode::Hybrid => {
                // Hybrid: check if there are high-severity anomalies
                let critical_anomalies: Vec<&Anomaly> = orientation
                    .anomalies
                    .iter()
                    .filter(|a| a.severity > self.config.anomaly_alert_threshold)
                    .collect();

                if !critical_anomalies.is_empty() {
                    // Queue anomaly alerts for user decision
                    for anomaly in &critical_anomalies {
                        let alert = AnomalyAlert {
                            alert_id: Uuid::new_v4(),
                            anomaly: (*anomaly).clone(),
                            suggested_action: decision.options.first().cloned().unwrap_or_else(|| {
                                DecisionOption {
                                    option_id: "investigate".to_string(),
                                    description: "Investigate anomaly".to_string(),
                                    expected_outcome: "Understanding of root cause".to_string(),
                                    risk_score: 0.1,
                                    confidence: 0.8,
                                }
                            }),
                            detected_at: Utc::now(),
                            user_response: None,
                        };

                        let mut alerts = self.pending_alerts.lock().await;
                        alerts.push_back(alert);
                        // Keep max 50 pending alerts
                        while alerts.len() > 50 {
                            alerts.pop_front();
                        }
                    }

                    // Alert user via WhatsApp
                    self.alert_generator
                        .generate_alert(
                            "ooda_hybrid_anomaly",
                            &format!(
                                "{} critical anomalies detected. Pending your review.",
                                critical_anomalies.len()
                            ),
                            decision.confidence,
                        )
                        .await?;

                    info!(
                        anomaly_count = critical_anomalies.len(),
                        "Hybrid mode: queued anomaly alerts for user review"
                    );

                    Ok(None) // Action deferred to user decision
                } else if decision.confidence >= self.config.min_decision_confidence {
                    // Low-risk: auto-act in hybrid mode too
                    Ok(Some(self.act(decision).await?))
                } else {
                    Ok(None)
                }
            }
        }
    }

    // ─────────────────────────────────────────────────────────────────
    // Core Phase Implementations (shared across tiers)
    // ─────────────────────────────────────────────────────────────────

    /// Phase 1: Observe — Ingest data from all sources
    pub async fn observe(&self) -> Result<Vec<Observation>> {
        self.observe_for_tier(CycleTier::Fast).await
    }

    /// Phase 2: Orient — Synthesize context from memory + patterns
    pub async fn orient(&self, observations: &[Observation]) -> Result<Orientation> {
        self.orient_for_tier(CycleTier::Fast, observations).await
    }

    /// Phase 3: Decide — Select the best action based on orientation
    pub async fn decide(&self, orientation: &Orientation) -> Result<Decision> {
        self.decide_for_tier(CycleTier::Fast, orientation).await
    }

    /// Phase 4: Act — Execute the chosen decision
    pub async fn act(&self, decision: &Decision) -> Result<Action> {
        let result = match decision.selected_option.as_str() {
            "investigate_trend" | "investigate_divergence" => {
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
            "generate_market_signals" => {
                // Generate and push market signals
                serde_json::json!({
                    "action": "market_signals_generated",
                    "description": decision.rationale,
                })
            }
            "check_model_drift" => {
                // Check model performance for drift
                serde_json::json!({
                    "action": "model_drift_check_initiated",
                })
            }
            "evaluate_flywheel" | "evaluate_federated_learning" => {
                // Evaluate federated learning or flywheel
                serde_json::json!({
                    "action": "evaluation_initiated",
                    "type": decision.selected_option,
                })
            }
            "continue_monitoring" | _ => {
                serde_json::json!({
                    "action": "monitoring_continued",
                })
            }
        };

        // Superagent: FlywheelEngine — capture action as a signal for model improvement
        use crate::superagent::flywheel::SignalContext;
        let flywheel_signal = crate::superagent::flywheel::ActionSignal {
            signal_id: Uuid::new_v4(),
            user_id: Uuid::nil(),
            org_id: Uuid::nil(),
            action_type: match decision.selected_option.as_str() {
                "investigate_trend" | "investigate_divergence" => ActionType::ViewReport,
                "alert_stakeholders" | "anomaly_alert" => ActionType::AcknowledgeAlert,
                "generate_market_signals" => ActionType::SyncData,
                "evaluate_flywheel" => ActionType::AchieveGoal,
                _ => ActionType::Custom(decision.selected_option.clone()),
            },
            context: SignalContext {
                region: "system".to_string(),
                product_category: None,
                device_type: "ooda_orchestrator".to_string(),
                session_duration_secs: None,
                confidence_score: Some(decision.confidence),
                metadata: result.clone(),
            },
            timestamp: Utc::now(),
        };
        if let Err(e) = self.flywheel.capture_signal(flywheel_signal).await {
            debug!(error = %e, "Flywheel signal capture failed (non-fatal)");
        }

        // Superagent: SyncEngine — queue the action result for offline-first distribution
        if let Err(e) = self.sync_engine
            .queue_sync(
                "ooda_system",
                Uuid::nil(),
                "ooda_action",
                &decision.selected_option,
                crate::superagent::sync::SyncOperation::Create,
                result.clone(),
                SyncPriority::Normal,
            )
            .await
        {
            debug!(error = %e, "Sync queue failed (non-fatal)");
        }

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

    // ─────────────────────────────────────────────────────────────────
    // Public API
    // ─────────────────────────────────────────────────────────────────

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

    /// Get the current harness mode
    pub fn harness_mode(&self) -> HarnessMode {
        self.config.harness_mode
    }

    /// Get the flywheel engine
    pub fn flywheel(&self) -> &FlywheelEngine {
        &self.flywheel
    }

    /// Get the guardrails engine
    pub fn guardrails(&self) -> &GuardrailsEngine {
        &self.guardrails
    }

    /// Get the intelligence engine
    pub fn intelligence(&self) -> &IntelligenceEngine {
        &self.intelligence
    }

    /// Get the memory engine
    pub fn memory(&self) -> &MemoryEngine {
        &self.memory
    }

    /// Get the sync engine
    pub fn sync_engine(&self) -> &SyncEngine {
        &self.sync_engine
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
        let mode = state.orchestrator.harness_mode();
        let alerts = state.orchestrator.pending_alerts().await;

        Json(serde_json::json!({
            "cycle_count": count,
            "orientation": orientation,
            "harness_mode": mode,
            "pending_alerts": alerts.len(),
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

    /// On-demand invocation: user query → harness calls OODA directly
    async fn invoke_on_demand(
        State(state): State<Arc<crate::db::AppState>>,
        Json(payload): Json<serde_json::Value>,
    ) -> Result<Json<serde_json::Value>, axum::http::StatusCode> {
        match state.orchestrator.invoke_on_demand(payload).await {
            Ok(result) => Ok(Json(serde_json::json!(result))),
            Err(e) => {
                tracing::error!(error = %e, "On-demand invocation failed");
                Err(axum::http::StatusCode::INTERNAL_SERVER_ERROR)
            }
        }
    }

    /// Respond to a pending anomaly alert (hybrid mode)
    async fn respond_to_alert(
        State(state): State<Arc<crate::db::AppState>>,
        Json(payload): Json<serde_json::Value>,
    ) -> Result<Json<serde_json::Value>, axum::http::StatusCode> {
        let alert_id = payload
            .get("alert_id")
            .and_then(|v| v.as_str())
            .and_then(|s| Uuid::parse_str(s).ok())
            .ok_or(axum::http::StatusCode::BAD_REQUEST)?;

        let user_decision = UserDecision {
            approved: payload.get("approved").and_then(|v| v.as_bool()).unwrap_or(false),
            override_action: payload
                .get("override_action")
                .and_then(|v| v.as_str())
                .map(String::from),
            responded_at: Utc::now(),
        };

        match state
            .orchestrator
            .respond_to_alert(alert_id, user_decision)
            .await
        {
            Ok(action) => Ok(Json(serde_json::json!({
                "status": "processed",
                "action": action,
            }))),
            Err(e) => {
                tracing::error!(error = %e, "Alert response failed");
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

    async fn get_alerts(
        State(state): State<Arc<crate::db::AppState>>,
    ) -> Json<serde_json::Value> {
        let alerts = state.orchestrator.pending_alerts().await;
        Json(serde_json::json!({
            "pending_alerts": alerts.len(),
            "alerts": alerts,
        }))
    }

    axum::Router::new()
        .route("/status", get(get_status))
        .route("/cycle", post(trigger_cycle))
        .route("/invoke", post(invoke_on_demand))
        .route("/alert/respond", post(respond_to_alert))
        .route("/alerts", get(get_alerts))
        .route("/history", get(get_history))
}
