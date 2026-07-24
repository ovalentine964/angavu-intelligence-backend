use axum::{Json, Router, routing::post};
use crate::error::AppResult;
use crate::middleware::AuthContext;
use crate::AppState;

/// Mount voice routes (auth required).
pub fn routes() -> Router<AppState> {
    Router::new()
        .route("/voice/transcribe", post(transcribe))
}

/// POST /voice/transcribe
async fn transcribe(
    auth_ctx: AuthContext,
    Json(_body): Json<serde_json::Value>,
) -> AppResult<Json<serde_json::Value>> {
    tracing::info!(user_id = %auth_ctx.user_id, "Voice transcription requested");
    Ok(Json(serde_json::json!({
        "transcription": "",
        "status": "not_implemented"
    })))
}
