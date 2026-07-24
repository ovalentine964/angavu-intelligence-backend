use axum::{Json, Router, routing::post};
use crate::error::AppResult;
use crate::middleware::AuthContext;
use crate::AppState;

/// Mount sync routes (auth required).
pub fn routes() -> Router<AppState> {
    Router::new()
        .route("/sync/batch", post(batch_sync))
}

/// POST /sync/batch
async fn batch_sync(
    auth_ctx: AuthContext,
    Json(body): Json<serde_json::Value>,
) -> AppResult<Json<serde_json::Value>> {
    tracing::info!(user_id = %auth_ctx.user_id, "Batch sync requested");
    Ok(Json(serde_json::json!({
        "synced_count": 0,
        "failed": [],
        "status": "not_implemented"
    })))
}
