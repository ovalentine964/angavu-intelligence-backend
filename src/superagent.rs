//! Superagent module — bridges the tools subsystem into the application.
//!
//! Re-exports the OODAOrchestrator and provides the Axum router
//! for superagent control-plane endpoints.

pub use crate::tools::OODAOrchestrator;

use axum::{extract::State, routing::get, Json, Router};
use std::sync::Arc;

/// Build the superagent control-plane router.
pub fn router() -> Router<Arc<crate::db::AppState>> {
    Router::new()
        .route("/status", get(get_status))
        .route("/cycle", get(trigger_cycle))
        .route("/history", get(get_history))
}

async fn get_status(
    State(state): State<Arc<crate::db::AppState>>,
) -> Json<serde_json::Value> {
    let count = state.orchestrator.cycle_count().await;
    let orientation = state.orchestrator.current_orientation().await;
    Json(serde_json::json!({
        "cycle_count": count,
        "orientation": orientation,
        "status": "running",
    }))
}

async fn trigger_cycle(
    State(state): State<Arc<crate::db::AppState>>,
) -> Json<serde_json::Value> {
    match state.orchestrator.run_cycle().await {
        Ok(result) => Json(serde_json::json!({
            "status": "completed",
            "cycle_id": result.cycle_id,
            "duration_ms": result.duration_ms,
        })),
        Err(e) => {
            tracing::error!(error = %e, "Manual cycle failed");
            Json(serde_json::json!({
                "status": "error",
                "error": e.to_string(),
            }))
        }
    }
}

async fn get_history(
    State(state): State<Arc<crate::db::AppState>>,
) -> Json<serde_json::Value> {
    let history = state.orchestrator.history().await;
    Json(serde_json::json!({
        "cycles": history.len(),
        "history": history,
    }))
}
