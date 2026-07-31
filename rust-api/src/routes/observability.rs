// Observability API routes for Angavu Intelligence Backend
// Exposes SLO status, agent trace stats, and health metrics

use axum::{
    extract::{Query, State},
    http::StatusCode,
    Json,
    Router,
    routing::get,
};
use serde::{Deserialize, Serialize};
use std::sync::Arc;

use crate::observability::slo::SloTracker;
use crate::observability::agent_traces::AgentTraceLogger;

/// Observability state shared across routes
pub struct ObservabilityState {
    pub slo_tracker: Arc<SloTracker>,
    pub trace_logger: Option<Arc<AgentTraceLogger>>,
}

/// Build observability routes
pub fn observability_routes(state: Arc<ObservabilityState>) -> Router {
    Router::new()
        .route("/slo", get(get_slo_status))
        .route("/slo/breached", get(get_breached_slos))
        .route("/traces/stats", get(get_trace_stats))
        .with_state(state)
}

/// Query params for trace stats
#[derive(Deserialize)]
struct TraceStatsQuery {
    hours: Option<i64>,
}

/// SLO status response
#[derive(Serialize)]
struct SloStatusResponse {
    slos: Vec<SloStatusItem>,
    all_met: bool,
}

#[derive(Serialize)]
struct SloStatusItem {
    name: String,
    description: String,
    target_percent: f64,
    current_value: f64,
    is_met: bool,
    error_budget_remaining_percent: f64,
}

/// GET /observability/slo — Current SLO status
async fn get_slo_status(
    State(state): State<Arc<ObservabilityState>>,
) -> Json<SloStatusResponse> {
    let statuses = state.slo_tracker.statuses();
    let items: Vec<SloStatusItem> = statuses
        .iter()
        .map(|s| SloStatusItem {
            name: s.definition.name.clone(),
            description: s.definition.description.clone(),
            target_percent: s.definition.target_percent,
            current_value: s.current_value,
            is_met: s.is_met,
            error_budget_remaining_percent: s.error_budget_remaining_percent,
        })
        .collect();

    let all_met = items.iter().all(|i| i.is_met);

    Json(SloStatusResponse {
        slos: items,
        all_met,
    })
}

/// GET /observability/slo/breached — Currently breached SLOs
async fn get_breached_slos(
    State(state): State<Arc<ObservabilityState>>,
) -> Json<Vec<SloStatusItem>> {
    let breached = state.slo_tracker.breached_slos();
    let items: Vec<SloStatusItem> = breached
        .iter()
        .map(|s| SloStatusItem {
            name: s.definition.name.clone(),
            description: s.definition.description.clone(),
            target_percent: s.definition.target_percent,
            current_value: s.current_value,
            is_met: s.is_met,
            error_budget_remaining_percent: s.error_budget_remaining_percent,
        })
        .collect();

    Json(items)
}

/// GET /observability/traces/stats — Agent trace statistics
async fn get_trace_stats(
    State(state): State<Arc<ObservabilityState>>,
    Query(params): Query<TraceStatsQuery>,
) -> Result<Json<serde_json::Value>, StatusCode> {
    let hours = params.hours.unwrap_or(24);

    match &state.trace_logger {
        Some(logger) => {
            match logger.get_trace_stats(hours).await {
                Ok(stats) => Ok(Json(serde_json::json!(stats))),
                Err(e) => {
                    tracing::error!("Trace stats error: {}", e);
                    Err(StatusCode::INTERNAL_SERVER_ERROR)
                }
            }
        }
        None => Ok(Json(serde_json::json!({
            "message": "Trace logger not configured",
            "time_range_hours": hours
        }))),
    }
}
