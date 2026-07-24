use axum::{Json, Router, routing::get};
use crate::error::AppResult;
use crate::middleware::AuthContext;
use crate::AppState;

/// Mount credit routes (auth required).
pub fn routes() -> Router<AppState> {
    Router::new()
        .route("/credit/report", get(credit_report))
}

/// GET /credit/report
///
/// Get the user's credit report summary.
async fn credit_report(
    auth_ctx: AuthContext,
) -> AppResult<Json<serde_json::Value>> {
    tracing::info!(user_id = %auth_ctx.user_id, "Credit report requested");

    Ok(Json(serde_json::json!({
        "user_id": auth_ctx.user_id,
        "credit_score": null,
        "status": "not_available",
        "message": "Credit reporting not yet implemented"
    })))
}
