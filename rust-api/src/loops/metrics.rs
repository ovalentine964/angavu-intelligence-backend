// Loop Engineering Metrics — Observability for all loops
// Prometheus-compatible metrics for monitoring OODA loops, drift, pipelines

use serde::{Deserialize, Serialize};
use chrono::{DateTime, Utc};

// ─── Loop Metrics ─────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LoopMetrics {
    // Fast loop
    pub fast_loop_iterations: u64,
    pub fast_loop_last_run: Option<DateTime<Utc>>,
    pub fast_loop_lag_count: u64,
    pub fast_loop_avg_duration_ms: f64,
    pub fast_loop_error_count: u64,

    // Medium loop
    pub medium_loop_iterations: u64,
    pub medium_loop_last_run: Option<DateTime<Utc>>,
    pub medium_loop_avg_duration_ms: f64,
    pub medium_loop_error_count: u64,

    // Slow loop
    pub slow_loop_iterations: u64,
    pub slow_loop_last_run: Option<DateTime<Utc>>,
    pub slow_loop_avg_duration_ms: f64,
    pub slow_loop_error_count: u64,
    pub slow_loop_reports_generated: u64,

    // Deep loop
    pub deep_loop_iterations: u64,
    pub deep_loop_last_run: Option<DateTime<Utc>>,
    pub deep_loop_avg_duration_ms: f64,
    pub deep_loop_error_count: u64,
    pub deep_loop_fl_rounds_completed: u64,

    // Global
    pub uptime_seconds: u64,
    pub started_at: Option<DateTime<Utc>>,
}

impl Default for LoopMetrics {
    fn default() -> Self {
        Self {
            fast_loop_iterations: 0,
            fast_loop_last_run: None,
            fast_loop_lag_count: 0,
            fast_loop_avg_duration_ms: 0.0,
            fast_loop_error_count: 0,
            medium_loop_iterations: 0,
            medium_loop_last_run: None,
            medium_loop_avg_duration_ms: 0.0,
            medium_loop_error_count: 0,
            slow_loop_iterations: 0,
            slow_loop_last_run: None,
            slow_loop_avg_duration_ms: 0.0,
            slow_loop_error_count: 0,
            slow_loop_reports_generated: 0,
            deep_loop_iterations: 0,
            deep_loop_last_run: None,
            deep_loop_avg_duration_ms: 0.0,
            deep_loop_error_count: 0,
            deep_loop_fl_rounds_completed: 0,
            uptime_seconds: 0,
            started_at: Some(Utc::now()),
        }
    }
}

impl LoopMetrics {
    /// Format metrics as Prometheus-compatible text.
    pub fn to_prometheus(&self) -> String {
        let mut lines = Vec::new();

        // Fast loop
        lines.push("# HELP angavu_loop_fast_iterations Total fast loop iterations".to_string());
        lines.push("# TYPE angavu_loop_fast_iterations counter".to_string());
        lines.push(format!("angavu_loop_fast_iterations {}", self.fast_loop_iterations));

        lines.push("# HELP angavu_loop_fast_lag_total Events lagged behind".to_string());
        lines.push("# TYPE angavu_loop_fast_lag_total counter".to_string());
        lines.push(format!("angavu_loop_fast_lag_total {}", self.fast_loop_lag_count));

        lines.push("# HELP angavu_loop_fast_duration_ms Average fast loop duration".to_string());
        lines.push("# TYPE angavu_loop_fast_duration_ms gauge".to_string());
        lines.push(format!("angavu_loop_fast_duration_ms {}", self.fast_loop_avg_duration_ms));

        // Medium loop
        lines.push("# HELP angavu_loop_medium_iterations Total medium loop iterations".to_string());
        lines.push("# TYPE angavu_loop_medium_iterations counter".to_string());
        lines.push(format!("angavu_loop_medium_iterations {}", self.medium_loop_iterations));

        lines.push("# HELP angavu_loop_medium_duration_ms Average medium loop duration".to_string());
        lines.push("# TYPE angavu_loop_medium_duration_ms gauge".to_string());
        lines.push(format!("angavu_loop_medium_duration_ms {}", self.medium_loop_avg_duration_ms));

        // Slow loop
        lines.push("# HELP angavu_loop_slow_iterations Total slow loop iterations".to_string());
        lines.push("# TYPE angavu_loop_slow_iterations counter".to_string());
        lines.push(format!("angavu_loop_slow_iterations {}", self.slow_loop_iterations));

        lines.push("# HELP angavu_loop_slow_reports_generated Total reports generated".to_string());
        lines.push("# TYPE angavu_loop_slow_reports_generated counter".to_string());
        lines.push(format!("angavu_loop_slow_reports_generated {}", self.slow_loop_reports_generated));

        // Deep loop
        lines.push("# HELP angavu_loop_deep_iterations Total deep loop iterations".to_string());
        lines.push("# TYPE angavu_loop_deep_iterations counter".to_string());
        lines.push(format!("angavu_loop_deep_iterations {}", self.deep_loop_iterations));

        lines.push("# HELP angavu_loop_deep_fl_rounds Federated learning rounds completed".to_string());
        lines.push("# TYPE angavu_loop_deep_fl_rounds counter".to_string());
        lines.push(format!("angavu_loop_deep_fl_rounds {}", self.deep_loop_fl_rounds_completed));

        // Uptime
        lines.push("# HELP angavu_uptime_seconds Server uptime".to_string());
        lines.push("# TYPE angavu_uptime_seconds gauge".to_string());
        lines.push(format!("angavu_uptime_seconds {}", self.uptime_seconds));

        lines.join("\n") + "\n"
    }

    /// Get a summary for logging/health checks.
    pub fn summary(&self) -> String {
        format!(
            "Loops: fast={} (lag={}) medium={} slow={} (reports={}) deep={} (fl={}) uptime={}s",
            self.fast_loop_iterations,
            self.fast_loop_lag_count,
            self.medium_loop_iterations,
            self.slow_loop_iterations,
            self.slow_loop_reports_generated,
            self.deep_loop_iterations,
            self.deep_loop_fl_rounds_completed,
            self.uptime_seconds,
        )
    }
}

// ─── Drift Metrics ────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DriftMetrics {
    pub current_accuracy: f64,
    pub baseline_accuracy: f64,
    pub relative_degradation: f64,
    pub calibration_error: f64,
    pub model_version: String,
    pub last_retrain: Option<DateTime<Utc>>,
    pub is_rolled_back: bool,
    pub sample_count: usize,
}

impl DriftMetrics {
    pub fn to_prometheus(&self) -> String {
        let mut lines = Vec::new();

        lines.push("# HELP angavu_drift_accuracy Current model accuracy".to_string());
        lines.push("# TYPE angavu_drift_accuracy gauge".to_string());
        lines.push(format!("angavu_drift_accuracy {}", self.current_accuracy));

        lines.push("# HELP angavu_drift_baseline Baseline model accuracy".to_string());
        lines.push("# TYPE angavu_drift_baseline gauge".to_string());
        lines.push(format!("angavu_drift_baseline {}", self.baseline_accuracy));

        lines.push("# HELP angavu_drift_degradation Relative accuracy degradation".to_string());
        lines.push("# TYPE angavu_drift_degradation gauge".to_string());
        lines.push(format!("angavu_drift_degradation {}", self.relative_degradation));

        lines.push("# HELP angavu_drift_calibration_error Expected calibration error".to_string());
        lines.push("# TYPE angavu_drift_calibration_error gauge".to_string());
        lines.push(format!("angavu_drift_calibration_error {}", self.calibration_error));

        lines.push("# HELP angavu_drift_rolled_back Whether model is in rollback state".to_string());
        lines.push("# TYPE angavu_drift_rolled_back gauge".to_string());
        lines.push(format!("angavu_drift_rolled_back {}", if self.is_rolled_back { 1 } else { 0 }));

        lines.push("# HELP angavu_drift_sample_count Samples in drift window".to_string());
        lines.push("# TYPE angavu_drift_sample_count gauge".to_string());
        lines.push(format!("angavu_drift_sample_count {}", self.sample_count));

        lines.join("\n") + "\n"
    }
}

// ─── Circuit Breaker Metrics ──────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CircuitBreakerMetrics {
    pub services: Vec<ServiceMetrics>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ServiceMetrics {
    pub name: String,
    pub state: String,
    pub failure_rate: f64,
    pub avg_latency_ms: f64,
    pub total_requests: u64,
    pub total_rejected: u64,
}

impl CircuitBreakerMetrics {
    pub fn to_prometheus(&self) -> String {
        let mut lines = Vec::new();

        for svc in &self.services {
            let labels = format!("service=\"{}\"", svc.name);

            lines.push(format!("# HELP angavu_circuit_state Circuit state (0=closed,1=open,2=half-open)"));
            lines.push("# TYPE angavu_circuit_state gauge".to_string());
            let state_val = match svc.state.as_str() {
                "Closed" => 0,
                "Open" => 1,
                "HalfOpen" => 2,
                _ => -1,
            };
            lines.push(format!("angavu_circuit_state{{{}}} {}", labels, state_val));

            lines.push(format!("angavu_circuit_failure_rate{{{}}} {}", labels, svc.failure_rate));
            lines.push(format!("angavu_circuit_latency_ms{{{}}} {}", labels, svc.avg_latency_ms));
            lines.push(format!("angavu_circuit_requests_total{{{}}} {}", labels, svc.total_requests));
            lines.push(format!("angavu_circuit_rejected_total{{{}}} {}", labels, svc.total_rejected));
        }

        lines.join("\n") + "\n"
    }
}
