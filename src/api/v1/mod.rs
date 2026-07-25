// pub mod auth;         // TODO: not yet implemented
// pub mod users;         // TODO: not yet implemented
// pub mod intelligence;  // TODO: not yet implemented
// pub mod memory;        // TODO: not yet implemented
// pub mod sync;          // TODO: not yet implemented
// pub mod analytics;     // TODO: not yet implemented
pub mod endpoints;

use axum::{
    routing::{get, post, put, delete},
    Router,
};
use std::sync::Arc;
use crate::db::AppState;

pub fn router() -> Router<Arc<AppState>> {
    Router::new()
        // Auth routes — TODO: uncomment when auth module is implemented
        // .route("/auth/login", post(auth::login))
        // .route("/auth/register", post(auth::register))
        // .route("/auth/refresh", post(auth::refresh_token))
        // .route("/auth/logout", post(auth::logout))
        
        // User routes — TODO: uncomment when users module is implemented
        // .route("/users", get(users::list_users))
        // .route("/users/{id}", get(users::get_user))
        // .route("/users/{id}", put(users::update_user))
        // .route("/users/{id}", delete(users::delete_user))
        
        // Intelligence routes — TODO: uncomment when intelligence module is implemented
        // .route("/intelligence/forecast", post(intelligence::create_forecast))
        // .route("/intelligence/behavior", post(intelligence::analyze_behavior))
        // .route("/intelligence/market", post(intelligence::market_analysis))
        // .route("/intelligence/risk", post(intelligence::assess_risk))
        // .route("/intelligence/pricing", post(intelligence::optimize_pricing))
        // .route("/intelligence/churn", post(intelligence::predict_churn))
        // .route("/intelligence/tasks", get(intelligence::list_tasks))
        // .route("/intelligence/tasks/{id}", get(intelligence::get_task))
        // .route("/intelligence/insights", get(intelligence::get_insights))
        // .route("/intelligence/dashboard", get(intelligence::dashboard_metrics))
        
        // Memory routes — TODO: uncomment when memory module is implemented
        // .route("/memory/store", post(memory::store_memory))
        // .route("/memory/search", post(memory::search_memory))
        // .route("/memory/layers/{layer}", get(memory::get_by_layer))
        // .route("/memory/consolidate", post(memory::consolidate_memory))
        // .route("/memory/stats", get(memory::memory_stats))
        
        // Sync routes — TODO: uncomment when sync module is implemented
        // .route("/sync/push", post(sync::push_changes))
        // .route("/sync/pull", post(sync::pull_changes))
        // .route("/sync/status", get(sync::sync_status))
        // .route("/sync/federated/submit", post(sync::submit_federated_update))
        // .route("/sync/federated/status", get(sync::federated_status))
        
        // Analytics routes — TODO: uncomment when analytics module is implemented
        // .route("/analytics/revenue", get(analytics::revenue_analytics))
        // .route("/analytics/customers", get(analytics::customer_analytics))
        // .route("/analytics/system", get(analytics::system_analytics))
        
        // ── Tool endpoints (all 26 tools accessible via API) ──────────
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
        // New tools (7 recently wired)
        .route("/tools/mobile-money", get(endpoints::tools::mobile_money_signals))
        .route("/tools/composite-index", get(endpoints::tools::composite_index_status))
        .route("/tools/anomaly", get(endpoints::tools::anomaly_detector_status))
        .route("/tools/demand-forecast", get(endpoints::tools::demand_forecast))
        .route("/tools/scenario", get(endpoints::tools::scenario_modeler_status))
        .route("/tools/policy-impact", get(endpoints::tools::policy_impact_status))
        .route("/tools/inequality", get(endpoints::tools::inequality_tracker_status))
        
        // Billing routes
        .route("/billing/tiers", get(endpoints::billing::list_tiers))
        .route("/billing/subscriptions", post(endpoints::billing::create_subscription))
        .route("/billing/subscriptions/{org_id}", get(endpoints::billing::get_subscription))
        .route("/billing/subscriptions/{id}/tier", put(endpoints::billing::change_tier))
        .route("/billing/subscriptions/{id}/cancel", post(endpoints::billing::cancel_subscription))
        .route("/billing/api-keys", post(endpoints::billing::create_api_key))
        .route("/billing/api-keys/{org_id}", get(endpoints::billing::list_api_keys))
        .route("/billing/api-keys/{id}", delete(endpoints::billing::revoke_api_key))
        .route("/billing/usage/{org_id}", get(endpoints::billing::get_usage))
        .route("/billing/invoices/{org_id}", get(endpoints::billing::list_invoices))
        .route("/billing/invoices/detail/{id}", get(endpoints::billing::get_invoice))
        .route("/billing/invoices/{id}/finalize", post(endpoints::billing::finalize_invoice))
        .route("/billing/invoices/{id}/pay", post(endpoints::billing::pay_invoice))
}
