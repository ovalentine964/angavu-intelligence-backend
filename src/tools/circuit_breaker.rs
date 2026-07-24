//! CircuitBreaker — Prevent cascade failures
//!
//! Implements a three-state circuit breaker (Closed → Open → Half-Open)
//! to prevent cascading failures across database, Redis, ClickHouse,
//! and external API calls.

use anyhow::{anyhow, Result};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::RwLock;
use tracing::{debug, error, info, warn};

/// Circuit breaker state
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum CircuitState {
    /// Normal operation — requests flow through
    Closed,
    /// Failure threshold exceeded — requests are blocked
    Open,
    /// Testing if service recovered — limited requests allowed
    HalfOpen,
}

/// Configuration for the circuit breaker
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CircuitBreakerConfig {
    /// Number of failures before opening the circuit
    pub failure_threshold: u32,
    /// Number of successes in half-open state before closing
    pub success_threshold: u32,
    /// Duration in seconds to stay open before transitioning to half-open
    pub open_timeout_secs: u64,
    /// Window size for failure counting
    pub window_size_secs: u64,
    /// Maximum consecutive failures to track
    pub max_failures_tracked: usize,
}

impl Default for CircuitBreakerConfig {
    fn default() -> Self {
        Self {
            failure_threshold: 5,
            success_threshold: 3,
            open_timeout_secs: 30,
            window_size_secs: 60,
            max_failures_tracked: 100,
        }
    }
}

/// Per-service circuit breaker state
#[derive(Debug, Clone)]
struct ServiceCircuit {
    state: CircuitState,
    failure_count: u32,
    success_count: u32,
    last_failure_time: Option<DateTime<Utc>>,
    last_state_change: DateTime<Utc>,
    recent_failures: Vec<DateTime<Utc>>,
    total_requests: u64,
    total_failures: u64,
    total_rejected: u64,
}

impl ServiceCircuit {
    fn new() -> Self {
        Self {
            state: CircuitState::Closed,
            failure_count: 0,
            success_count: 0,
            last_failure_time: None,
            last_state_change: Utc::now(),
            recent_failures: Vec::new(),
            total_requests: 0,
            total_failures: 0,
            total_rejected: 0,
        }
    }
}

/// The CircuitBreaker tool
pub struct CircuitBreaker {
    config: CircuitBreakerConfig,
    circuits: Arc<RwLock<HashMap<String, ServiceCircuit>>>,
}

impl CircuitBreaker {
    pub fn new(config: CircuitBreakerConfig) -> Self {
        Self {
            config,
            circuits: Arc::new(RwLock::new(HashMap::new())),
        }
    }

    /// Check if the circuit is open (global check used by OODAOrchestrator)
    pub async fn is_open(&self) -> bool {
        let circuits = self.circuits.read().await;
        // If any critical service circuit is open, consider it open
        for (name, circuit) in circuits.iter() {
            if circuit.state == CircuitState::Open {
                warn!(service = %name, "Circuit breaker is open");
                return true;
            }
        }
        false
    }

    /// Check if a specific service circuit allows requests
    pub async fn is_allowed(&self, service: &str) -> bool {
        let mut circuits = self.circuits.write().await;
        let circuit = circuits
            .entry(service.to_string())
            .or_insert_with(ServiceCircuit::new);

        circuit.total_requests += 1;

        match circuit.state {
            CircuitState::Closed => true,
            CircuitState::Open => {
                // Check if open timeout has elapsed
                if let Some(last_change) = Some(circuit.last_state_change) {
                    let elapsed = Utc::now()
                        .signed_duration_since(last_change)
                        .num_seconds() as u64;
                    if elapsed >= self.config.open_timeout_secs {
                        // Transition to half-open
                        info!(service = %service, "Circuit transitioning from Open to HalfOpen");
                        circuit.state = CircuitState::HalfOpen;
                        circuit.success_count = 0;
                        circuit.last_state_change = Utc::now();
                        return true;
                    }
                }
                circuit.total_rejected += 1;
                false
            }
            CircuitState::HalfOpen => {
                // Allow limited requests in half-open state
                true
            }
        }
    }

    /// Record a successful call
    pub async fn record_success(&self) {
        // Global success — used by OODAOrchestrator
        debug!("Global circuit breaker: success recorded");
    }

    /// Record a success for a specific service
    pub async fn record_service_success(&self, service: &str) {
        let mut circuits = self.circuits.write().await;
        if let Some(circuit) = circuits.get_mut(service) {
            match circuit.state {
                CircuitState::HalfOpen => {
                    circuit.success_count += 1;
                    if circuit.success_count >= self.config.success_threshold {
                        info!(
                            service = %service,
                            successes = circuit.success_count,
                            "Circuit closing — service recovered"
                        );
                        circuit.state = CircuitState::Closed;
                        circuit.failure_count = 0;
                        circuit.success_count = 0;
                        circuit.last_state_change = Utc::now();
                    }
                }
                CircuitState::Closed => {
                    // Reset failure count on success
                    circuit.failure_count = 0;
                }
                _ => {}
            }
        }
    }

    /// Record a failure for a specific service
    pub async fn record_failure(&self, service: &str) {
        let mut circuits = self.circuits.write().await;
        let circuit = circuits
            .entry(service.to_string())
            .or_insert_with(ServiceCircuit::new);

        circuit.failure_count += 1;
        circuit.total_failures += 1;
        circuit.last_failure_time = Some(Utc::now());

        // Track recent failures for windowed counting
        circuit.recent_failures.push(Utc::now());
        if circuit.recent_failures.len() > self.config.max_failures_tracked {
            circuit.recent_failures.remove(0);
        }

        // Clean old failures outside the window
        let cutoff = Utc::now()
            - chrono::Duration::seconds(self.config.window_size_secs as i64);
        circuit
            .recent_failures
            .retain(|t| *t > cutoff);

        let window_failures = circuit.recent_failures.len() as u32;

        match circuit.state {
            CircuitState::Closed => {
                if window_failures >= self.config.failure_threshold {
                    error!(
                        service = %service,
                        failures = window_failures,
                        threshold = self.config.failure_threshold,
                        "Circuit OPENING — failure threshold exceeded"
                    );
                    circuit.state = CircuitState::Open;
                    circuit.last_state_change = Utc::now();
                }
            }
            CircuitState::HalfOpen => {
                // Any failure in half-open goes back to open
                warn!(service = %service, "Circuit reopening — failure in HalfOpen state");
                circuit.state = CircuitState::Open;
                circuit.success_count = 0;
                circuit.last_state_change = Utc::now();
            }
            CircuitState::Open => {
                // Already open, just track the failure
            }
        }
    }

    /// Get the current state of a service circuit
    pub async fn get_state(&self, service: &str) -> CircuitState {
        let circuits = self.circuits.read().await;
        circuits
            .get(service)
            .map(|c| c.state.clone())
            .unwrap_or(CircuitState::Closed)
    }

    /// Get metrics for all circuits
    pub async fn get_metrics(&self) -> HashMap<String, CircuitMetrics> {
        let circuits = self.circuits.read().await;
        circuits
            .iter()
            .map(|(name, circuit)| {
                let metrics = CircuitMetrics {
                    service: name.clone(),
                    state: circuit.state.clone(),
                    failure_count: circuit.failure_count,
                    total_requests: circuit.total_requests,
                    total_failures: circuit.total_failures,
                    total_rejected: circuit.total_rejected,
                    last_failure: circuit.last_failure_time,
                    last_state_change: circuit.last_state_change,
                    error_rate: if circuit.total_requests > 0 {
                        circuit.total_failures as f64 / circuit.total_requests as f64
                    } else {
                        0.0
                    },
                };
                (name.clone(), metrics)
            })
            .collect()
    }

    /// Manually reset a circuit to closed state
    pub async fn reset(&self, service: &str) -> Result<()> {
        let mut circuits = self.circuits.write().await;
        if let Some(circuit) = circuits.get_mut(service) {
            info!(service = %service, "Circuit manually reset to Closed");
            circuit.state = CircuitState::Closed;
            circuit.failure_count = 0;
            circuit.success_count = 0;
            circuit.recent_failures.clear();
            circuit.last_state_change = Utc::now();
            Ok(())
        } else {
            Err(anyhow!("No circuit found for service '{}'", service))
        }
    }

    /// Execute a closure with circuit breaker protection
    pub async fn execute<F, T>(&self, service: &str, f: F) -> Result<T>
    where
        F: std::future::Future<Output = Result<T>>,
    {
        if !self.is_allowed(service).await {
            return Err(anyhow!(
                "Circuit breaker is OPEN for service '{}'",
                service
            ));
        }

        match f.await {
            Ok(result) => {
                self.record_service_success(service).await;
                Ok(result)
            }
            Err(e) => {
                self.record_failure(service).await;
                Err(e)
            }
        }
    }
}

/// Circuit breaker metrics for monitoring
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CircuitMetrics {
    pub service: String,
    pub state: CircuitState,
    pub failure_count: u32,
    pub total_requests: u64,
    pub total_failures: u64,
    pub total_rejected: u64,
    pub last_failure: Option<DateTime<Utc>>,
    pub last_state_change: DateTime<Utc>,
    pub error_rate: f64,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_circuit_breaker_transitions() {
        let config = CircuitBreakerConfig {
            failure_threshold: 3,
            success_threshold: 2,
            open_timeout_secs: 1,
            window_size_secs: 60,
            max_failures_tracked: 100,
        };
        let cb = CircuitBreaker::new(config);

        // Initially closed
        assert_eq!(cb.get_state("test").await, CircuitState::Closed);
        assert!(cb.is_allowed("test").await);

        // Record failures to open the circuit
        for _ in 0..3 {
            cb.record_failure("test").await;
        }
        assert_eq!(cb.get_state("test").await, CircuitState::Open);
        assert!(!cb.is_allowed("test").await);

        // Wait for timeout
        tokio::time::sleep(tokio::time::Duration::from_secs(2)).await;

        // Should be half-open now
        assert!(cb.is_allowed("test").await);
        assert_eq!(cb.get_state("test").await, CircuitState::HalfOpen);

        // Record successes to close
        cb.record_service_success("test").await;
        cb.record_service_success("test").await;
        assert_eq!(cb.get_state("test").await, CircuitState::Closed);
    }
}
