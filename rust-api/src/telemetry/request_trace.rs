// Request Trace Middleware — Enriches OTel spans with request context
//
// Creates a parent span for every HTTP request with:
// - request_id (from X-Request-ID or auto-generated)
// - method, uri, status
// - user_id (from JWT claims)
// - tool_name (extracted from route path)
// - duration_ms
//
// All child spans (OODA phases, DB queries, Redis ops) automatically
// inherit this context through OpenTelemetry's parent-child relationship.

use axum::{
    extract::Request,
    middleware::Next,
    response::Response,
};
use std::time::Instant;

use super::correlation::CorrelationId;

/// Middleware that creates an OTel span for each HTTP request with full context.
pub async fn request_trace_middleware(mut request: Request, next: Next) -> Response {
    let start = Instant::now();
    let method = request.method().clone();
    let uri = request.uri().path().to_string();

    // Extract or generate correlation ID
    let correlation = CorrelationId::from_request(&request);
    request.extensions_mut().insert(correlation.clone());

    // Extract tool name from URI pattern (e.g., /api/v1/tools/credit-scores → credit-scores)
    let tool_name = extract_tool_name(&uri);

    // Extract user ID from JWT claims (if available — set by auth middleware downstream)
    // We'll record it after the response comes back if auth added it

    let span = tracing::info_span!(
        "http_request",
        request_id = %correlation.0,
        method = %method,
        uri = %uri,
        tool_name = %tool_name,
        user_id = tracing::field::Empty,
        status = tracing::field::Empty,
        duration_ms = tracing::field::Empty,
    );

    let _guard = span.enter();
    let response = next.run(request).await;

    let duration_ms = start.elapsed().as_millis() as u64;
    let status = response.status().as_u16();

    span.record("status", &status);
    span.record("duration_ms", &duration_ms);

    if response.status().is_server_error() {
        tracing::error!(
            status = status,
            duration_ms = duration_ms,
            "Request failed with server error"
        );
    } else if response.status().is_client_error() {
        tracing::warn!(
            status = status,
            duration_ms = duration_ms,
            "Request completed with client error"
        );
    } else {
        tracing::info!(
            status = status,
            duration_ms = duration_ms,
            "Request completed"
        );
    }

    response
}

/// Extract tool name from URI path.
/// /api/v1/tools/credit-scores → "credit-scores"
/// /api/v1/superagent/status → "superagent/status"
/// /api/v1/sync/anonymized → "sync"
/// /graphql → "graphql"
/// /health → "health"
fn extract_tool_name(uri: &str) -> String {
    let parts: Vec<&str> = uri.trim_matches('/').split('/').collect();
    match parts.as_slice() {
        ["api", "v1", "tools", name, ..] => name.to_string(),
        ["api", "v1", "superagent", name, ..] => format!("superagent/{}", name),
        ["api", "v1", "sync", ..] => "sync".to_string(),
        ["api", "v1", "billing", name, ..] => format!("billing/{}", name),
        ["graphql", ..] => "graphql".to_string(),
        ["health", ..] => "health".to_string(),
        _ => uri.to_string(),
    }
}
