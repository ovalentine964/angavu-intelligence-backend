use axum::http::{header, Method};
use tower_http::cors::{CorsLayer, AllowOrigin, AllowHeaders, AllowMethods};

/// Build a CORS layer from allowed origins.
pub fn cors_layer(allowed_origins: &[String]) -> CorsLayer {
    let origins: Vec<_> = allowed_origins
        .iter()
        .map(|o| o.parse().unwrap())
        .collect();

    CorsLayer::new()
        .allow_origin(AllowOrigin::list(origins))
        .allow_methods(AllowMethods::list(vec![
            Method::GET,
            Method::POST,
            Method::PUT,
            Method::PATCH,
            Method::DELETE,
            Method::OPTIONS,
        ]))
        .allow_headers(AllowHeaders::list(vec![
            header::AUTHORIZATION,
            header::CONTENT_TYPE,
            header::ACCEPT,
            "X-Request-ID".parse().unwrap(),
        ]))
        .expose_headers(vec![
            "X-Request-ID".parse().unwrap(),
            "X-RateLimit-Remaining".parse().unwrap(),
            "X-RateLimit-Reset".parse().unwrap(),
        ])
        .max_age(std::time::Duration::from_secs(3600))
}
