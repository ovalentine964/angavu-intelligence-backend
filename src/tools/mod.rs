//! Angavu Backend 20 Superagent Tools
//!
//! Each tool is a self-contained module with struct definitions, core business logic,
//! error handling (Result types), and integration with OODAOrchestrator.

pub mod ooda_orchestrator;
pub mod market_analyzer;
pub mod credit_scorer;
pub mod federated_aggregator;
pub mod sync_receiver;
pub mod distribution_analyzer;
pub mod fmcg_intelligence;
pub mod health_metrics;
pub mod economic_analyzer;
pub mod differential_privacy;
pub mod k_anonymity;
pub mod model_distributor;
pub mod whatsapp_sender;
pub mod alert_generator;
pub mod report_engine;
pub mod api_gateway;
pub mod audit_logger;
pub mod circuit_breaker;
pub mod rate_limiter;
pub mod mobile_money_signal_extractor;
pub mod composite_index_builder;
pub mod anomaly_detector;
pub mod demand_forecaster;
pub mod scenario_modeler;

// Re-export key types for convenience
pub use ooda_orchestrator::OODAOrchestrator;
pub use market_analyzer::MarketAnalyzer;
pub use credit_scorer::CreditScorer;
pub use report_engine::ReportEngine;
pub use api_gateway::ApiGateway;
pub use alert_generator::AlertGenerator;
pub use audit_logger::AuditLogger;
pub use circuit_breaker::CircuitBreaker;
pub use rate_limiter::RateLimiter;
pub use federated_aggregator::FederatedAggregator;
pub use sync_receiver::SyncReceiver;
pub use distribution_analyzer::DistributionAnalyzer;
pub use fmcg_intelligence::FMCGIntelligence;
pub use health_metrics::HealthMetrics;
pub use economic_analyzer::EconomicAnalyzer;
pub use differential_privacy::DifferentialPrivacyEngine;
pub use k_anonymity::KAnonymityEnforcer;
pub use model_distributor::ModelDistributor;
pub use whatsapp_sender::WhatsAppSender;
pub use mobile_money_signal_extractor::MobileMoneySignalExtractor;
pub use composite_index_builder::CompositeIndexBuilder;
pub use anomaly_detector::AnomalyDetector;
pub use demand_forecaster::DemandForecaster;
pub use scenario_modeler::ScenarioModeler;
