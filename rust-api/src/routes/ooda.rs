// rust-api/src/routes/ooda.rs

use axum::{extract::State, http::StatusCode, Json};
use serde::{Deserialize, Serialize};

use crate::graph::ooda::*;
use crate::graph::pipeline::*;
use crate::AppState;

/// GET /api/v1/ooda/status — Current OODA cycle status
pub async fn ooda_status(
    State(state): State<AppState>,
) -> Result<Json<OodaStatusResponse>, StatusCode> {
    // Query latest OODA cycle from PostgreSQL
    let cycle = sqlx::query_as!(
        OodaCycleRow,
        "SELECT id, cycle_speed, cycle_number, started_at, completed_at, status
         FROM ooda_cycles
         ORDER BY started_at DESC
         LIMIT 1"
    )
    .fetch_optional(&state.db)
    .await
    .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;

    Ok(Json(OodaStatusResponse {
        current_cycle: cycle,
        phases_completed: vec![],  // populated from ooda_phase_executions
        pipeline_progress: 0.0,
    }))
}

/// POST /api/v1/ooda/trigger — Manually trigger an OODA cycle
pub async fn trigger_ooda(
    State(state): State<AppState>,
    Json(req): Json<TriggerOodaRequest>,
) -> Result<Json<TriggerOodaResponse>, StatusCode> {
    let graph = OodaGraph::standard(req.speed);

    // Create cycle record
    let cycle_id = uuid::Uuid::new_v4();
    sqlx::query!(
        "INSERT INTO ooda_cycles (id, cycle_speed, cycle_number, trigger_source)
         VALUES ($1, $2, (SELECT COALESCE(MAX(cycle_number), 0) + 1 FROM ooda_cycles WHERE cycle_speed = $2), $3)",
        cycle_id,
        req.speed as CycleSpeed,
        req.trigger_source.unwrap_or_else(|| "manual".to_string()),
    )
    .execute(&state.db)
    .await
    .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;

    // Spawn async OODA execution
    let db = state.db.clone();
    let pipeline = PipelineDag::standard_intelligence_pipeline();
    tokio::spawn(async move {
        // Execute OODA phases in order
        for phase in [OodaPhase::Observe, OodaPhase::Orient, OodaPhase::Decide, OodaPhase::Act] {
            // Check circuit breaker
            // Execute phase
            // Record result
            // Check conditional transitions
        }
    });

    Ok(Json(TriggerOodaResponse {
        cycle_id,
        status: "started".to_string(),
    }))
}

#[derive(Deserialize)]
pub struct TriggerOodaRequest {
    pub speed: CycleSpeed,
    pub trigger_source: Option<String>,
}

#[derive(Serialize)]
pub struct TriggerOodaResponse {
    pub cycle_id: uuid::Uuid,
    pub status: String,
}

#[derive(Serialize)]
pub struct OodaStatusResponse {
    pub current_cycle: Option<OodaCycleRow>,
    pub phases_completed: Vec<OodaPhaseRow>,
    pub pipeline_progress: f64,
}

#[derive(Serialize)]
pub struct OodaCycleRow {
    pub id: uuid::Uuid,
    pub cycle_speed: String,
    pub cycle_number: i64,
    pub started_at: chrono::DateTime<chrono::Utc>,
    pub completed_at: Option<chrono::DateTime<chrono::Utc>>,
    pub status: String,
}

#[derive(Serialize)]
pub struct OodaPhaseRow {
    pub phase: String,
    pub status: String,
    pub duration_ms: Option<i64>,
}
