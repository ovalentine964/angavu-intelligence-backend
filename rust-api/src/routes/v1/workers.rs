use axum::{
    extract::{Path, State},
    Json,
    Router,
    routing::{get, put},
};
use uuid::Uuid;

use crate::error::{AppError, AppResult};
use crate::middleware::AuthContext;
use crate::models::worker::*;
use crate::AppState;

/// Mount worker routes (auth required).
pub fn routes() -> Router<AppState> {
    Router::new()
        .route("/workers/{id}", get(get_worker).put(update_worker))
        .route("/workers/{id}/score", get(get_score))
}

/// GET /workers/{id}
///
/// Retrieve a worker's business profile.
#[utoipa::path(
    get,
    path = "/api/v1/workers/{id}",
    params(
        ("id" = Uuid, Path, description = "Worker ID"),
    ),
    responses(
        (status = 200, description = "Worker profile", body = Worker),
        (status = 404, description = "Worker not found"),
        (status = 403, description = "Access denied"),
    ),
    security(
        ("bearer_auth" = [])
    ),
    tag = "workers"
)]
async fn get_worker(
    State(_state): State<AppState>,
    auth_ctx: AuthContext,
    Path(id): Path<Uuid>,
) -> AppResult<Json<serde_json::Value>> {
    // Workers can view their own profile; admins/managers can view any
    if auth_ctx.user_id != id && auth_ctx.role != "admin" && auth_ctx.role != "manager" {
        return Err(AppError::Forbidden(
            "You can only view your own profile".to_string(),
        ));
    }

    // TODO: Fetch worker from database
    tracing::info!(
        requester = %auth_ctx.user_id,
        worker_id = %id,
        "Fetching worker profile"
    );

    Err(AppError::NotFound(format!("Worker {} not found", id)))
}

/// PUT /workers/{id}
///
/// Update a worker's business profile.
#[utoipa::path(
    put,
    path = "/api/v1/workers/{id}",
    params(
        ("id" = Uuid, Path, description = "Worker ID"),
    ),
    request_body = UpdateWorkerRequest,
    responses(
        (status = 200, description = "Profile updated", body = Worker),
        (status = 404, description = "Worker not found"),
        (status = 403, description = "Access denied"),
        (status = 422, description = "Validation error"),
    ),
    security(
        ("bearer_auth" = [])
    ),
    tag = "workers"
)]
async fn update_worker(
    State(_state): State<AppState>,
    auth_ctx: AuthContext,
    Path(id): Path<Uuid>,
    Json(body): Json<UpdateWorkerRequest>,
) -> AppResult<Json<serde_json::Value>> {
    // Workers can only update their own profile
    if auth_ctx.user_id != id && auth_ctx.role != "admin" {
        return Err(AppError::Forbidden(
            "You can only update your own profile".to_string(),
        ));
    }

    // Validate optional fields if provided
    if let Some(ref name) = body.business_name {
        if name.trim().is_empty() {
            return Err(AppError::Validation(
                "Business name cannot be empty".to_string(),
            ));
        }
    }

    // TODO: Fetch existing worker, apply partial update, save to database
    tracing::info!(
        requester = %auth_ctx.user_id,
        worker_id = %id,
        "Updating worker profile"
    );

    Err(AppError::NotFound(format!("Worker {} not found", id)))
}

/// GET /workers/{id}/score
///
/// Get the Alama Score (credit score 0–1000) for a worker.
#[utoipa::path(
    get,
    path = "/api/v1/workers/{id}/score",
    params(
        ("id" = Uuid, Path, description = "Worker ID"),
    ),
    responses(
        (status = 200, description = "Alama Score", body = AlamaScoreResponse),
        (status = 404, description = "Worker not found"),
        (status = 403, description = "Access denied"),
    ),
    security(
        ("bearer_auth" = [])
    ),
    tag = "workers"
)]
async fn get_score(
    State(_state): State<AppState>,
    auth_ctx: AuthContext,
    Path(id): Path<Uuid>,
) -> AppResult<Json<serde_json::Value>> {
    // Workers can view their own score; admins/managers can view any
    if auth_ctx.user_id != id && auth_ctx.role != "admin" && auth_ctx.role != "manager" {
        return Err(AppError::Forbidden(
            "You can only view your own score".to_string(),
        ));
    }

    // TODO: Compute or fetch Alama Score from intelligence engine
    tracing::info!(
        requester = %auth_ctx.user_id,
        worker_id = %id,
        "Fetching Alama Score"
    );

    // Placeholder: return a zeroed score structure
    // In production this would call the LLM service or read from DB
    let response = AlamaScoreResponse {
        score: 0,
        grade: "N/A".to_string(),
        breakdown: ScoreBreakdown {
            consistency: 0,
            volume_growth: 0,
            stability: 0,
            financial_health: 0,
            engagement: 0,
        },
        calculated_at: chrono::Utc::now(),
        trend: "unknown".to_string(),
    };

    Ok(Json(serde_json::json!(response)))
}
