use axum::{
    extract::Request,
    http::HeaderValue,
    middleware::Next,
    response::Response,
};
use uuid::Uuid;

/// Middleware that attaches a unique request ID to every request/response.
/// - If the client sends `X-Request-ID`, it is reused.
/// - Otherwise, a new UUID v4 is generated.
/// The ID is added to response headers and request extensions.
pub async fn request_id_middleware(
    mut request: Request,
    next: Next,
) -> Response {
    let request_id = request
        .headers()
        .get("X-Request-ID")
        .and_then(|v| v.to_str().ok())
        .filter(|s| !s.is_empty())
        .map(|s| s.to_string())
        .unwrap_or_else(|| Uuid::new_v4().to_string());

    // Store in extensions for downstream handlers
    request.extensions_mut().insert(RequestId(request_id.clone()));

    let mut response = next.run(request).await;

    // Add to response headers
    if let Ok(val) = HeaderValue::from_str(&request_id) {
        response.headers_mut().insert("X-Request-ID", val);
    }

    response
}

/// Request ID extractor for use in handlers.
#[derive(Debug, Clone)]
pub struct RequestId(pub String);

impl std::fmt::Display for RequestId {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.0)
    }
}

/// Build the request ID middleware layer.
pub fn request_id_layer() -> axum::middleware::FromFnLayer<
    impl Fn(
        Request,
        Next,
    ) -> std::pin::Pin<
        Box<dyn std::future::Future<Output = Response> + Send>,
    > + Clone + Send + 'static,
> {
    axum::middleware::from_fn(request_id_middleware)
}
