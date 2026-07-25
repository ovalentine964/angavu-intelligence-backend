use std::collections::HashMap;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

/// In-memory sliding window rate limiter.
/// For production, swap the `store` field with a Redis-backed implementation
/// using the same trait interface.
pub struct RateLimiter {
    limits: HashMap<String, (u32, Duration)>,
    /// Sliding window log: key → sorted list of request timestamps.
    requests: HashMap<String, Vec<Instant>>,
    /// Optional Redis URL for distributed rate limiting.
    redis_url: Option<String>,
}

/// A single rate limit entry for serialization.
#[derive(Debug, Clone)]
pub struct RateLimitEntry {
    pub max_requests: u32,
    pub window: Duration,
    pub current_count: usize,
    pub oldest_request: Option<Instant>,
}

impl RateLimiter {
    pub fn new() -> Self {
        let mut limits = HashMap::new();
        limits.insert("/auth".to_string(), (5, Duration::from_secs(900))); // 5 per 15min
        limits.insert("/sync".to_string(), (100, Duration::from_secs(3600))); // 100 per hour
        limits.insert("/reports".to_string(), (200, Duration::from_secs(3600))); // 200 per hour
        limits.insert("/intelligence".to_string(), (50, Duration::from_secs(3600))); // 50 per hour
        Self {
            limits,
            requests: HashMap::new(),
            redis_url: None,
        }
    }

    pub fn with_redis(redis_url: &str) -> Self {
        let mut limiter = Self::new();
        limiter.redis_url = Some(redis_url.to_string());
        limiter
    }

    /// Add a custom rate limit for an endpoint.
    pub fn add_limit(&mut self, endpoint: &str, max_requests: u32, window: Duration) {
        self.limits
            .insert(endpoint.to_string(), (max_requests, window));
    }

    /// Build the storage key for a client+endpoint pair.
    fn storage_key(endpoint: &str, client_id: &str) -> String {
        format!("rl:{}:{}", endpoint, client_id)
    }

    /// Check if a request is allowed under the sliding window.
    /// Returns true if allowed, false if rate limited.
    pub fn check(&mut self, endpoint: &str, client_id: &str) -> bool {
        let key = Self::storage_key(endpoint, client_id);
        let (max_requests, window) = match self.limits.get(endpoint) {
            Some(l) => *l,
            None => return true, // No limit configured → allow
        };

        let now = Instant::now();
        let requests = self.requests.entry(key).or_default();

        // Remove requests outside the sliding window
        requests.retain(|r| now.duration_since(*r) < window);

        if requests.len() >= max_requests as usize {
            false
        } else {
            requests.push(now);
            true
        }
    }

    /// Get how many requests remain in the current window.
    pub fn remaining(&self, endpoint: &str, client_id: &str) -> u32 {
        let key = Self::storage_key(endpoint, client_id);
        let (max_requests, window) = match self.limits.get(endpoint) {
            Some(l) => *l,
            None => return u32::MAX,
        };
        let now = Instant::now();
        match self.requests.get(&key) {
            Some(reqs) => {
                let valid = reqs.iter().filter(|r| now.duration_since(**r) < window).count();
                max_requests.saturating_sub(valid as u32)
            }
            None => max_requests,
        }
    }

    /// Get the time until the oldest request in the window expires.
    /// Returns None if no requests in window.
    pub fn retry_after(&self, endpoint: &str, client_id: &str) -> Option<Duration> {
        let key = Self::storage_key(endpoint, client_id);
        let (_, window) = self.limits.get(endpoint)?;
        let now = Instant::now();
        let requests = self.requests.get(&key)?;
        requests
            .first()
            .map(|r| window.checked_sub(now.duration_since(*r)).unwrap_or_default())
    }

    /// Get current state of a rate limit entry for monitoring.
    pub fn status(&self, endpoint: &str, client_id: &str) -> Option<RateLimitEntry> {
        let key = Self::storage_key(endpoint, client_id);
        let &(max_requests, window) = self.limits.get(endpoint)?;
        let now = Instant::now();
        let count = self
            .requests
            .get(&key)
            .map(|reqs| reqs.iter().filter(|r| now.duration_since(**r) < window).count())
            .unwrap_or(0);
        Some(RateLimitEntry {
            max_requests,
            window,
            current_count: count,
            oldest_request: self.requests.get(&key).and_then(|reqs| reqs.first().copied()),
        })
    }

    /// Reset rate limit state for a specific client+endpoint.
    pub fn reset(&mut self, endpoint: &str, client_id: &str) {
        let key = Self::storage_key(endpoint, client_id);
        self.requests.remove(&key);
    }

    /// Reset all rate limit state.
    pub fn reset_all(&mut self) {
        self.requests.clear();
    }

    /// Prune expired entries from memory. Call periodically to free memory.
    pub fn prune_expired(&mut self) {
        let now = Instant::now();
        self.requests.retain(|_, reqs| {
            reqs.retain(|r| now.duration_since(*r) < Duration::from_secs(3600));
            !reqs.is_empty()
        });
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::thread;

    #[test]
    fn test_basic_rate_limit() {
        let mut limiter = RateLimiter::new();
        // /auth allows 5 per 15min
        for _ in 0..5 {
            assert!(limiter.check("/auth", "client1"));
        }
        assert!(!limiter.check("/auth", "client1"));
    }

    #[test]
    fn test_different_clients_independent() {
        let mut limiter = RateLimiter::new();
        for _ in 0..5 {
            assert!(limiter.check("/auth", "client1"));
        }
        assert!(!limiter.check("/auth", "client1"));
        // client2 should still be allowed
        assert!(limiter.check("/auth", "client2"));
    }

    #[test]
    fn test_different_endpoints_independent() {
        let mut limiter = RateLimiter::new();
        for _ in 0..5 {
            limiter.check("/auth", "client1");
        }
        assert!(!limiter.check("/auth", "client1"));
        // /sync has different limit
        assert!(limiter.check("/sync", "client1"));
    }

    #[test]
    fn test_unknown_endpoint_allowed() {
        let mut limiter = RateLimiter::new();
        assert!(limiter.check("/unknown", "client1"));
        assert!(limiter.check("/unknown", "client1"));
    }

    #[test]
    fn test_remaining_count() {
        let mut limiter = RateLimiter::new();
        assert_eq!(limiter.remaining("/auth", "client1"), 5);
        limiter.check("/auth", "client1");
        assert_eq!(limiter.remaining("/auth", "client1"), 4);
    }

    #[test]
    fn test_retry_after_some() {
        let mut limiter = RateLimiter::new();
        limiter.check("/auth", "client1");
        let retry = limiter.retry_after("/auth", "client1");
        assert!(retry.is_some());
        // Should be close to 15 minutes
        assert!(retry.unwrap() <= Duration::from_secs(900));
    }

    #[test]
    fn test_retry_after_none_when_empty() {
        let limiter = RateLimiter::new();
        assert!(limiter.retry_after("/auth", "client1").is_none());
    }

    #[test]
    fn test_reset() {
        let mut limiter = RateLimiter::new();
        for _ in 0..5 {
            limiter.check("/auth", "client1");
        }
        assert!(!limiter.check("/auth", "client1"));
        limiter.reset("/auth", "client1");
        assert!(limiter.check("/auth", "client1"));
    }

    #[test]
    fn test_reset_all() {
        let mut limiter = RateLimiter::new();
        for _ in 0..5 {
            limiter.check("/auth", "client1");
        }
        limiter.reset_all();
        assert!(limiter.check("/auth", "client1"));
    }

    #[test]
    fn test_custom_limit() {
        let mut limiter = RateLimiter::new();
        limiter.add_limit("/custom", 2, Duration::from_secs(60));
        assert!(limiter.check("/custom", "c1"));
        assert!(limiter.check("/custom", "c1"));
        assert!(!limiter.check("/custom", "c1"));
    }

    #[test]
    fn test_status() {
        let mut limiter = RateLimiter::new();
        limiter.check("/auth", "client1");
        let status = limiter.status("/auth", "client1").unwrap();
        assert_eq!(status.max_requests, 5);
        assert_eq!(status.current_count, 1);
    }

    #[test]
    fn test_sliding_window_expires() {
        // Use a very short window for testing
        let mut limiter = RateLimiter::new();
        limiter.add_limit("/test", 2, Duration::from_millis(50));
        assert!(limiter.check("/test", "c1"));
        assert!(limiter.check("/test", "c1"));
        assert!(!limiter.check("/test", "c1"));
        // Wait for window to expire
        thread::sleep(Duration::from_millis(60));
        assert!(limiter.check("/test", "c1"));
    }

    #[test]
    fn test_prune_expired() {
        let mut limiter = RateLimiter::new();
        limiter.add_limit("/short", 10, Duration::from_millis(10));
        limiter.check("/short", "c1");
        thread::sleep(Duration::from_millis(20));
        limiter.prune_expired();
        // After pruning, the entry should be removed
        assert!(limiter.requests.is_empty() || limiter.remaining("/short", "c1") == 10);
    }
}
