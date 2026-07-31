// src/gateway/mod.rs

pub mod auth;
pub mod rate_limit;
pub mod k_anonymity;
pub mod audit;
pub mod tool_output_verification;
pub mod sync_verification;
pub mod webhook_integration;
pub mod human_approval;
pub mod error;
pub mod tools_impl;

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
    response::IntoResponse,
    routing::{get, post},
    Json,
};
use serde_json::json;

// ═══════════════════════════════════════════════════════════
//  STUB HANDLER MODULES — Unified ErrorResponse format
//  Each returns {"error": {"code": ..., "message": ...}}
// ═══════════════════════════════════════════════════════════

use error::ErrorResponse;

/// Tool API handlers — credit scoring, market analysis, etc.
mod tools {
    use super::*;

    pub async fn credit_score(Json(_payload): Json<serde_json::Value>) -> impl IntoResponse {
        ErrorResponse::not_implemented("Credit scoring API")
    }

    pub async fn market_analysis() -> impl IntoResponse {
        ErrorResponse::not_implemented("Market analysis API")
    }

    pub async fn demand_forecast() -> impl IntoResponse {
        ErrorResponse::not_implemented("Demand forecast API")
    }

    pub async fn economic_indicators(Json(_payload): Json<serde_json::Value>) -> impl IntoResponse {
        ErrorResponse::not_implemented("Economic indicators API")
    }

    pub async fn distribution_gaps() -> impl IntoResponse {
        ErrorResponse::not_implemented("Distribution gap analysis API")
    }

    pub async fn fmcg_report() -> impl IntoResponse {
        ErrorResponse::not_implemented("FMCG intelligence report API")
    }

    pub async fn privacy_noise(Json(_payload): Json<serde_json::Value>) -> impl IntoResponse {
        ErrorResponse::not_implemented("Privacy noise injection API")
    }

    pub async fn anonymize(Json(_payload): Json<serde_json::Value>) -> impl IntoResponse {
        ErrorResponse::not_implemented("Data anonymization API")
    }

    pub async fn federated_status() -> impl IntoResponse {
        ErrorResponse::not_implemented("Federated learning status API")
    }

    pub async fn generate_report(Json(_payload): Json<serde_json::Value>) -> impl IntoResponse {
        ErrorResponse::not_implemented("Report generation API")
    }
}

/// Superagent API handlers — OODA orchestrator control plane
mod superagent {
    use super::*;

    pub async fn status() -> impl IntoResponse {
        ErrorResponse::not_implemented("Superagent status API")
    }

    pub async fn trigger_cycle(Json(_payload): Json<serde_json::Value>) -> impl IntoResponse {
        ErrorResponse::not_implemented("OODA cycle trigger")
    }

    pub async fn invoke(Json(_payload): Json<serde_json::Value>) -> impl IntoResponse {
        ErrorResponse::not_implemented("Superagent invocation API")
    }
}

/// Billing API handlers — subscription tiers, API keys
mod billing {
    use super::*;

    pub async fn list_tiers() -> impl IntoResponse {
        ErrorResponse::not_implemented("Billing tier listing")
    }

    pub async fn create_subscription(Json(_payload): Json<serde_json::Value>) -> impl IntoResponse {
        ErrorResponse::not_implemented("Subscription creation")
    }

    pub async fn create_api_key(Json(_payload): Json<serde_json::Value>) -> impl IntoResponse {
        ErrorResponse::not_implemented("API key management")
    }
}

/// Build the full API gateway router with all middleware.
/// S6: Accepts additional routers that should also be protected by JWT auth.
pub fn build_gateway_router(state: GatewayState, additional_protected_routers: Vec<Router>) -> Router {
    // S14: CORS configuration — allow same-origin + configured origins
    let cors = tower_http::cors::CorsLayer::new()
        .allow_origin(tower_http::cors::AllowOrigin::predicate(
            |origin: &axum::http::HeaderValue, _request_parts: &axum::http::request::Parts| {
                // Allow requests with no origin (mobile apps, curl, server-to-server)
                if origin.is_empty() {
                    return true;
                }
                // In production, check against ALLOWED_ORIGINS env var
                if let Ok(allowed) = std::env::var("ALLOWED_ORIGINS") {
                    if let Ok(origin_str) = origin.to_str() {
                        return allowed.split(',').any(|o| o.trim() == origin_str);
                    }
                }
                // Default: allow localhost for development
                if let Ok(origin_str) = origin.to_str() {
                    return origin_str.starts_with("http://localhost")
                        || origin_str.starts_with("https://localhost");
                }
                false
            },
        ))
        .allow_methods([
            axum::http::Method::GET,
            axum::http::Method::POST,
            axum::http::Method::PUT,
            axum::http::Method::DELETE,
            axum::http::Method::OPTIONS,
        ])
        .allow_headers([
            axum::http::header::AUTHORIZATION,
            axum::http::header::CONTENT_TYPE,
            axum::http::header::HeaderName::from_static("x-webhook-key"),
            axum::http::header::HeaderName::from_static("x-request-id"),
        ])
        .expose_headers([
            axum::http::header::HeaderName::from_static("x-ratelimit-remaining"),
            axum::http::header::HeaderName::from_static("retry-after"),
        ])
        .max_age(std::time::Duration::from_secs(3600));

    // Public routes (no auth required)
    let public_routes = Router::new()
        .route("/health", get(health_check))
        .route("/api/v1/tools", get(list_tools));

    // Protected routes (auth + rate limit + audit required)
    let mut protected_routes = Router::new()
        // Tools endpoints — D1: top 5 critical endpoints implemented
        .route("/api/v1/tools/credit-scores", post(tools_impl::compute_credit_score))
        .route("/api/v1/tools/market-analyses", get(tools_impl::get_market_analysis))
        .route("/api/v1/tools/demand-forecasts", get(tools_impl::get_demand_forecast))
        .route("/api/v1/tools/economic-indicators", post(tools::economic_indicators))
        .route("/api/v1/tools/distribution-gaps", get(tools::distribution_gaps))
        .route("/api/v1/tools/fmcg-reports", get(tools::fmcg_report))
        .route("/api/v1/tools/privacy/noise", post(tools::privacy_noise))
        .route("/api/v1/tools/anonymization", post(tools::anonymize))
        .route("/api/v1/tools/federated-learning/status", get(tools_impl::get_federated_status))
        .route("/api/v1/tools/reports", post(tools::generate_report))
        // Superagent endpoints
        .route("/api/v1/superagent/status", get(superagent::status))
        .route("/api/v1/superagent/cycles", post(superagent::trigger_cycle))
        .route("/api/v1/superagent/invocations", post(superagent::invoke))
        // Sync endpoint
        .route("/api/v1/sync/anonymized", post(sync::receiver::handle_sync))
        // Billing endpoints — D1: tiers listing implemented
        .route("/api/v1/billing/tiers", get(tools_impl::list_billing_tiers))
        .route("/api/v1/billing/subscriptions", post(billing::create_subscription))
        .route("/api/v1/billing/api-keys", post(billing::create_api_key));

    // S6: Merge additional protected routers (approval, GraphQL) inside auth layer
    for router in additional_protected_routers {
        protected_routes = protected_routes.merge(router);
    }

    // Apply middleware stack to all protected routes
    protected_routes = protected_routes
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
        .layer(cors)
        .with_state(state)
}

async fn health_check() -> &'static str {
    "OK"
}

async fn list_tools() -> &'static str {
    r#"{"tools": ["market_analyzer", "credit_scorer", "distribution_analyzer", "fmcg_intelligence", "health_metrics", "economic_analyzer"]}"#
}
