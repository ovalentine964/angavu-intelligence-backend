use axum::{Json, Router, routing::post};
use uuid::Uuid;
use chrono::Utc;

use crate::error::AppResult;
use crate::middleware::AuthContext;
use crate::models::intelligence::*;
use crate::AppState;

/// Mount intelligence routes (auth required).
pub fn routes() -> Router<AppState> {
    Router::new()
        .route("/intelligence/query", post(query))
}

/// POST /intelligence/query
///
/// Run an intelligence query against the user's business data.
#[utoipa::path(
    post,
    path = "/api/v1/intelligence/query",
    request_body = IntelligenceQueryRequest,
    responses(
        (status = 200, description = "Intelligence response", body = IntelligenceResponse),
    ),
    security(
        ("bearer_auth" = [])
    ),
    tag = "intelligence"
)]
async fn query(
    auth_ctx: AuthContext,
    Json(body): Json<IntelligenceQueryRequest>,
) -> AppResult<Json<serde_json::Value>> {
    // TODO: Forward to LLM inference service
    tracing::info!(
        user_id = %auth_ctx.user_id,
        query_type = ?body.query_type,
        "Intelligence query received"
    );

    let response = IntelligenceResponse {
        query_id: Uuid::new_v4(),
        query_type: body.query_type,
        summary: "Intelligence engine not yet wired.".to_string(),
        insights: vec![],
        recommendations: vec![],
        data_points: None,
        confidence: 0.0,
        generated_at: Utc::now(),
    };

    Ok(Json(serde_json::json!(response)))
}
