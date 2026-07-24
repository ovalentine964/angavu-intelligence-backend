//! Angavu Backend 20 Superagent Tools
//!
//! Each tool is a self-contained module with struct definitions, core business logic,
//! error handling (Result types), and integration with OODAOrchestrator.

pub mod ooda_orchestrator;
pub mod market_analyzer;
pub mod credit_scorer;
pub mod federated_aggregator;
pub mod sync_receiver;
pub mod report_engine;
pub mod audit_logger;
pub mod api_gateway;
pub mod distribution_analyzer;
pub mod fmcg_intelligence;
pub mod health_metrics;
pub mod economic_analyzer;
pub mod differential_privacy;
pub mod k_anonymity;
pub mod model_distributor;
pub mod whatsapp_sender;
pub mod alert_generator;
pub mod circuit_breaker;
pub mod rate_limiter;
pub mod secret_rotator;

// Re-export the orchestrator for the superagent module
pub use ooda_orchestrator::OODAOrchestrator;
