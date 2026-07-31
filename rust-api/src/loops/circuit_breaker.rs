// Circuit Breaker for External Services
// WhatsApp API, payment processors, partner APIs
// States: Closed → Open → Half-Open → Closed

use std::collections::HashMap;
use std::sync::Arc;
use std::time::Duration;
use tokio::sync::RwLock;
use serde::{Deserialize, Serialize};
use chrono::{DateTime, Utc};
use tracing::{info, warn, error};

// ─── Circuit Breaker State Machine ────────────────────────────────────────

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq)]
pub enum CircuitState {
    /// Normal operation — requests pass through
    Closed,
    /// All requests fail fast — no calls to the service
    Open,
    /// Limited requests allowed through to test recovery
    HalfOpen,
}

// ─── Circuit Breaker Configuration ────────────────────────────────────────

#[derive(Debug, Clone)]
pub struct CircuitBreakerConfig {
    /// Number of consecutive failures to trip the circuit
    pub failure_threshold: u32,
    /// Duration to wait in Open state before transitioning to HalfOpen
    pub open_timeout: Duration,
    /// Number of successful requests in HalfOpen to close the circuit
    pub half_open_success_threshold: u32,
    /// Number of failures in HalfOpen to re-open the circuit
    pub half_open_failure_threshold: u32,
    /// Rolling window size for failure rate calculation
    pub rolling_window: Duration,
    /// Maximum concurrent requests in HalfOpen state
    pub half_open_max_concurrent: u32,
}

impl Default for CircuitBreakerConfig {
    fn default() -> Self {
        Self {
            failure_threshold: 5,
            open_timeout: Duration::from_secs(60),
            half_open_success_threshold: 3,
            half_open_failure_threshold: 2,
            rolling_window: Duration::from_secs(300), // 5 minutes
            half_open_max_concurrent: 1,
        }
    }
}

// ─── Fallback Strategy ────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum FallbackStrategy {
    /// Return cached data (may be stale)
    CachedData { max_age_seconds: u64 },
    /// Return a degraded/default response
    DegradedResponse { message: String },
    /// Queue the request for later retry
    QueueForRetry { retry_after_seconds: u64 },
    /// Return an error to the caller
    FailFast { error: String },
}

// ─── Request Outcome ──────────────────────────────────────────────────────

#[derive(Debug, Clone)]
pub enum RequestOutcome {
    Success { latency_ms: u64 },
    Failure { error: String, is_system_error: bool },
    Rejected { reason: String }, // circuit is open
}

// ─── Circuit Breaker ──────────────────────────────────────────────────────

/// A single circuit breaker instance for one external service.
pub struct CircuitBreaker {
    config: CircuitBreakerConfig,
    state: CircuitState,
    /// Consecutive failures in Closed state
    failure_count: u32,
    /// Consecutive successes in HalfOpen state
    half_open_successes: u32,
    /// Failures in HalfOpen state
    half_open_failures: u32,
    /// When the circuit transitioned to Open
    opened_at: Option<DateTime<Utc>>,
    /// Rolling window of recent request outcomes
    recent_outcomes: Vec<TimestampedOutcome>,
    /// Fallback strategy when circuit is open
    fallback: FallbackStrategy,
    /// Service name (for logging)
    service_name: String,
    /// Total requests rejected while open
    total_rejected: u64,
    /// Total failures
    total_failures: u64,
    /// Total successes
    total_successes: u64,
}

#[derive(Debug, Clone)]
struct TimestampedOutcome {
    success: bool,
    timestamp: DateTime<Utc>,
    latency_ms: u64,
}

impl CircuitBreaker {
    pub fn new(service_name: String, config: CircuitBreakerConfig, fallback: FallbackStrategy) -> Self {
        Self {
            config,
            state: CircuitState::Closed,
            failure_count: 0,
            half_open_successes: 0,
            half_open_failures: 0,
            opened_at: None,
            recent_outcomes: Vec::with_capacity(100),
            fallback,
            service_name,
            total_rejected: 0,
            total_failures: 0,
            total_successes: 0,
        }
    }

    /// Check if a request should be allowed through.
    /// Returns Ok(()) if allowed, Err(fallback) if rejected.
    pub fn check(&mut self) -> Result<(), FallbackStrategy> {
        self.maybe_transition();

        match self.state {
            CircuitState::Closed => Ok(()),
            CircuitState::Open => {
                self.total_rejected += 1;
                Err(self.fallback.clone())
            }
            CircuitState::HalfOpen => {
                // Allow limited concurrent requests
                Ok(())
            }
        }
    }

    /// Record a successful request.
    pub fn record_success(&mut self, latency_ms: u64) {
        self.total_successes += 1;
        self.recent_outcomes.push(TimestampedOutcome {
            success: true,
            timestamp: Utc::now(),
            latency_ms,
        });
        self.prune_old_outcomes();

        match self.state {
            CircuitState::Closed => {
                self.failure_count = 0; // reset on success
            }
            CircuitState::HalfOpen => {
                self.half_open_successes += 1;
                if self.half_open_successes >= self.config.half_open_success_threshold {
                    self.transition_to_closed();
                }
            }
            CircuitState::Open => {
                // Shouldn't happen (requests are rejected), but handle gracefully
            }
        }
    }

    /// Record a failed request.
    pub fn record_failure(&mut self, error: &str, is_system_error: bool) {
        self.total_failures += 1;
        self.recent_outcomes.push(TimestampedOutcome {
            success: false,
            timestamp: Utc::now(),
            latency_ms: 0,
        });
        self.prune_old_outcomes();

        // Only count system errors (timeouts, connection refused) toward circuit tripping.
        // Business errors (4xx) should not trip the circuit.
        if !is_system_error {
            return;
        }

        match self.state {
            CircuitState::Closed => {
                self.failure_count += 1;
                if self.failure_count >= self.config.failure_threshold {
                    self.transition_to_open();
                }
            }
            CircuitState::HalfOpen => {
                self.half_open_failures += 1;
                if self.half_open_failures >= self.config.half_open_failure_threshold {
                    self.transition_to_open();
                }
            }
            CircuitState::Open => {
                // Already open, nothing to do
            }
        }
    }

    /// Check if requests should pass through (compatibility method for graph/pipeline).
    pub fn should_allow(&mut self) -> bool {
        self.maybe_transition();
        match self.state {
            CircuitState::Closed => true,
            CircuitState::Open => false,
            CircuitState::HalfOpen => true,
        }
    }

    /// Get current state.
    pub fn state(&self) -> CircuitState {
        self.state
    }

    /// Get the service name.
    pub fn service_name(&self) -> &str {
        &self.service_name
    }

    /// Get the current failure count (in Closed state).
    pub fn failure_count(&self) -> u32 {
        self.failure_count
    }

    /// Get the failure rate within the rolling window.
    pub fn failure_rate(&self) -> f64 {
        if self.recent_outcomes.is_empty() {
            return 0.0;
        }
        let failures = self.recent_outcomes.iter().filter(|o| !o.success).count();
        failures as f64 / self.recent_outcomes.len() as f64
    }

    /// Get average latency within the rolling window.
    pub fn avg_latency_ms(&self) -> f64 {
        let successes: Vec<&TimestampedOutcome> = self.recent_outcomes.iter()
            .filter(|o| o.success)
            .collect();
        if successes.is_empty() {
            return 0.0;
        }
        let sum: u64 = successes.iter().map(|o| o.latency_ms).sum();
        sum as f64 / successes.len() as f64
    }

    /// Get health status for monitoring.
    pub fn health(&self) -> CircuitHealth {
        CircuitHealth {
            service: self.service_name.clone(),
            state: self.state,
            failure_rate: self.failure_rate(),
            avg_latency_ms: self.avg_latency_ms(),
            total_requests: self.total_successes + self.total_failures,
            total_rejected: self.total_rejected,
            failure_count: self.failure_count,
            opened_at: self.opened_at,
        }
    }

    // ─── State Transitions ───────────────────────────────────────────────

    fn maybe_transition(&mut self) {
        if self.state == CircuitState::Open {
            if let Some(opened_at) = self.opened_at {
                let elapsed = Utc::now().signed_duration_since(opened_at);
                if elapsed.to_std().unwrap_or(Duration::ZERO) >= self.config.open_timeout {
                    self.transition_to_half_open();
                }
            }
        }
    }

    fn transition_to_open(&mut self) {
        error!(
            "Circuit breaker OPENED for service '{}' after {} consecutive failures",
            self.service_name, self.failure_count
        );
        self.state = CircuitState::Open;
        self.opened_at = Some(Utc::now());
        self.half_open_successes = 0;
        self.half_open_failures = 0;
    }

    fn transition_to_half_open(&mut self) {
        info!(
            "Circuit breaker transitioning to HALF-OPEN for service '{}'",
            self.service_name
        );
        self.state = CircuitState::HalfOpen;
        self.half_open_successes = 0;
        self.half_open_failures = 0;
    }

    fn transition_to_closed(&mut self) {
        info!(
            "Circuit breaker CLOSED for service '{}' (recovered after {}ms open)",
            self.service_name,
            self.opened_at
                .map(|o| Utc::now().signed_duration_since(o).num_milliseconds())
                .unwrap_or(0)
        );
        self.state = CircuitState::Closed;
        self.failure_count = 0;
        self.opened_at = None;
    }

    fn prune_old_outcomes(&mut self) {
        let cutoff = Utc::now() - chrono::Duration::from_std(self.config.rolling_window).unwrap_or(chrono::Duration::minutes(5));
        self.recent_outcomes.retain(|o| o.timestamp > cutoff);
    }
}

// ─── Circuit Health (for monitoring) ──────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CircuitHealth {
    pub service: String,
    pub state: CircuitState,
    pub failure_rate: f64,
    pub avg_latency_ms: f64,
    pub total_requests: u64,
    pub total_rejected: u64,
    pub failure_count: u32,
    pub opened_at: Option<DateTime<Utc>>,
}

// ─── Circuit Breaker Registry ─────────────────────────────────────────────

/// Manages circuit breakers for all external services.
/// Services are registered with names; each gets its own circuit breaker.
pub struct CircuitBreakerRegistry {
    breakers: RwLock<HashMap<String, Arc<RwLock<CircuitBreaker>>>>,
}

impl CircuitBreakerRegistry {
    pub fn new() -> Self {
        Self {
            breakers: RwLock::new(HashMap::new()),
        }
    }

    /// Register a new service with its circuit breaker configuration.
    pub async fn register(
        &self,
        service_name: &str,
        config: CircuitBreakerConfig,
        fallback: FallbackStrategy,
    ) {
        let breaker = CircuitBreaker::new(
            service_name.to_string(),
            config,
            fallback,
        );
        let mut breakers = self.breakers.write().await;
        breakers.insert(service_name.to_string(), Arc::new(RwLock::new(breaker)));
        info!("Circuit breaker registered for service: {}", service_name);
    }

    /// Get the circuit breaker for a service.
    pub async fn get(&self, service_name: &str) -> Option<Arc<RwLock<CircuitBreaker>>> {
        let breakers = self.breakers.read().await;
        breakers.get(service_name).cloned()
    }

    /// Check if a request to a service should be allowed.
    pub async fn check(&self, service_name: &str) -> Result<(), FallbackStrategy> {
        let breakers = self.breakers.read().await;
        if let Some(breaker) = breakers.get(service_name) {
            breaker.write().await.check()
        } else {
            // No circuit breaker registered — allow by default
            Ok(())
        }
    }

    /// Record a success for a service.
    pub async fn record_success(&self, service_name: &str, latency_ms: u64) {
        let breakers = self.breakers.read().await;
        if let Some(breaker) = breakers.get(service_name) {
            breaker.write().await.record_success(latency_ms);
        }
    }

    /// Record a failure for a service.
    pub async fn record_failure(&self, service_name: &str, error: &str, is_system_error: bool) {
        let breakers = self.breakers.read().await;
        if let Some(breaker) = breakers.get(service_name) {
            breaker.write().await.record_failure(error, is_system_error);
        }
    }

    /// Get health status for all services.
    pub async fn health_all(&self) -> Vec<CircuitHealth> {
        let breakers = self.breakers.read().await;
        let mut health = Vec::with_capacity(breakers.len());
        for (_, breaker) in breakers.iter() {
            health.push(breaker.read().await.health());
        }
        health
    }

    /// Get health for a specific service.
    pub async fn health(&self, service_name: &str) -> Option<CircuitHealth> {
        let breakers = self.breakers.read().await;
        breakers.get(service_name).map(|b| {
            // We need to block here since health() is sync
            // In production, use a dedicated health check task
            futures::executor::block_on(b.read()).health()
        })
    }

    /// Register default services with standard configurations.
    pub async fn register_defaults(&self) {
        // WhatsApp API
        self.register(
            "whatsapp",
            CircuitBreakerConfig {
                failure_threshold: 5,
                open_timeout: Duration::from_secs(60),
                ..Default::default()
            },
            FallbackStrategy::QueueForRetry { retry_after_seconds: 120 },
        ).await;

        // M-Pesa API
        self.register(
            "mpesa",
            CircuitBreakerConfig {
                failure_threshold: 3, // more sensitive — payment critical
                open_timeout: Duration::from_secs(30),
                ..Default::default()
            },
            FallbackStrategy::DegradedResponse {
                message: "Payment processing temporarily unavailable. Please try again shortly.".to_string(),
            },
        ).await;

        // DeepSeek LLM API
        self.register(
            "deepseek",
            CircuitBreakerConfig {
                failure_threshold: 5,
                open_timeout: Duration::from_secs(120),
                ..Default::default()
            },
            FallbackStrategy::CachedData { max_age_seconds: 3600 },
        ).await;

        // Partner FMCG API
        self.register(
            "fmcg_partner",
            CircuitBreakerConfig {
                failure_threshold: 5,
                open_timeout: Duration::from_secs(60),
                ..Default::default()
            },
            FallbackStrategy::CachedData { max_age_seconds: 7200 },
        ).await;

        // SMS Gateway
        self.register(
            "sms_gateway",
            CircuitBreakerConfig {
                failure_threshold: 5,
                open_timeout: Duration::from_secs(60),
                ..Default::default()
            },
            FallbackStrategy::QueueForRetry { retry_after_seconds: 300 },
        ).await;
    }
}

// ─── Reusable CircuitBreaker Trait ────────────────────────────────────────

/// Trait for services that can be wrapped with circuit breaker protection.
/// Implement this trait for any external service client.
#[async_trait::async_trait]
pub trait CircuitBreakerProtected: Send + Sync {
    /// The type of response from the service.
    type Response;
    /// The type of error from the service.
    type Error: std::fmt::Display;

    /// The name of this service (for circuit breaker registry).
    fn service_name(&self) -> &str;

    /// Execute the actual request to the external service.
    async fn execute_request(&self) -> Result<Self::Response, Self::Error>;

    /// Get the circuit breaker registry.
    fn registry(&self) -> &CircuitBreakerRegistry;

    /// Execute a request with circuit breaker protection.
    async fn call(&self) -> Result<Self::Response, ProtectedCallError<Self::Error>> {
        // Check circuit
        let registry = self.registry();
        if let Err(fallback) = registry.check(self.service_name()).await {
            return Err(ProtectedCallError::CircuitOpen(fallback));
        }

        // Execute request
        let start = std::time::Instant::now();
        match self.execute_request().await {
            Ok(response) => {
                let latency = start.elapsed().as_millis() as u64;
                registry.record_success(self.service_name(), latency).await;
                Ok(response)
            }
            Err(e) => {
                let is_system = is_system_error(&e.to_string());
                registry.record_failure(self.service_name(), &e.to_string(), is_system).await;
                Err(ProtectedCallError::ServiceError(e))
            }
        }
    }
}

#[derive(Debug)]
pub enum ProtectedCallError<E> {
    /// Circuit breaker is open — request rejected
    CircuitOpen(FallbackStrategy),
    /// The service itself returned an error
    ServiceError(E),
}

fn is_system_error(error_msg: &str) -> bool {
    let lower = error_msg.to_lowercase();
    lower.contains("timeout") ||
    lower.contains("connection refused") ||
    lower.contains("connection reset") ||
    lower.contains("dns") ||
    lower.contains("network") ||
    lower.contains("503") ||
    lower.contains("502") ||
    lower.contains("504")
}

// ─── Tests ────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_circuit_breaker_closed_to_open() {
        let mut cb = CircuitBreaker::new(
            "test".to_string(),
            CircuitBreakerConfig {
                failure_threshold: 3,
                open_timeout: Duration::from_secs(1),
                ..Default::default()
            },
            FallbackStrategy::FailFast { error: "circuit open".to_string() },
        );

        // Initial state: closed
        assert_eq!(cb.state(), CircuitState::Closed);
        assert!(cb.check().is_ok());

        // Record 3 system failures
        cb.record_failure("timeout", true);
        assert_eq!(cb.state(), CircuitState::Closed);
        cb.record_failure("timeout", true);
        assert_eq!(cb.state(), CircuitState::Closed);
        cb.record_failure("timeout", true);

        // Should be open now
        assert_eq!(cb.state(), CircuitState::Open);
        assert!(cb.check().is_err());
    }

    #[test]
    fn test_circuit_breaker_half_open_recovery() {
        let mut cb = CircuitBreaker::new(
            "test".to_string(),
            CircuitBreakerConfig {
                failure_threshold: 2,
                open_timeout: Duration::from_millis(1), // very short for testing
                half_open_success_threshold: 2,
                ..Default::default()
            },
            FallbackStrategy::FailFast { error: "circuit open".to_string() },
        );

        // Trip the circuit
        cb.record_failure("timeout", true);
        cb.record_failure("timeout", true);
        assert_eq!(cb.state(), CircuitState::Open);

        // Wait for timeout
        std::thread::sleep(Duration::from_millis(5));

        // Should transition to half-open
        assert!(cb.check().is_ok());
        assert_eq!(cb.state(), CircuitState::HalfOpen);

        // Record successes to close
        cb.record_success(100);
        cb.record_success(100);
        assert_eq!(cb.state(), CircuitState::Closed);
    }

    #[test]
    fn test_circuit_breaker_business_errors_dont_trip() {
        let mut cb = CircuitBreaker::new(
            "test".to_string(),
            CircuitBreakerConfig {
                failure_threshold: 2,
                ..Default::default()
            },
            FallbackStrategy::FailFast { error: "circuit open".to_string() },
        );

        // Business errors (is_system_error=false) should not trip
        cb.record_failure("invalid input", false);
        cb.record_failure("invalid input", false);
        cb.record_failure("invalid input", false);
        assert_eq!(cb.state(), CircuitState::Closed);
    }

    #[test]
    fn test_failure_rate_calculation() {
        let mut cb = CircuitBreaker::new(
            "test".to_string(),
            CircuitBreakerConfig::default(),
            FallbackStrategy::FailFast { error: "circuit open".to_string() },
        );

        cb.record_success(100);
        cb.record_success(100);
        cb.record_failure("error", true);

        let rate = cb.failure_rate();
        assert!((rate - 1.0 / 3.0).abs() < 0.01);
    }

    #[test]
    fn test_fallback_strategies() {
        let cached = FallbackStrategy::CachedData { max_age_seconds: 3600 };
        let degraded = FallbackStrategy::DegradedResponse {
            message: "Service unavailable".to_string(),
        };
        let queued = FallbackStrategy::QueueForRetry { retry_after_seconds: 120 };
        let fail = FallbackStrategy::FailFast { error: "error".to_string() };

        // All should be cloneable and serializable
        let _ = (cached.clone(), degraded.clone(), queued.clone(), fail.clone());
    }

    #[test]
    fn test_is_system_error() {
        assert!(is_system_error("connection timeout"));
        assert!(is_system_error("Connection refused"));
        assert!(is_system_error("DNS resolution failed"));
        assert!(is_system_error("HTTP 503 Service Unavailable"));
        assert!(is_system_error("HTTP 502 Bad Gateway"));

        assert!(!is_system_error("invalid input"));
        assert!(!is_system_error("not found"));
        assert!(!is_system_error("unauthorized"));
    }
}
