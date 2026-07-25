pub mod postgres;
pub mod redis;
pub mod clickhouse;

use std::sync::Arc;
use anyhow::Context;
use crate::models::Config;
use crate::superagent::OODAOrchestrator;
use crate::superagent::{
    FlywheelEngine, GuardrailsEngine, IntelligenceEngine, MemoryEngine, SyncEngine,
};
use crate::tools::{
    MarketAnalyzer, CreditScorer, FederatedAggregator, SyncReceiver,
    DistributionAnalyzer, FMCGIntelligence, HealthMetrics, EconomicAnalyzer,
    DifferentialPrivacyEngine, KAnonymityEnforcer, ModelDistributor,
    WhatsAppSender, AlertGenerator, ReportEngine, ApiGateway, AuditLogger,
    CircuitBreaker, RateLimiter,
};
use crate::tools::differential_privacy::DifferentialPrivacyConfig;
use crate::tools::circuit_breaker::CircuitBreakerConfig;

/// Application state shared across handlers — holds all 20 tools + orchestrator.
pub struct AppState {
    pub db: DatabaseConnections,
    pub orchestrator: Arc<OODAOrchestrator>,
    pub config: Config,

    // ── Tool instances (20 total) ──────────────────────────────────────
    // Analysis & Intelligence
    pub market_analyzer: Arc<MarketAnalyzer>,
    pub credit_scorer: Arc<CreditScorer>,
    pub distribution_analyzer: Arc<DistributionAnalyzer>,
    pub fmcg_intelligence: Arc<FMCGIntelligence>,
    pub economic_analyzer: Arc<EconomicAnalyzer>,
    pub health_metrics: Arc<HealthMetrics>,

    // Privacy & Security
    pub differential_privacy: Arc<DifferentialPrivacyEngine>,
    pub k_anonymity: Arc<KAnonymityEnforcer>,
    pub federated_aggregator: Arc<FederatedAggregator>,

    // Data & Sync
    pub sync_receiver: Arc<SyncReceiver>,
    pub model_distributor: Arc<ModelDistributor>,

    // Reporting & Alerts
    pub report_engine: Arc<ReportEngine>,
    pub alert_generator: Arc<AlertGenerator>,
    pub whatsapp_sender: Arc<WhatsAppSender>,

    // Infrastructure
    pub api_gateway: Arc<ApiGateway>,
    pub audit_logger: Arc<AuditLogger>,
    pub circuit_breaker: Arc<CircuitBreaker>,
    pub rate_limiter: Arc<RateLimiter>,

    // Superagent engines (5 new capability modules)
    pub flywheel: Arc<FlywheelEngine>,
    pub guardrails: Arc<GuardrailsEngine>,
    pub intelligence: Arc<IntelligenceEngine>,
    pub memory: Arc<MemoryEngine>,
    pub sync_engine: Arc<SyncEngine>,
}

impl AppState {
    /// Construct AppState with all tools wired up.
    pub async fn new(db: DatabaseConnections, config: Config) -> anyhow::Result<Arc<Self>> {
        // Orchestrator (async init)
        let orchestrator = Arc::new(OODAOrchestrator::new(db.clone()).await?);

        // DB-backed tools
        let market_analyzer = Arc::new(MarketAnalyzer::new(db.clone()));
        let credit_scorer = Arc::new(CreditScorer::new(db.clone()));
        let distribution_analyzer = Arc::new(DistributionAnalyzer::new(db.clone()));
        let fmcg_intelligence = Arc::new(FMCGIntelligence::new(db.clone()));
        let federated_aggregator = Arc::new(FederatedAggregator::new(db.clone()));
        let sync_receiver = Arc::new(SyncReceiver::new(db.clone()));
        let alert_generator = Arc::new(AlertGenerator::new(db.clone()));
        let audit_logger = Arc::new(AuditLogger::new(db.clone()));

        // Standalone tools
        let economic_analyzer = Arc::new(EconomicAnalyzer::new());
        let health_metrics = Arc::new(HealthMetrics::new());
        let differential_privacy = Arc::new(DifferentialPrivacyEngine::new(
            DifferentialPrivacyConfig::default(),
        ));
        let k_anonymity = Arc::new(KAnonymityEnforcer::new(10));
        let model_distributor = Arc::new(ModelDistributor::new());
        let whatsapp_sender = Arc::new(WhatsAppSender::new());
        let report_engine = Arc::new(ReportEngine::new());
        let api_gateway = Arc::new(ApiGateway::new(1000));
        let circuit_breaker = Arc::new(CircuitBreaker::new(CircuitBreakerConfig::default()));
        let rate_limiter = Arc::new(RateLimiter::new());

        // Superagent engines
        let flywheel = Arc::new(FlywheelEngine::new());
        let guardrails = Arc::new(GuardrailsEngine::new());
        let intelligence = Arc::new(IntelligenceEngine::new());
        let memory = Arc::new(MemoryEngine::new());
        let sync_engine = Arc::new(SyncEngine::new());

        Ok(Arc::new(Self {
            db,
            orchestrator,
            config,
            market_analyzer,
            credit_scorer,
            distribution_analyzer,
            fmcg_intelligence,
            economic_analyzer,
            health_metrics,
            differential_privacy,
            k_anonymity,
            federated_aggregator,
            sync_receiver,
            model_distributor,
            report_engine,
            alert_generator,
            whatsapp_sender,
            api_gateway,
            audit_logger,
            circuit_breaker,
            rate_limiter,
            flywheel,
            guardrails,
            intelligence,
            memory,
            sync_engine,
        }))
    }
}

/// All database connections
#[derive(Clone)]
pub struct DatabaseConnections {
    pub postgres: sqlx::PgPool,
    pub redis: redis::aio::ConnectionManager,
    pub clickhouse: clickhouse::Client,
}

impl DatabaseConnections {
    pub async fn new(config: &Config) -> anyhow::Result<Self> {
        let postgres = postgres::create_pool(&config.database).await?;
        let redis = redis::create_connection(&config.redis).await?;
        let clickhouse = clickhouse::create_client(&config.clickhouse).await?;

        // Run ClickHouse schema migrations
        clickhouse::run_migrations(&clickhouse).await
            .context("Failed to run ClickHouse migrations")?;

        Ok(Self {
            postgres,
            redis,
            clickhouse,
        })
    }
}
