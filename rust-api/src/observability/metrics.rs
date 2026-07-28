// Prometheus metrics instrumentation for Angavu Intelligence Backend
// Exposes /metrics endpoint with HTTP, OODA, sync, credit, and federated learning metrics

use metrics::{counter, histogram, gauge};
use std::time::Instant;
use axum::{
    extract::Request,
    middleware::Next,
    response::Response,
};

/// Register all application metrics.
/// Call once at startup before serving requests.
pub fn register_metrics() {
    // ── HTTP Metrics ──────────────────────────────────────────
    metrics::describe_counter!("http_requests_total", "Total HTTP requests");
    metrics::describe_histogram!("http_request_duration_seconds", "HTTP request latency");
    metrics::describe_gauge!("http_active_connections", "Active HTTP connections");

    // ── OODA Loop Metrics ─────────────────────────────────────
    metrics::describe_histogram!("ooda_loop_cycle_seconds", "OODA loop full cycle time");
    metrics::describe_histogram!("ooda_phase_duration_seconds", "OODA phase duration (observe/orient/decide/act)");
    metrics::describe_counter!("ooda_loop_cycles_total", "Total OODA loop cycles completed");

    // ── Sync Pipeline Metrics ─────────────────────────────────
    metrics::describe_counter!("sync_operations_total", "Total sync operations");
    metrics::describe_counter!("sync_bytes_transferred_total", "Total bytes synced");
    metrics::describe_histogram!("sync_operation_duration_seconds", "Sync operation latency");

    // ── Credit Scoring Metrics ────────────────────────────────
    metrics::describe_gauge!("credit_score_accuracy", "Credit scoring accuracy");
    metrics::describe_gauge!("credit_score_f1", "Credit scoring F1 score");
    metrics::describe_histogram!("credit_scoring_duration_seconds", "Credit scoring latency");

    // ── Federated Learning Metrics ────────────────────────────
    metrics::describe_counter!("federated_learning_rounds_total", "Total FL aggregation rounds");
    metrics::describe_gauge!("federated_learning_clients_active", "Active FL clients");
    metrics::describe_histogram!("federated_learning_aggregation_duration_seconds", "FL aggregation time");
    metrics::describe_counter!("federated_learning_aggregation_failures_total", "FL aggregation failures");

    // ── Intent Classification Metrics ─────────────────────────
    metrics::describe_gauge!("intent_classification_accuracy", "Intent classification accuracy");

    // ── Database Metrics ──────────────────────────────────────
    metrics::describe_histogram!("db_query_duration_seconds", "Database query latency");

    // ── Redis Metrics ─────────────────────────────────────────
    metrics::describe_counter!("redis_operations_total", "Total Redis operations");
}

/// Metrics layer for Axum — tracks request count, latency, and active connections.
pub async fn metrics_middleware(request: Request, next: Next) -> Response {
    let method = request.method().clone();
    let path = request.uri().path().to_string();
    let start = Instant::now();

    counter!("http_requests_total",
        "method" => method.to_string(),
        "handler" => path.clone()
    )
    .increment(1);

    gauge!("http_active_connections").increment(1.0);

    let response = next.run(request).await;

    let duration = start.elapsed().as_secs_f64();
    let status = response.status().as_u16().to_string();

    histogram!("http_request_duration_seconds",
        "method" => method.to_string(),
        "handler" => path,
        "status" => status
    )
    .record(duration);

    gauge!("http_active_connections").decrement(1.0);

    response
}

/// Record an OODA loop cycle time.
pub fn record_ooda_cycle(loop_name: &str, duration_secs: f64) {
    histogram!("ooda_loop_cycle_seconds", "loop_name" => loop_name.to_string())
        .record(duration_secs);
    counter!("ooda_loop_cycles_total", "loop_name" => loop_name.to_string())
        .increment(1);
}

/// Record an OODA phase duration.
pub fn record_ooda_phase(phase: &str, duration_secs: f64) {
    histogram!("ooda_phase_duration_seconds", "phase" => phase.to_string())
        .record(duration_secs);
}

/// Record a sync operation.
pub fn record_sync_operation(status: &str, duration_secs: f64, bytes: u64) {
    counter!("sync_operations_total", "status" => status.to_string())
        .increment(1);
    histogram!("sync_operation_duration_seconds", "status" => status.to_string())
        .record(duration_secs);
    counter!("sync_bytes_transferred_total")
        .increment(bytes);
}

/// Update credit scoring accuracy gauge.
pub fn update_credit_accuracy(model_version: &str, accuracy: f64, f1: f64) {
    gauge!("credit_score_accuracy", "model_version" => model_version.to_string())
        .set(accuracy);
    gauge!("credit_score_f1", "model_version" => model_version.to_string())
        .set(f1);
}

/// Record a credit scoring operation.
pub fn record_credit_scoring(duration_secs: f64) {
    histogram!("credit_scoring_duration_seconds").record(duration_secs);
}

/// Record a federated learning aggregation round.
pub fn record_fl_round(duration_secs: f64, clients: u64, success: bool) {
    counter!("federated_learning_rounds_total").increment(1);
    gauge!("federated_learning_clients_active").set(clients as f64);
    histogram!("federated_learning_aggregation_duration_seconds").record(duration_secs);
    if !success {
        counter!("federated_learning_aggregation_failures_total").increment(1);
    }
}

/// Update intent classification accuracy.
pub fn update_intent_accuracy(accuracy: f64) {
    gauge!("intent_classification_accuracy").set(accuracy);
}

/// Record a database query duration.
pub fn record_db_query(db: &str, duration_secs: f64) {
    histogram!("db_query_duration_seconds", "db" => db.to_string())
        .record(duration_secs);
}

/// Record a Redis operation.
pub fn record_redis_op(operation: &str) {
    counter!("redis_operations_total", "operation" => operation.to_string())
        .increment(1);
}
