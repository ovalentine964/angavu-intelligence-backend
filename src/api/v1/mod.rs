pub mod auth;
pub mod users;
pub mod intelligence;
pub mod memory;
pub mod sync;
pub mod analytics;

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
}
