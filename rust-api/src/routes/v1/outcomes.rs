use axum::{
    extract::State,
    Json,
    Router,
    routing::{get, post},
};
use chrono::Utc;
use uuid::Uuid;

use crate::error::{AppError, AppResult};
use crate::middleware::AuthContext;
use crate::models::outcome::*;
use crate::AppState;

/// Mount outcome routes (auth required).
pub fn routes() -> Router<AppState> {
    Router::new()
        .route("/outcomes/consent", post(update_consent))
        .route("/outcomes/track", get(track_outcomes))
        .route("/outcomes/verify", post(verify_outcome))
}

/// Consent update request body.
#[derive(Debug, serde::Deserialize, utoipa::ToSchema)]
pub struct ConsentRequest {
    /// Whether the user consents to outcome tracking
    pub consent: bool,
    /// Optional consent scope (e.g., "revenue", "all")
    #[serde(default = "default_consent_scope")]
    pub scope: String,
}

fn default_consent_scope() -> String {
    "all".to_string()
}

/// POST /outcomes/consent
///
/// Update the user's consent for outcome-based tracking.
#[utoipa::path(
    post,
    path = "/api/v1/outcomes/consent",
    request_body = ConsentRequest,
    responses(
        (status = 200, description = "Consent updated"),
        (status = 422, description = "Validation error"),
    ),
    security(
        ("bearer_auth" = [])
    ),
    tag = "outcomes"
)]
async fn update_consent(
    State(_state): State<AppState>,
    auth_ctx: AuthContext,
    Json(body): ConsentRequest,
) -> AppResult<Json<serde_json::Value>> {
    let valid_scopes = ["all", "revenue", "cost", "efficiency"];
    if !valid_scopes.contains(&body.scope.as_str()) {
        return Err(AppError::Validation(format!(
            "Invalid scope '{}'. Must be one of: {:?}",
            body.scope, valid_scopes
        )));
    }

    // TODO: Persist consent record in database
    tracing::info!(
        user_id = %auth_ctx.user_id,
        consent = body.consent,
        scope = %body.scope,
        "Consent updated"
    );

    Ok(Json(serde_json::json!({
        "user_id": auth_ctx.user_id,
        "consent": body.consent,
        "scope": body.scope,
        "updated_at": Utc::now(),
    })))
}

/// GET /outcomes/track
///
/// Retrieve tracked outcomes for the authenticated user.
#[utoipa::path(
    get,
    path = "/api/v1/outcomes/track",
    responses(
        (status = 200, description = "Tracked outcomes summary", body = OutcomeSummary),
    ),
    security(
        ("bearer_auth" = [])
    ),
    tag = "outcomes"
)]
async fn track_outcomes(
    State(_state): State<AppState>,
    auth_ctx: AuthContext,
) -> AppResult<Json<serde_json::Value>> {
    // TODO: Query outcomes from database for this user
    tracing::info!(
        user_id = %auth_ctx.user_id,
        "Fetching tracked outcomes"
    );

    let summary = OutcomeSummary {
        total_outcomes: 0,
        total_value: 0.0,
        by_type: vec![],
        monthly_trend: vec![],
    };

    Ok(Json(serde_json::json!(summary)))
}

/// Outcome verification request.
#[derive(Debug, serde::Deserialize, utoipa::ToSchema)]
pub struct VerifyOutcomeRequest {
    /// Outcome ID to verify
    pub outcome_id: Uuid,
    /// Verification action: confirm, dispute
    pub action: String,
    /// Optional note from verifier
    pub note: Option<String>,
}

/// POST /outcomes/verify
///
/// Verify a tracked outcome (confirm or dispute).
#[utoipa::path(
    post,
    path = "/api/v1/outcomes/verify",
    request_body = VerifyOutcomeRequest,
    responses(
        (status = 200, description = "Outcome verified", body = Outcome),
        (status = 404, description = "Outcome not found"),
        (status = 422, description = "Validation error"),
    ),
    security(
        ("bearer_auth" = [])
    ),
    tag = "outcomes"
)]
async fn verify_outcome(
    State(_state): State<AppState>,
    auth_ctx: AuthContext,
    Json(body): Json<VerifyOutcomeRequest>,
) -> AppResult<Json<serde_json::Value>> {
    let valid_actions = ["confirm", "dispute"];
    if !valid_actions.contains(&body.action.as_str()) {
        return Err(AppError::Validation(format!(
            "Invalid action '{}'. Must be one of: {:?}",
            body.action, valid_actions
        )));
    }

    // TODO: Fetch outcome from DB, verify ownership, update status
    tracing::info!(
        user_id = %auth_ctx.user_id,
        outcome_id = %body.outcome_id,
        action = %body.action,
        "Verifying outcome"
    );

    // Placeholder — return 404 until DB is wired
    Err(AppError::NotFound(format!(
        "Outcome {} not found",
        body.outcome_id
    )))
}
