use axum::{
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde::Serialize;
use utoipa::ToSchema;

/// Unified API error response.
#[derive(Debug, Serialize, ToSchema)]
pub struct ApiError {
    /// HTTP status code
    pub status: u16,
    /// Error type identifier
    pub error: String,
    /// Human-readable error message
    pub message: String,
    /// Optional field-level validation errors
    #[serde(skip_serializing_if = "Option::is_none")]
    pub details: Option<Vec<FieldError>>,
}

/// Field-level validation error.
#[derive(Debug, Serialize, ToSchema)]
pub struct FieldError {
    /// Field name that failed validation
    pub field: String,
    /// Validation error message
    pub message: String,
}

/// Application error enum covering all error types.
#[derive(Debug, thiserror::Error)]
pub enum AppError {
    #[error("Authentication failed: {0}")]
    Unauthorized(String),

    #[error("Access denied: {0}")]
    Forbidden(String),

    #[error("Resource not found: {0}")]
    NotFound(String),

    #[error("Validation failed: {0}")]
    Validation(String),

    #[error("Validation failed with field errors")]
    ValidationWithDetails(Vec<FieldError>),

    #[error("Conflict: {0}")]
    Conflict(String),

    #[error("Database error: {0}")]
    Database(#[from] sqlx::Error),

    #[error("Internal error: {0}")]
    Internal(String),

    #[error("External service error: {0}")]
    ExternalService(String),

    #[error("Rate limit exceeded")]
    RateLimitExceeded,

    #[error("Bad request: {0}")]
    BadRequest(String),
}

impl AppError {
    fn status_code(&self) -> StatusCode {
        match self {
            AppError::Unauthorized(_) => StatusCode::UNAUTHORIZED,
            AppError::Forbidden(_) => StatusCode::FORBIDDEN,
            AppError::NotFound(_) => StatusCode::NOT_FOUND,
            AppError::Validation(_) | AppError::ValidationWithDetails(_) => {
                StatusCode::UNPROCESSABLE_ENTITY
            }
            AppError::Conflict(_) => StatusCode::CONFLICT,
            AppError::Database(_) => StatusCode::INTERNAL_SERVER_ERROR,
            AppError::Internal(_) => StatusCode::INTERNAL_SERVER_ERROR,
            AppError::ExternalService(_) => StatusCode::BAD_GATEWAY,
            AppError::RateLimitExceeded => StatusCode::TOO_MANY_REQUESTS,
            AppError::BadRequest(_) => StatusCode::BAD_REQUEST,
        }
    }

    fn error_type(&self) -> &str {
        match self {
            AppError::Unauthorized(_) => "unauthorized",
            AppError::Forbidden(_) => "forbidden",
            AppError::NotFound(_) => "not_found",
            AppError::Validation(_) | AppError::ValidationWithDetails(_) => "validation_error",
            AppError::Conflict(_) => "conflict",
            AppError::Database(_) => "internal_error",
            AppError::Internal(_) => "internal_error",
            AppError::ExternalService(_) => "external_service_error",
            AppError::RateLimitExceeded => "rate_limit_exceeded",
            AppError::BadRequest(_) => "bad_request",
        }
    }
}

impl IntoResponse for AppError {
    fn into_response(self) -> Response {
        let status = self.status_code();
        let details = match &self {
            AppError::ValidationWithDetails(d) => Some(d.clone()),
            _ => None,
        };

        // Log internal errors at error level
        if status.is_server_error() {
            tracing::error!(error = %self, "Server error");
        } else if status.is_client_error() {
            tracing::warn!(error = %self, "Client error");
        }

        let body = ApiError {
            status: status.as_u16(),
            error: self.error_type().to_string(),
            message: self.to_string(),
            details,
        };

        (status, Json(body)).into_response()
    }
}

/// Convenience alias for Results using AppError.
pub type AppResult<T> = Result<T, AppError>;
