// src/gateway/mod.rs

pub mod auth;
pub mod rate_limit;
pub mod k_anonymity;
pub mod audit;
pub mod tool_output_verification;
pub mod sync_verification;

use axum::{
    extract::{Request, State},
    http::StatusCode,
    middleware::Next,
    response::Response,
};
use std::sync::Arc;

/// Shared gateway state accessible by all middleware
#[derive(Clone)]
pub struct GatewayState {
    /// JWT validation keys
    pub jwt_config: Arc<auth::JwtConfig>,
    /// Rate limiter state
    pub rate_limiter: Arc<rate_limit::RateLimiter>,
    /// k-Anonymity enforcer
    pub k_anonymity: Arc<k_anonymity::KAnonymityEnforcer>,
    /// Audit logger
    pub audit: Arc<audit::AuditLogger>,
    /// Sync state for bidirectional sync
    pub sync_state: Arc<crate::sync::receiver::SyncState>,
}

// src/gateway/mod.rs (continued — full router assembly)

use axum::{
    Router,
    middleware,
    routing::{get, post},
};

/// Build the full API gateway router with all middleware
pub fn build_gateway_router(state: GatewayState) -> Router {
    // Public routes (no auth required)
    let public_routes = Router::new()
        .route("/health", get(health_check))
        .route("/api/v1/tools", get(list_tools));

    // Protected routes (auth + rate limit + audit required)
    let protected_routes = Router::new()
        // Tools endpoints
        .route("/api/v1/tools/credit", post(tools::credit_score))
        .route("/api/v1/tools/market", get(tools::market_analysis))
        .route("/api/v1/tools/market/demand", get(tools::demand_forecast))
        .route("/api/v1/tools/economic", post(tools::economic_indicators))
        .route("/api/v1/tools/distribution", get(tools::distribution_gaps))
        .route("/api/v1/tools/fmcg", get(tools::fmcg_report))
        .route("/api/v1/tools/privacy/noise", post(tools::privacy_noise))
        .route("/api/v1/tools/anonymize", post(tools::anonymize))
        .route("/api/v1/tools/federated", get(tools::federated_status))
        .route("/api/v1/tools/report", post(tools::generate_report))
        // Superagent endpoints
        .route("/superagent/status", get(superagent::status))
        .route("/superagent/cycle", post(superagent::trigger_cycle))
        .route("/superagent/invoke", post(superagent::invoke))
        // Sync endpoint (bidirectional — push + pull)
        .route("/api/v1/sync/anonymized", post(sync::receiver::handle_sync))
        // Billing endpoints
        .route("/api/v1/billing/tiers", get(billing::list_tiers))
        .route("/api/v1/billing/subscriptions", post(billing::create_subscription))
        .route("/api/v1/billing/api-keys", post(billing::create_api_key))
        // Apply middleware stack (order matters — outermost runs first)
        .layer(middleware::from_fn_with_state(
            state.clone(),
            auth::jwt_auth_middleware,
        ))
        .layer(middleware::from_fn_with_state(
            state.clone(),
            rate_limit::rate_limit_middleware,
        ))
        .layer(middleware::from_fn_with_state(
            state.clone(),
            audit::audit_middleware,
        ));

    Router::new()
        .merge(public_routes)
        .merge(protected_routes)
        .with_state(state)
}

async fn health_check() -> &'static str {
    "OK"
}

async fn list_tools() -> &'static str {
    r#"{"tools": ["market_analyzer", "credit_scorer", "distribution_analyzer", "fmcg_intelligence", "health_metrics", "economic_analyzer"]}"#
}
