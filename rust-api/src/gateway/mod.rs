// src/gateway/mod.rs

pub mod audit;
pub mod auth;
pub mod data_retention;
pub mod error;
pub mod graph_sync;
pub mod human_approval;
pub mod k_anonymity;
pub mod rate_limit;
pub mod security_headers;
pub mod sync_verification;
pub mod tool_output_verification;
pub mod tools_impl;
pub mod webhook_integration; // P1: Data retention policies and right-to-erasure enforcement

use axum::{
    extract::{ConnectInfo, Request, State},
    http::StatusCode,
    middleware::Next,
    response::Response,
};
use std::net::SocketAddr;
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
    /// Privacy budget tracker (RDP composition, per-query-type)
    pub privacy_budget: Arc<crate::credit::privacy_budget::PrivacyBudgetTracker>,
    /// Differential privacy engine (shared, for endpoint-level noise)
    pub dp_engine: Arc<parking_lot::RwLock<crate::statistical::DifferentialPrivacyEngine>>,
    /// Audit logger
    pub audit: Arc<audit::AuditLogger>,
    /// Sync state for bidirectional sync
    pub sync_state: Arc<crate::sync::receiver::SyncState>,
    /// Database pool for implemented tool endpoints (D1)
    pub db: sqlx::PgPool,
    /// Redis connection for implemented tool endpoints (D1)
    pub redis: redis::aio::ConnectionManager,
}

// src/gateway/mod.rs (continued — full router assembly)

use axum::{
    middleware,
    response::IntoResponse,
    routing::{get, post},
    Json, Router,
};
use serde_json::json;

// ═══════════════════════════════════════════════════════════
//  STUB HANDLER MODULES — Unified ErrorResponse format
//  Each returns {"error": {"code": ..., "message": ...}}
// ═══════════════════════════════════════════════════════════

use error::ErrorResponse;

// Request types for privacy/anonymization APIs
#[derive(Debug, serde::Deserialize)]
pub struct PrivacyNoiseRequest {
    /// The true value to add noise to
    pub value: f64,
    /// "laplace" or "gaussian"
    pub mechanism: String,
    /// Query sensitivity (default: 1.0)
    pub sensitivity: Option<f64>,
}

#[derive(Debug, serde::Deserialize)]
pub struct AnonymizeRequest {
    /// Cohort key for k-anonymity check
    pub cohort_key: String,
    /// Number of individuals in the cohort
    pub cohort_size: u32,
    /// The aggregated value to anonymize
    pub aggregated_value: f64,
    /// Query sensitivity for DP noise (default: auto from value)
    pub sensitivity: Option<f64>,
}

/// Tool API handlers — stubs for endpoints not yet implemented.
/// These return 501 NOT_IMPLEMENTED with a clear "Coming Soon" message.
mod tools {
    use super::*;

    pub async fn credit_score() -> impl IntoResponse {
        ErrorResponse::not_implemented("Credit scoring API — Coming Soon")
    }

    pub async fn market_analysis() -> impl IntoResponse {
        ErrorResponse::not_implemented("Market analysis API — Coming Soon")
    }

    pub async fn demand_forecast() -> impl IntoResponse {
        ErrorResponse::not_implemented("Demand forecast API — Coming Soon")
    }

    pub async fn economic_indicators() -> impl IntoResponse {
        ErrorResponse::not_implemented("Economic indicators API — Coming Soon")
    }

    pub async fn distribution_gaps() -> impl IntoResponse {
        ErrorResponse::not_implemented("Distribution gap analysis API — Coming Soon")
    }

    pub async fn fmcg_report() -> impl IntoResponse {
        ErrorResponse::not_implemented("FMCG intelligence report API — Coming Soon")
    }

    pub async fn privacy_noise(
        State(state): State<GatewayState>,
        Json(req): Json<PrivacyNoiseRequest>,
    ) -> impl IntoResponse {
        // P1: Working privacy noise API (was 501 stub)
        let mut dp = state.dp_engine.write();
        let result = match req.mechanism.as_str() {
            "laplace" => {
                let sensitivity = req.sensitivity.unwrap_or(1.0);
                dp.laplace_mechanism_f64(req.value, sensitivity)
            }
            "gaussian" => {
                let sensitivity = req.sensitivity.unwrap_or(1.0);
                dp.gaussian_mechanism_f64(req.value, sensitivity)
            }
            _ => {
                return ErrorResponse::bad_request("mechanism must be 'laplace' or 'gaussian'")
                    .into_response();
            }
        };

        Json(serde_json::json!({
            "noisy_value": result.noisy_value,
            "epsilon_used": result.epsilon_used,
            "budget_remaining": result.budget_remaining,
            "suppressed": result.suppressed,
            "mechanism": req.mechanism,
        }))
        .into_response()
    }

    pub async fn anonymize(
        State(state): State<GatewayState>,
        Json(req): Json<AnonymizeRequest>,
    ) -> impl IntoResponse {
        // P1: Working anonymization API (was 501 stub)
        // Apply k-anonymity check
        let k_result = state.k_anonymity.enforce_with_audit(
            &req.cohort_key,
            (),
            req.cohort_size,
            "POST /api/v1/tools/anonymization",
        );

        if k_result.suppressed {
            return ErrorResponse::k_anonymity_violation(
                req.cohort_size as usize,
                state.k_anonymity.k_threshold(),
            )
            .into_response();
        }

        // Apply DP noise to the aggregated value
        let mut dp = state.dp_engine.write();
        let dp_result = dp.gaussian_mean(
            req.aggregated_value,
            req.sensitivity.unwrap_or(req.aggregated_value.abs()),
            req.cohort_size.max(1) as u64,
        );

        Json(serde_json::json!({
            "anonymized_value": dp_result.noisy_value,
            "k_anonymity": {
                "k": state.k_anonymity.k_threshold(),
                "cohort_size": req.cohort_size,
                "suppressed": false,
            },
            "differential_privacy": {
                "epsilon_used": dp_result.epsilon_used,
                "budget_remaining": dp_result.budget_remaining,
            },
        }))
        .into_response()
    }

    pub async fn federated_status() -> impl IntoResponse {
        ErrorResponse::not_implemented("Federated learning status API — Coming Soon")
    }

    pub async fn generate_report() -> impl IntoResponse {
        ErrorResponse::not_implemented("Report generation API — Coming Soon")
    }
}

/// Superagent API handlers — OODA orchestrator control plane.
/// These return 501 NOT_IMPLEMENTED with a clear "Coming Soon" message.
mod superagent {
    use super::*;

    pub async fn status() -> impl IntoResponse {
        ErrorResponse::not_implemented("Superagent status API — Coming Soon")
    }

    pub async fn trigger_cycle() -> impl IntoResponse {
        ErrorResponse::not_implemented("OODA cycle trigger — Coming Soon")
    }

    pub async fn invoke() -> impl IntoResponse {
        ErrorResponse::not_implemented("Superagent invocation API — Coming Soon")
    }
}

/// Billing API handlers — fully implemented.
/// Uses the billing module for real subscription, usage, payment, and invoice management.
mod billing {
    use super::auth::Claims;
    use super::*;
    use crate::billing::{invoice, metering, mpesa, subscription};
    use axum::extract::Path;

    pub async fn create_subscription(
        State(state): State<GatewayState>,
        claims: Claims,
        Json(req): Json<subscription::CreateSubscriptionRequest>,
    ) -> impl IntoResponse {
        match subscription::create_subscription(&state.db, &state.redis, &claims.org_id, req).await
        {
            Ok(sub) => (
                StatusCode::CREATED,
                Json(serde_json::to_value(sub).unwrap()),
            )
                .into_response(),
            Err(e) => {
                tracing::error!(error = %e, org_id = %claims.org_id, "Failed to create subscription");
                ErrorResponse::internal().into_response()
            }
        }
    }

    pub async fn create_api_key() -> impl IntoResponse {
        ErrorResponse::not_implemented("API key management — Coming Soon")
    }
}

/// Billing handler implementations using the billing module.
mod billing_handlers {
    use super::auth::Claims;
    use super::*;
    use crate::billing::{invoice, metering, mpesa, subscription};
    use axum::extract::Path;

    pub async fn get_subscription(
        State(state): State<GatewayState>,
        claims: Claims,
    ) -> impl IntoResponse {
        match subscription::get_active_subscription(&state.db, &claims.org_id).await {
            Ok(Some(sub)) => Json(serde_json::to_value(sub).unwrap()).into_response(),
            Ok(None) => ErrorResponse::not_found("Subscription").into_response(),
            Err(e) => {
                tracing::error!(error = %e, org_id = %claims.org_id, "Failed to get subscription");
                ErrorResponse::internal().into_response()
            }
        }
    }

    pub async fn cancel_subscription(
        State(state): State<GatewayState>,
        claims: Claims,
    ) -> impl IntoResponse {
        match subscription::cancel_subscription(&state.db, &claims.org_id).await {
            Ok(sub) => Json(serde_json::to_value(sub).unwrap()).into_response(),
            Err(e) => {
                tracing::error!(error = %e, org_id = %claims.org_id, "Failed to cancel subscription");
                ErrorResponse::internal().into_response()
            }
        }
    }

    pub async fn get_usage(State(state): State<GatewayState>, claims: Claims) -> impl IntoResponse {
        match metering::get_usage_summary(&state.redis, &state.db, &claims.org_id, &claims.tier)
            .await
        {
            Ok(usage) => Json(serde_json::to_value(usage).unwrap()).into_response(),
            Err(e) => {
                tracing::error!(error = %e, org_id = %claims.org_id, "Failed to get usage");
                ErrorResponse::internal().into_response()
            }
        }
    }

    pub async fn initiate_payment(
        State(state): State<GatewayState>,
        claims: Claims,
        Json(req): Json<mpesa::StkPushRequest>,
    ) -> impl IntoResponse {
        let mpesa_config = crate::webhook::MpesaConfig {
            passkey: std::env::var("MPESA_PASSKEY").unwrap_or_default(),
            shortcode: std::env::var("MPESA_SHORTCODE").unwrap_or_else(|_| "174379".to_string()),
            initiator_password: std::env::var("MPESA_INITIATOR_PASSWORD").unwrap_or_default(),
            environment: match std::env::var("MPESA_ENVIRONMENT").as_deref() {
                Ok("production") => crate::webhook::MpesaEnvironment::Production,
                _ => crate::webhook::MpesaEnvironment::Sandbox,
            },
        };

        match mpesa::initiate_stk_push(&state.db, &state.redis, &mpesa_config, &claims.org_id, req)
            .await
        {
            Ok(resp) => (
                StatusCode::ACCEPTED,
                Json(serde_json::to_value(resp).unwrap()),
            )
                .into_response(),
            Err(e) => {
                tracing::error!(error = %e, org_id = %claims.org_id, "Failed to initiate payment");
                ErrorResponse::internal().into_response()
            }
        }
    }

    pub async fn list_invoices(
        State(state): State<GatewayState>,
        claims: Claims,
        axum::extract::Query(params): axum::extract::Query<invoice::InvoiceListParams>,
    ) -> impl IntoResponse {
        match invoice::list_invoices(&state.db, &claims.org_id, params).await {
            Ok(invoices) => Json(serde_json::json!({ "invoices": invoices })).into_response(),
            Err(e) => {
                tracing::error!(error = %e, org_id = %claims.org_id, "Failed to list invoices");
                ErrorResponse::internal().into_response()
            }
        }
    }

    pub async fn get_invoice(
        State(state): State<GatewayState>,
        claims: Claims,
        Path(invoice_id): Path<String>,
    ) -> impl IntoResponse {
        match invoice::get_invoice(&state.db, &claims.org_id, &invoice_id).await {
            Ok(Some(inv)) => Json(serde_json::to_value(inv).unwrap()).into_response(),
            Ok(None) => ErrorResponse::not_found("Invoice").into_response(),
            Err(e) => {
                tracing::error!(error = %e, invoice_id = %invoice_id, "Failed to get invoice");
                ErrorResponse::internal().into_response()
            }
        }
    }

    pub async fn reactivate_subscription(
        State(state): State<GatewayState>,
        claims: Claims,
    ) -> impl IntoResponse {
        match subscription::reactivate_subscription(&state.db, &claims.org_id).await {
            Ok(sub) => Json(serde_json::to_value(sub).unwrap()).into_response(),
            Err(e) => {
                tracing::error!(error = %e, org_id = %claims.org_id, "Failed to reactivate subscription");
                ErrorResponse::internal().into_response()
            }
        }
    }

    pub async fn check_payment_status(
        State(state): State<GatewayState>,
        claims: Claims,
        Path(txn_id): Path<String>,
    ) -> impl IntoResponse {
        match mpesa::get_payment_status(&state.db, &claims.org_id, &txn_id).await {
            Ok(Some(status)) => Json(serde_json::to_value(status).unwrap()).into_response(),
            Ok(None) => ErrorResponse::not_found("Payment").into_response(),
            Err(e) => {
                tracing::error!(error = %e, txn_id = %txn_id, "Failed to check payment status");
                ErrorResponse::internal().into_response()
            }
        }
    }

    pub async fn download_invoice_pdf(
        State(state): State<GatewayState>,
        claims: Claims,
        Path(invoice_id): Path<String>,
    ) -> impl IntoResponse {
        match invoice::generate_invoice_pdf(&state.db, &claims.org_id, &invoice_id).await {
            Ok(pdf_bytes) => {
                let headers = [
                    (
                        axum::http::header::CONTENT_TYPE,
                        "application/pdf".to_string(),
                    ),
                    (
                        axum::http::header::CONTENT_DISPOSITION,
                        format!("attachment; filename=\"invoice-{}.pdf\"", invoice_id),
                    ),
                ];
                (StatusCode::OK, headers, pdf_bytes).into_response()
            }
            Err(e) => {
                tracing::error!(error = %e, invoice_id = %invoice_id, "Failed to generate invoice PDF");
                ErrorResponse::internal().into_response()
            }
        }
    }
}

/// Build the full API gateway router with all middleware.
/// S6: Accepts additional routers that should also be protected by JWT auth.
pub fn build_gateway_router(
    state: GatewayState,
    additional_protected_routers: Vec<Router>,
) -> Router {
    // P2: Hardened CORS — explicit ALLOWED_ORIGINS with no localhost fallback in production
    let cors = tower_http::cors::CorsLayer::new()
        .allow_origin(tower_http::cors::AllowOrigin::predicate(
            |origin: &axum::http::HeaderValue, _request_parts: &axum::http::request::Parts| {
                // Allow requests with no origin (mobile apps, curl, server-to-server)
                if origin.is_empty() {
                    return true;
                }
                // Check against ALLOWED_ORIGINS env var (required in production)
                if let Ok(allowed) = std::env::var("ALLOWED_ORIGINS") {
                    if let Ok(origin_str) = origin.to_str() {
                        return allowed.split(',').any(|o| o.trim() == origin_str);
                    }
                    // If ALLOWED_ORIGINS is set but origin can't be parsed, reject
                    return false;
                }
                // Fallback: allow localhost only in development (ANGAVU_ENV != production)
                let is_production = std::env::var("ANGAVU_ENV")
                    .map(|v| v == "production")
                    .unwrap_or(false);
                if !is_production {
                    if let Ok(origin_str) = origin.to_str() {
                        return origin_str.starts_with("http://localhost")
                            || origin_str.starts_with("https://localhost");
                    }
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

    // Vary: Origin header for proper CDN/proxy caching of CORS responses
    let vary_header = tower_http::set_header::SetResponseHeaderLayer::overriding(
        axum::http::header::VARY,
        axum::http::HeaderValue::from_static("origin"),
    );

    // Public routes (no auth required) — health check moved to telemetry module
    let public_routes = Router::new().route("/api/v1/tools", get(list_tools));

    // Protected routes (auth + rate limit + audit required)
    let mut protected_routes = Router::new()
        // Tools endpoints — D1: top 5 critical endpoints implemented
        .route(
            "/api/v1/tools/credit-scores",
            post(tools_impl::compute_credit_score),
        )
        .route(
            "/api/v1/tools/market-analyses",
            get(tools_impl::get_market_analysis),
        )
        .route(
            "/api/v1/tools/demand-forecasts",
            get(tools_impl::get_demand_forecast),
        )
        .route(
            "/api/v1/tools/economic-indicators",
            post(tools::economic_indicators),
        )
        .route(
            "/api/v1/tools/distribution-gaps",
            get(tools::distribution_gaps),
        )
        .route("/api/v1/tools/fmcg-reports", get(tools::fmcg_report))
        .route("/api/v1/tools/privacy/noise", post(tools::privacy_noise))
        .route("/api/v1/tools/anonymization", post(tools::anonymize))
        .route(
            "/api/v1/tools/federated-learning/status",
            get(tools_impl::get_federated_status),
        )
        .route(
            "/api/v1/tools/credit/:score_id/explain",
            get(tools_impl::explain_credit_score),
        )
        .route("/api/v1/tools/reports", post(tools::generate_report))
        // Superagent endpoints
        .route("/api/v1/superagent/status", get(superagent::status))
        .route("/api/v1/superagent/cycles", post(superagent::trigger_cycle))
        .route("/api/v1/superagent/invocations", post(superagent::invoke))
        // Sync endpoints
        .route(
            "/api/v1/sync/anonymized",
            post(crate::sync::receiver::handle_sync),
        )
        .route("/api/v1/sync/graph", post(graph_sync::handle_graph_sync))
        // Billing endpoints — fully implemented
        .route("/api/v1/billing/tiers", get(tools_impl::list_billing_tiers))
        .route(
            "/api/v1/billing/subscriptions",
            post(billing::create_subscription),
        )
        .route(
            "/api/v1/billing/subscriptions/me",
            get(billing_handlers::get_subscription),
        )
        .route(
            "/api/v1/billing/subscriptions/cancel",
            post(billing_handlers::cancel_subscription),
        )
        .route("/api/v1/billing/usage", get(billing_handlers::get_usage))
        .route(
            "/api/v1/billing/payments/initiate",
            post(billing_handlers::initiate_payment),
        )
        .route(
            "/api/v1/billing/invoices",
            get(billing_handlers::list_invoices),
        )
        .route(
            "/api/v1/billing/invoices/:invoice_id",
            get(billing_handlers::get_invoice),
        )
        .route(
            "/api/v1/billing/invoices/:invoice_id/pdf",
            get(billing_handlers::download_invoice_pdf),
        )
        .route(
            "/api/v1/billing/subscriptions/reactivate",
            post(billing_handlers::reactivate_subscription),
        )
        .route(
            "/api/v1/billing/payments/:txn_id/status",
            get(billing_handlers::check_payment_status),
        )
        .route("/api/v1/billing/api-keys", post(billing::create_api_key));

    // S6: Merge additional protected routers (approval, GraphQL) inside auth layer
    for router in additional_protected_routers {
        protected_routes = protected_routes.merge(router);
    }

    // Apply middleware stack to all protected routes
    // Order: correlation_id → request_trace → auth → usage_metering → rate_limit → audit
    protected_routes = protected_routes
        .layer(middleware::from_fn(
            crate::telemetry::correlation::correlation_middleware,
        ))
        .layer(middleware::from_fn(
            crate::telemetry::request_trace::request_trace_middleware,
        ))
        .layer(middleware::from_fn_with_state(
            state.clone(),
            auth::jwt_auth_middleware,
        ))
        .layer(middleware::from_fn_with_state(
            state.clone(),
            crate::billing::metering::usage_metering_middleware,
        ))
        .layer(middleware::from_fn_with_state(
            state.clone(),
            rate_limit::rate_limit_middleware,
        ))
        .layer(middleware::from_fn_with_state(
            state.clone(),
            audit::audit_middleware,
        ));

    // ── Global middleware layers (applied to ALL routes) ──

    // Request body size limit: 10 MB max
    let body_limit = tower_http::limit::RequestBodyLimitLayer::new(10 * 1024 * 1024);

    // Per-request timeout: 30 seconds
    let timeout = tower_http::timeout::TimeoutLayer::new(std::time::Duration::from_secs(30));

    // Response compression: gzip/brotli (P2 — reduces bandwidth for API responses)
    let compression = tower_http::compression::CompressionLayer::new()
        .gzip(true)
        .br(true)
        .deflate(true);

    // Token issuance and refresh are public (no auth required)
    let auth_public = Router::new()
        .route("/api/v1/auth/token", post(auth::issue_token))
        .route("/api/v1/auth/refresh", post(auth::refresh_token));

    // Logout requires authentication (to identify which token to revoke)
    let auth_protected = Router::new().route("/api/v1/auth/logout", post(auth::logout));

    // Merge logout into protected routes so it benefits from JWT middleware
    protected_routes = protected_routes.merge(auth_protected);

    Router::new()
        .merge(public_routes)
        .merge(auth_public)
        .merge(protected_routes)
        .layer(cors)
        .layer(vary_header)
        .layer(middleware::from_fn(
            security_headers::security_headers_middleware,
        ))
        .layer(compression)
        .layer(body_limit)
        .layer(timeout)
        .with_state(state)
}

// Health check is now in telemetry::health module with DB/Redis/ClickHouse checks

async fn list_tools() -> &'static str {
    r#"{"tools": ["market_analyzer", "credit_scorer", "distribution_analyzer", "fmcg_intelligence", "health_metrics", "economic_analyzer"]}"#
}
