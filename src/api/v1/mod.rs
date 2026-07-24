pub mod auth;
pub mod users;
pub mod intelligence;
pub mod memory;
pub mod sync;
pub mod analytics;
pub mod endpoints;

use axum::{
    routing::{get, post, put, delete},
    Router,
};
use std::sync::Arc;
use crate::db::AppState;

pub fn router() -> Router<Arc<AppState>> {
    Router::new()
        // Auth routes
        .route("/auth/login", post(auth::login))
        .route("/auth/register", post(auth::register))
        .route("/auth/refresh", post(auth::refresh_token))
        .route("/auth/logout", post(auth::logout))
        
        // User routes
        .route("/users", get(users::list_users))
        .route("/users/{id}", get(users::get_user))
        .route("/users/{id}", put(users::update_user))
        .route("/users/{id}", delete(users::delete_user))
        
        // Intelligence routes
        .route("/intelligence/forecast", post(intelligence::create_forecast))
        .route("/intelligence/behavior", post(intelligence::analyze_behavior))
        .route("/intelligence/market", post(intelligence::market_analysis))
        .route("/intelligence/risk", post(intelligence::assess_risk))
        .route("/intelligence/pricing", post(intelligence::optimize_pricing))
        .route("/intelligence/churn", post(intelligence::predict_churn))
        .route("/intelligence/tasks", get(intelligence::list_tasks))
        .route("/intelligence/tasks/{id}", get(intelligence::get_task))
        .route("/intelligence/insights", get(intelligence::get_insights))
        .route("/intelligence/dashboard", get(intelligence::dashboard_metrics))
        
        // Memory routes
        .route("/memory/store", post(memory::store_memory))
        .route("/memory/search", post(memory::search_memory))
        .route("/memory/layers/{layer}", get(memory::get_by_layer))
        .route("/memory/consolidate", post(memory::consolidate_memory))
        .route("/memory/stats", get(memory::memory_stats))
        
        // Sync routes
        .route("/sync/push", post(sync::push_changes))
        .route("/sync/pull", post(sync::pull_changes))
        .route("/sync/status", get(sync::sync_status))
        .route("/sync/federated/submit", post(sync::submit_federated_update))
        .route("/sync/federated/status", get(sync::federated_status))
        
        // Analytics routes
        .route("/analytics/revenue", get(analytics::revenue_analytics))
        .route("/analytics/customers", get(analytics::customer_analytics))
        .route("/analytics/system", get(analytics::system_analytics))
        
        // ── Tool endpoints (all 20 tools accessible via API) ──────────
        .route("/tools", get(endpoints::tools::list_tools))
        // Analysis & Intelligence
        .route("/tools/health", get(endpoints::tools::health_metrics))
        .route("/tools/credit", post(endpoints::tools::credit_score))
        .route("/tools/market", get(endpoints::tools::market_analysis))
        .route("/tools/market/demand", get(endpoints::tools::market_demand))
        .route("/tools/economic", post(endpoints::tools::economic_indicators))
        .route("/tools/distribution", get(endpoints::tools::distribution_gaps))
        .route("/tools/fmcg", get(endpoints::tools::fmcg_report))
        // Privacy & Security
        .route("/tools/privacy/noise", post(endpoints::tools::add_noise))
        .route("/tools/anonymize", post(endpoints::tools::anonymize))
        .route("/tools/federated", get(endpoints::tools::federated_status))
        // Data & Sync
        .route("/tools/sync", get(endpoints::tools::sync_status))
        .route("/tools/model", get(endpoints::tools::model_status))
        // Reporting & Alerts
        .route("/tools/report", post(endpoints::tools::generate_report))
        .route("/tools/alert", post(endpoints::tools::generate_alert))
        .route("/tools/whatsapp", post(endpoints::tools::send_whatsapp))
        // Infrastructure
        .route("/tools/gateway", get(endpoints::tools::gateway_status))
        .route("/tools/audit", get(endpoints::tools::audit_status))
        .route("/tools/circuit-breaker", get(endpoints::tools::circuit_breaker_status))
        .route("/tools/rate-limiter", get(endpoints::tools::rate_limiter_status))
}
