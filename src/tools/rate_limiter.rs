use std::collections::HashMap;
use std::time::{Duration, Instant};

pub struct RateLimiter {
    limits: HashMap<String, (u32, Duration)>,
    requests: HashMap<String, Vec<Instant>>,
}

impl RateLimiter {
    pub fn new() -> Self {
        let mut limits = HashMap::new();
        limits.insert("/auth".to_string(), (5, Duration::from_secs(900))); // 5 per 15min
        limits.insert("/sync".to_string(), (100, Duration::from_secs(3600))); // 100 per hour
        limits.insert("/reports".to_string(), (200, Duration::from_secs(3600))); // 200 per hour
        limits.insert("/intelligence".to_string(), (50, Duration::from_secs(3600))); // 50 per hour
        Self { limits, requests: HashMap::new() }
    }

    pub fn check(&mut self, endpoint: &str, client_id: &str) -> bool {
        let key = format!("{}:{}", endpoint, client_id);
        let (max_requests, window) = match self.limits.get(endpoint) {
            Some(l) => *l,
            None => return true, // No limit configured
        };
        let now = Instant::now();
        let requests = self.requests.entry(key).or_insert_with(Vec::new);
        requests.retain(|r| now.duration_since(*r) < window);
        if requests.len() >= max_requests as usize {
            false
        } else {
            requests.push(now);
            true
        }
    }

    pub fn retry_after(&self, endpoint: &str, client_id: &str) -> Option<Duration> {
        let key = format!("{}:{}", endpoint, client_id);
        let (_, window) = self.limits.get(endpoint)?;
        let requests = self.requests.get(&key)?;
        requests.first().map(|r| window.checked_sub(r.elapsed()).unwrap_or_default())
    }
}
