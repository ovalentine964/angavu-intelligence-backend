use axum::{
    extract::ConnectInfo,
    http::StatusCode,
    middleware::Next,
    response::{IntoResponse, Response},
    extract::Request,
};
use std::collections::HashMap;
use std::net::SocketAddr;
use std::sync::Arc;
use tokio::sync::RwLock;
use chrono::Utc;

/// Simple in-memory rate limiter using a sliding window per IP.
/// For production, replace with Redis-backed rate limiting.

#[derive(Debug, Clone)]
struct RateLimitEntry {
    /// Timestamps of requests in the current window
    requests: Vec<i64>,
}

#[derive(Debug, Clone)]
pub struct RateLimiter {
    /// Map of IP address -> rate limit entry
    entries: Arc<RwLock<HashMap<String, RateLimitEntry>>>,
    /// Maximum requests per window
    max_requests: u64,
    /// Window duration in seconds
    window_secs: i64,
}

impl RateLimiter {
    pub fn new(max_requests: u64, window_secs: u64) -> Self {
        Self {
            entries: Arc::new(RwLock::new(HashMap::new())),
            max_requests,
            window_secs: window_secs as i64,
        }
    }

    /// Check if a request from the given IP is allowed.
    /// Returns (allowed: bool, remaining: u64, reset_at: i64).
    async fn check(&self, ip: &str) -> (bool, u64, i64) {
        let now = Utc::now().timestamp();
        let window_start = now - self.window_secs;

        let mut entries = self.entries.write().await;
        let entry = entries
            .entry(ip.to_string())
            .or_insert_with(|| RateLimitEntry { requests: Vec::new() });

        // Remove expired entries
        entry.requests.retain(|&ts| ts > window_start);

        let count = entry.requests.len() as u64;
        let remaining = self.max_requests.saturating_sub(count);
        let reset_at = now + self.window_secs;

        if count >= self.max_requests {
            (false, 0, reset_at)
        } else {
            entry.requests.push(now);
            (true, remaining - 1, reset_at)
        }
    }
}

/// Axum middleware for rate limiting by client IP.
pub async fn rate_limit_middleware(
    ConnectInfo(addr): ConnectInfo<SocketAddr>,
    request: Request,
    next: Next,
) -> Response {
    // Get rate limiter from extensions
    let limiter = request
        .extensions()
        .get::<RateLimiter>()
        .cloned();

    let Some(limiter) = limiter else {
        return next.run(request).await;
    };

    let ip = addr.ip().to_string();
    let (allowed, remaining, reset_at) = limiter.check(&ip).await;

    let mut response = if allowed {
        next.run(request).await
    } else {
        (
            StatusCode::TOO_MANY_REQUESTS,
            axum::Json(serde_json::json!({
                "status": 429,
                "error": "rate_limit_exceeded",
                "message": "Too many requests. Please try again later.",
                "retry_after": reset_at - Utc::now().timestamp()
            })),
        )
            .into_response()
    };

    // Add rate limit headers
    let headers = response.headers_mut();
    headers.insert("X-RateLimit-Remaining", remaining.to_string().parse().unwrap());
    headers.insert("X-RateLimit-Reset", reset_at.to_string().parse().unwrap());

    response
}

/// Build the rate limit layer as an axum middleware function.
pub fn rate_limit_layer(max_requests: u64, window_secs: u64) -> RateLimiter {
    RateLimiter::new(max_requests, window_secs)
}
