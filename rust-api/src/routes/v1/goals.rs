use axum::{Json, Router, routing::{get, post}};
use crate::error::AppResult;
use crate::middleware::AuthContext;
use crate::AppState;

/// Mount goals routes (auth required).
pub fn routes() -> Router<AppState> {
    Router::new()
        .route("/goals", post(create_goal).get(list_goals))
}

/// POST /goals
async fn create_goal(
    auth_ctx: AuthContext,
    Json(body): Json<serde_json::Value>,
) -> AppResult<Json<serde_json::Value>> {
    tracing::info!(user_id = %auth_ctx.user_id, "Create goal requested");
    Ok(Json(serde_json::json!({"status": "not_implemented"})))
}

/// GET /goals
async fn list_goals(
    auth_ctx: AuthContext,
) -> AppResult<Json<serde_json::Value>> {
    tracing::info!(user_id = %auth_ctx.user_id, "List goals requested");
    Ok(Json(serde_json::json!({"data": [], "total": 0})))
}
