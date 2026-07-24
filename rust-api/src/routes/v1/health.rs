use axum::{extract::State, http::StatusCode, Json, Router, routing::get};
use serde::Serialize;
use utoipa::ToSchema;

use crate::AppState;

/// Basic health response.
#[derive(Debug, Serialize, ToSchema)]
pub struct HealthResponse {
    /// Service status
    pub status: String,
    /// Service name
    pub service: String,
    /// Semantic version
    pub version: String,
    /// Environment (development / staging / production)
    pub environment: String,
    /// Current server timestamp (RFC 3339)
    pub timestamp: String,
}

/// Readiness response.
#[derive(Debug, Serialize, ToSchema)]
pub struct ReadinessResponse {
    /// Overall ready status
    pub ready: bool,
    /// Database connectivity check
    pub database: ComponentStatus,
    /// LLM service connectivity check
    pub llm_service: ComponentStatus,
}

/// Individual component health.
#[derive(Debug, Serialize, ToSchema)]
pub struct ComponentStatus {
    pub healthy: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub latency_ms: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub message: Option<String>,
}

/// Mount health routes (public, no auth).
pub fn routes() -> Router<AppState> {
    Router::new()
        .route("/health", get(basic_health))
        .route("/health/ready", get(readiness))
}

/// GET /health
///
/// Basic liveness probe. Returns 200 if the process is running.
#[utoipa::path(
    get,
    path = "/api/v1/health",
    responses(
        (status = 200, description = "Service is healthy", body = HealthResponse),
    ),
    tag = "health"
)]
async fn basic_health(
    State(state): State<AppState>,
) -> (StatusCode, Json<HealthResponse>) {
    let body = HealthResponse {
        status: "ok".to_string(),
        service: "angavu-intelligence-api".to_string(),
        version: env!("CARGO_PKG_VERSION").to_string(),
        environment: state.config.environment.clone(),
        timestamp: chrono::Utc::now().to_rfc3339(),
    };
    (StatusCode::OK, Json(body))
}

/// GET /health/ready
///
/// Readiness probe — checks that downstream dependencies (database, LLM service) are reachable.
#[utoipa::path(
    get,
    path = "/api/v1/health/ready",
    responses(
        (status = 200, description = "Service is ready", body = ReadinessResponse),
        (status = 503, description = "Service is not ready", body = ReadinessResponse),
    ),
    tag = "health"
)]
async fn readiness(
    State(state): State<AppState>,
) -> (StatusCode, Json<ReadinessResponse>) {
    // Database check — TODO: replace with real pool ping when DB is wired
    let db_status = ComponentStatus {
        healthy: true,
        latency_ms: None,
        message: Some("database pool not yet wired — placeholder".to_string()),
    };

    // LLM service check — lightweight TCP / HTTP probe
    let llm_status = match reqwest::get(format!("{}/health", state.config.llm_service_url)).await {
        Ok(resp) => ComponentStatus {
            healthy: resp.status().is_success(),
            latency_ms: None,
            message: None,
        },
        Err(e) => ComponentStatus {
            healthy: false,
            latency_ms: None,
            message: Some(format!("LLM service unreachable: {}", e)),
        },
    };

    let ready = db_status.healthy && llm_status.healthy;
    let status_code = if ready {
        StatusCode::OK
    } else {
        StatusCode::SERVICE_UNAVAILABLE
    };

    let body = ReadinessResponse {
        ready,
        database: db_status,
        llm_service: llm_status,
    };

    (status_code, Json(body))
}
