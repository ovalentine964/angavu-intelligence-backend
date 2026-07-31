// src/gateway/rate_limit.rs

use axum::{
    extract::Request,
    http::StatusCode,
    middleware::Next,
    response::Response,
};
use dashmap::DashMap;
use std::sync::Arc;
use std::time::{Duration, Instant};

/// Token-bucket rate limiter per buyer (used by authenticated routes)
pub struct RateLimiter {
    /// Per-key token buckets
    buckets: Arc<DashMap<String, TokenBucket>>,
    /// Default requests per minute for unknown keys
    default_rpm: u32,
}

/// S15: Per-IP rate limiter for unauthenticated endpoints (webhooks, approvals)
pub struct IpRateLimiter {
    buckets: Arc<DashMap<String, TokenBucket>>,
    rpm: u32,
}

impl IpRateLimiter {
    pub fn new(rpm: u32) -> Self {
        Self {
            buckets: Arc::new(DashMap::new()),
            rpm,
        }
    }

    /// Check if a request from this IP is allowed.
    pub fn check(&self, ip: &str) -> Result<u32, Duration> {
        let mut bucket = self.buckets
            .entry(ip.to_string())
            .or_insert_with(|| {
                TokenBucket::new(self.rpm as f64, self.rpm as f64 / 60.0)
            });

        if bucket.try_consume() {
            Ok(bucket.tokens as u32)
        } else {
            Err(bucket.retry_after())
        }
    }
}

struct TokenBucket {
    tokens: f64,
    max_tokens: f64,
    refill_rate: f64, // tokens per second
    last_refill: Instant,
}

impl TokenBucket {
    fn new(max_tokens: f64, refill_rate: f64) -> Self {
        Self {
            tokens: max_tokens,
            max_tokens,
            refill_rate,
            last_refill: Instant::now(),
        }
    }

    fn try_consume(&mut self) -> bool {
        self.refill();
        if self.tokens >= 1.0 {
            self.tokens -= 1.0;
            true
        } else {
            false
        }
    }

    fn refill(&mut self) {
        let now = Instant::now();
        let elapsed = now.duration_since(self.last_refill).as_secs_f64();
        self.tokens = (self.tokens + elapsed * self.refill_rate).min(self.max_tokens);
        self.last_refill = now;
    }

    fn retry_after(&self) -> Duration {
        if self.tokens >= 1.0 {
            Duration::ZERO
        } else {
            Duration::from_secs_f64((1.0 - self.tokens) / self.refill_rate)
        }
    }
}

impl RateLimiter {
    pub fn new(default_rpm: u32) -> Self {
        Self {
            buckets: Arc::new(DashMap::new()),
            default_rpm,
        }
    }

    /// Check if a request is allowed. Returns Ok(remaining) or Err(retry_after).
    pub fn check(&self, key_id: &str, tier_rpm: u32) -> Result<u32, Duration> {
        let mut bucket = self.buckets
            .entry(key_id.to_string())
            .or_insert_with(|| {
                let rpm = tier_rpm.max(self.default_rpm) as f64;
                TokenBucket::new(rpm, rpm / 60.0)
            });

        if bucket.try_consume() {
            Ok(bucket.tokens as u32)
        } else {
            Err(bucket.retry_after())
        }
    }
}

/// Rate limiting middleware
pub async fn rate_limit_middleware(
    State(state): State<super::GatewayState>,
    request: Request,
    next: Next,
) -> Result<Response, StatusCode> {
    // Extract claims from auth middleware
    let claims = request
        .extensions()
        .get::<super::auth::Claims>()
        .cloned()
        .ok_or(StatusCode::UNAUTHORIZED)?;

    let rpm = claims.tier.rate_limit_per_minute();

    match state.rate_limiter.check(&claims.key_id, rpm) {
        Ok(remaining) => {
            let mut response = next.run(request).await;
            if let Ok(val) = remaining.to_string().parse() {
                response.headers_mut().insert(
                    "X-RateLimit-Remaining",
                    val,
                );
            }
            Ok(response)
        }
        Err(retry_after) => {
            let mut response = Response::new(axum::body::Body::empty());
            *response.status_mut() = StatusCode::TOO_MANY_REQUESTS;
            if let Ok(val) = retry_after.as_secs().to_string().parse() {
                response.headers_mut().insert(
                    "Retry-After",
                    val,
                );
            }
            Ok(response)
        }
    }
}
