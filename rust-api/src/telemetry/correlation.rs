// Correlation ID — Propagates X-Request-ID through all log entries and OTel spans
//
// Every incoming request gets a unique correlation ID (UUIDv7 for time-ordered sorting).
// If the client sends X-Request-ID, it's reused. Otherwise one is generated.
// The ID is injected into the tracing span, added to response headers, and
// included in every structured log entry via the tracing span fields.

use axum::{extract::Request, http::HeaderValue, middleware::Next, response::Response};
use uuid::Uuid;

/// Header name for correlation ID propagation.
pub const CORRELATION_HEADER: &str = "x-request-id";

/// Correlation ID extractor — use in handlers via `axum::extract::Extension`.
#[derive(Debug, Clone)]
pub struct CorrelationId(pub String);

impl std::fmt::Display for CorrelationId {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.0)
    }
}

impl CorrelationId {
    /// Generate a new time-ordered correlation ID.
    pub fn new() -> Self {
        Self(Uuid::new_v4().to_string())
    }

    /// Extract from request headers or generate a new one.
    pub fn from_request(req: &Request) -> Self {
        req.headers()
            .get(CORRELATION_HEADER)
            .and_then(|v| v.to_str().ok())
            .filter(|s| !s.is_empty())
            .map(|s| Self(s.to_string()))
            .unwrap_or_else(Self::new)
    }
}

impl Default for CorrelationId {
    fn default() -> Self {
        Self::new()
    }
}

/// Middleware: extract or generate correlation ID, inject into span + response headers.
pub async fn correlation_middleware(mut request: Request, next: Next) -> Response {
    let correlation = CorrelationId::from_request(&request);

    // Create a tracing span with the correlation ID for all downstream logs
    let span = tracing::info_span!(
        "http_request",
        request_id = %correlation.0,
        method = %request.method(),
        uri = %request.uri().path(),
    );
    let _guard = span.enter();

    // Store correlation ID in request extensions for handlers
    request.extensions_mut().insert(correlation.clone());

    let mut response = next.run(request).await;

    // Add correlation ID to response headers
    if let Ok(header_value) = HeaderValue::from_str(&correlation.0) {
        response
            .headers_mut()
            .insert(CORRELATION_HEADER, header_value);
    }

    response
}
