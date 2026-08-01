// src/gateway/security_headers.rs
//
// Security Headers Middleware
//
// Applies standard security headers to all responses:
// - HSTS
// - X-Content-Type-Options
// - X-Frame-Options
// - X-XSS-Protection
// - Content-Security-Policy
// - Referrer-Policy

use axum::{
    body::Body,
    http::{HeaderValue, Request, Response},
    middleware::Next,
};

/// Security headers middleware.
/// Injects hardened HTTP headers into every response.
pub async fn security_headers_middleware(
    request: Request<Body>,
    next: Next,
) -> Response<Body> {
    let mut response = next.run(request).await;

    let headers = response.headers_mut();

    // HSTS: Force HTTPS for 1 year, include subdomains
    headers.insert(
        "strict-transport-security",
        HeaderValue::from_static("max-age=31536000; includeSubDomains"),
    );

    // Prevent MIME type sniffing
    headers.insert(
        "x-content-type-options",
        HeaderValue::from_static("nosniff"),
    );

    // Prevent clickjacking — no framing allowed
    headers.insert(
        "x-frame-options",
        HeaderValue::from_static("DENY"),
    );

    // Legacy XSS filter (for older browsers)
    headers.insert(
        "x-xss-protection",
        HeaderValue::from_static("1; mode=block"),
    );

    // Content Security Policy — restrict to self-origin
    headers.insert(
        "content-security-policy",
        HeaderValue::from_static("default-src 'self'"),
    );

    // Referrer Policy — send origin only on cross-origin requests
    headers.insert(
        "referrer-policy",
        HeaderValue::from_static("strict-origin-when-cross-origin"),
    );

    // Permissions Policy — disable sensitive browser features
    headers.insert(
        "permissions-policy",
        HeaderValue::from_static("camera=(), microphone=(), geolocation=(), payment=()"),
    );

    response
}
