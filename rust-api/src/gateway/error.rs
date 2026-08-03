// src/gateway/error.rs
//
// Unified API Error Response — Single source of truth for all error formatting.
//
// Every error returned by the Angavu API follows this structure:
// {
//   "error": {
//     "code": "RATE_LIMITED",
//     "message": "Too many requests. Try again in 30 seconds.",
//     "details": { ... },
//     "request_id": "uuid"
//   }
// }

use axum::{
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde::Serialize;

/// Unified error response body matching OpenAPI `Error` schema.
#[derive(Debug, Serialize)]
pub struct ErrorResponse {
    pub error: ErrorBody,
}

/// Inner error details.
#[derive(Debug, Serialize)]
pub struct ErrorBody {
    /// Machine-readable error code (UPPER_SNAKE_CASE).
    pub code: String,
    /// Human-readable message (English; client can translate).
    pub message: String,
    /// Optional structured details (field validation errors, etc.).
    #[serde(skip_serializing_if = "Option::is_none")]
    pub details: Option<serde_json::Value>,
    /// Request correlation ID for debugging.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub request_id: Option<String>,
}

impl ErrorResponse {
    /// Create a new error with code + message.
    pub fn new(code: impl Into<String>, message: impl Into<String>) -> Self {
        Self {
            error: ErrorBody {
                code: code.into(),
                message: message.into(),
                details: None,
                request_id: None,
            },
        }
    }

    /// Attach structured details.
    pub fn with_details(mut self, details: serde_json::Value) -> Self {
        self.error.details = Some(details);
        self
    }

    /// Attach a request ID.
    pub fn with_request_id(mut self, request_id: impl Into<String>) -> Self {
        self.error.request_id = Some(request_id.into());
        self
    }

    // ── Convenience constructors for common errors ──────────

    pub fn bad_request(message: impl Into<String>) -> Self {
        Self::new("BAD_REQUEST", message)
    }

    pub fn unauthorized() -> Self {
        Self::new("UNAUTHORIZED", "Missing or invalid authentication token.")
    }

    pub fn forbidden() -> Self {
        Self::new(
            "FORBIDDEN",
            "You do not have permission to access this resource.",
        )
    }

    pub fn not_found(resource: impl Into<String>) -> Self {
        Self::new("NOT_FOUND", format!("{} not found.", resource.into()))
    }

    pub fn conflict(message: impl Into<String>) -> Self {
        Self::new("CONFLICT", message)
    }

    pub fn rate_limited(retry_after_secs: u64) -> Self {
        Self::new(
            "RATE_LIMITED",
            format!(
                "Too many requests. Try again in {} seconds.",
                retry_after_secs
            ),
        )
    }

    pub fn k_anonymity_violation(cohort_size: usize, minimum: usize) -> Self {
        Self::new(
            "K_ANONYMITY_VIOLATION",
            format!(
                "Cohort has {} members but minimum is {} to protect privacy.",
                cohort_size, minimum
            ),
        )
        .with_details(serde_json::json!({
            "actual_size": cohort_size,
            "minimum_size": minimum
        }))
    }

    pub fn not_implemented(tool: impl Into<String>) -> Self {
        Self::new(
            "NOT_IMPLEMENTED",
            format!(
                "{} is not yet available. This endpoint is coming soon.",
                tool.into()
            ),
        )
    }

    pub fn privacy_budget_exhausted(query_type: &str, remaining: f64, window_reset: &str) -> Self {
        Self::new(
            "PRIVACY_BUDGET_EXHAUSTED",
            format!(
                "Privacy budget exhausted for query type '{}'. Remaining: {:.4}. Window resets at {}.",
                query_type, remaining, window_reset
            ),
        )
        .with_details(serde_json::json!({
            "query_type": query_type,
            "remaining_epsilon": remaining,
            "window_reset_at": window_reset
        }))
    }

    pub fn internal() -> Self {
        Self::new(
            "INTERNAL_ERROR",
            "An unexpected error occurred. Please try again later.",
        )
    }

    pub fn validation(field: impl Into<String>, reason: impl Into<String>) -> Self {
        Self::new(
            "VALIDATION_ERROR",
            format!(
                "Validation failed for '{}': {}",
                field.into(),
                reason.into()
            ),
        )
    }

    pub fn expired(message: impl Into<String>) -> Self {
        Self::new("EXPIRED", message)
    }
}

/// Convert ErrorResponse into an Axum Response with the correct status code.
impl IntoResponse for ErrorResponse {
    fn into_response(self) -> Response {
        let status = match self.error.code.as_str() {
            "BAD_REQUEST" | "VALIDATION_ERROR" => StatusCode::BAD_REQUEST,
            "UNAUTHORIZED" => StatusCode::UNAUTHORIZED,
            "FORBIDDEN" => StatusCode::FORBIDDEN,
            "NOT_FOUND" => StatusCode::NOT_FOUND,
            "CONFLICT" => StatusCode::CONFLICT,
            "RATE_LIMITED" => StatusCode::TOO_MANY_REQUESTS,
            "K_ANONYMITY_VIOLATION" | "PRIVACY_BUDGET_EXHAUSTED" => StatusCode::FORBIDDEN,
            "NOT_IMPLEMENTED" => StatusCode::NOT_IMPLEMENTED,
            "EXPIRED" => StatusCode::GONE,
            _ => StatusCode::INTERNAL_SERVER_ERROR,
        };

        (status, Json(self)).into_response()
    }
}

/// Allow converting ErrorResponse from common error types.
impl From<anyhow::Error> for ErrorResponse {
    fn from(err: anyhow::Error) -> Self {
        tracing::error!(error = %err, "Unhandled error");
        ErrorResponse::internal()
    }
}

impl From<sqlx::Error> for ErrorResponse {
    fn from(err: sqlx::Error) -> Self {
        tracing::error!(error = %err, "Database error");
        ErrorResponse::internal()
    }
}
