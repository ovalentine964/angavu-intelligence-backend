// Health Check Endpoints — Liveness, readiness, and detailed diagnostics
//
// GET /health          — Simple liveness (200 OK if process is alive)
// GET /health/ready    — Readiness (checks DB, Redis connectivity)
// GET /health/detailed — Full diagnostics (pool stats, memory, uptime, version)
//
// Used by:
// - Docker HEALTHCHECK
// - Kubernetes liveness/readiness probes
// - Load balancer health checks
// - CI/CD deploy verification

use axum::{extract::State, http::StatusCode, response::IntoResponse, routing::get, Json, Router};
use serde::Serialize;
use std::sync::Arc;
use sysinfo::System;

/// Health check state — shared references to all data stores.
#[derive(Clone)]
pub struct HealthState {
    pub db: sqlx::PgPool,
    pub redis: redis::aio::ConnectionManager,
    /// Optional ClickHouse client (may not be configured)
    pub clickhouse_url: Option<String>,
    /// Application start time for uptime calculation
    pub started_at: std::time::Instant,
}

/// Build the health check router.
pub fn health_router(state: HealthState) -> Router {
    Router::new()
        .route("/health", get(liveness))
        .route("/health/ready", get(readiness))
        .route("/health/detailed", get(detailed_health))
        .with_state(Arc::new(state))
}

/// GET /health — Simple liveness check.
/// Returns 200 OK if the process is running. No dependency checks.
async fn liveness() -> impl IntoResponse {
    (StatusCode::OK, Json(serde_json::json!({"status": "ok"})))
}

/// GET /health/ready — Readiness check.
/// Verifies DB and Redis are reachable. Returns 503 if any dependency is down.
async fn readiness(State(state): State<Arc<HealthState>>) -> impl IntoResponse {
    let mut checks = Vec::new();
    let mut all_ok = true;

    // PostgreSQL check
    let db_start = std::time::Instant::now();
    let db_ok = sqlx::query("SELECT 1").execute(&state.db).await.is_ok();
    let db_ms = db_start.elapsed().as_millis() as u64;
    checks.push(HealthCheck {
        component: "postgresql".to_string(),
        status: if db_ok { "ok" } else { "error" }.to_string(),
        latency_ms: db_ms,
        message: if db_ok {
            None
        } else {
            Some("Connection failed".to_string())
        },
    });
    if !db_ok {
        all_ok = false;
    }

    // Redis check
    let redis_start = std::time::Instant::now();
    let redis_ok = {
        let mut conn = state.redis.clone();
        redis::cmd("PING")
            .query_async::<_, String>(&mut conn)
            .await
            .is_ok()
    };
    let redis_ms = redis_start.elapsed().as_millis() as u64;
    checks.push(HealthCheck {
        component: "redis".to_string(),
        status: if redis_ok { "ok" } else { "error" }.to_string(),
        latency_ms: redis_ms,
        message: if redis_ok {
            None
        } else {
            Some("PING failed".to_string())
        },
    });
    if !redis_ok {
        all_ok = false;
    }

    // ClickHouse check (optional)
    if let Some(ref ch_url) = state.clickhouse_url {
        let ch_start = std::time::Instant::now();
        let ch_ok = reqwest::get(format!("{}/ping", ch_url))
            .await
            .map(|r| r.status().is_success())
            .unwrap_or(false);
        let ch_ms = ch_start.elapsed().as_millis() as u64;
        checks.push(HealthCheck {
            component: "clickhouse".to_string(),
            status: if ch_ok { "ok" } else { "error" }.to_string(),
            latency_ms: ch_ms,
            message: if ch_ok {
                None
            } else {
                Some("Ping failed".to_string())
            },
        });
        if !ch_ok {
            all_ok = false;
        }
    }

    let response = ReadinessResponse {
        status: if all_ok { "ok" } else { "degraded" }.to_string(),
        checks,
    };

    if all_ok {
        (
            StatusCode::OK,
            Json(serde_json::to_value(response).unwrap()),
        )
            .into_response()
    } else {
        (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(serde_json::to_value(response).unwrap()),
        )
            .into_response()
    }
}

/// GET /health/detailed — Full diagnostic information.
/// Includes pool stats, memory usage, uptime, version, and all dependency checks.
async fn detailed_health(State(state): State<Arc<HealthState>>) -> impl IntoResponse {
    let mut checks = Vec::new();

    // PostgreSQL
    let db_start = std::time::Instant::now();
    let db_ok = sqlx::query("SELECT 1").execute(&state.db).await.is_ok();
    let db_ms = db_start.elapsed().as_millis() as u64;
    let pool_stats = PoolStats {
        active: state.db.size(),
        idle: state.db.num_idle(),
        max_size: state.db.options().get_max_connections(),
    };
    checks.push(DetailedCheck {
        component: "postgresql".to_string(),
        status: if db_ok { "ok" } else { "error" }.to_string(),
        latency_ms: db_ms,
        details: serde_json::json!({
            "pool": pool_stats,
        }),
    });

    // Redis
    let redis_start = std::time::Instant::now();
    let redis_ok = {
        let mut conn = state.redis.clone();
        redis::cmd("PING")
            .query_async::<_, String>(&mut conn)
            .await
            .is_ok()
    };
    let redis_ms = redis_start.elapsed().as_millis() as u64;
    checks.push(DetailedCheck {
        component: "redis".to_string(),
        status: if redis_ok { "ok" } else { "error" }.to_string(),
        latency_ms: redis_ms,
        details: serde_json::json!({}),
    });

    // ClickHouse (optional)
    if let Some(ref ch_url) = state.clickhouse_url {
        let ch_start = std::time::Instant::now();
        let ch_ok = reqwest::get(format!("{}/ping", ch_url))
            .await
            .map(|r| r.status().is_success())
            .unwrap_or(false);
        let ch_ms = ch_start.elapsed().as_millis() as u64;
        checks.push(DetailedCheck {
            component: "clickhouse".to_string(),
            status: if ch_ok { "ok" } else { "error" }.to_string(),
            latency_ms: ch_ms,
            details: serde_json::json!({}),
        });
    }

    // System info
    let sys = System::new_all();
    let uptime_secs = state.started_at.elapsed().as_secs();

    let response = DetailedHealthResponse {
        status: "ok".to_string(),
        version: env!("CARGO_PKG_VERSION").to_string(),
        uptime_secs,
        system: SystemInfo {
            total_memory_mb: sys.total_memory() / 1024 / 1024,
            used_memory_mb: sys.used_memory() / 1024 / 1024,
            available_memory_mb: sys.available_memory() / 1024 / 1024,
            cpu_count: sys.cpus().len(),
            load_avg_1m: System::load_average().one,
        },
        checks,
    };

    (
        StatusCode::OK,
        Json(serde_json::to_value(response).unwrap()),
    )
}

// ── Response Types ──────────────────────────────────────────────────────

#[derive(Serialize)]
struct HealthCheck {
    component: String,
    status: String,
    latency_ms: u64,
    #[serde(skip_serializing_if = "Option::is_none")]
    message: Option<String>,
}

#[derive(Serialize)]
struct ReadinessResponse {
    status: String,
    checks: Vec<HealthCheck>,
}

#[derive(Serialize)]
struct DetailedCheck {
    component: String,
    status: String,
    latency_ms: u64,
    details: serde_json::Value,
}

#[derive(Serialize)]
struct PoolStats {
    active: u32,
    idle: u32,
    max_size: u32,
}

#[derive(Serialize)]
struct SystemInfo {
    total_memory_mb: u64,
    used_memory_mb: u64,
    available_memory_mb: u64,
    cpu_count: usize,
    load_avg_1m: f64,
}

#[derive(Serialize)]
struct DetailedHealthResponse {
    status: String,
    version: String,
    uptime_secs: u64,
    system: SystemInfo,
    checks: Vec<DetailedCheck>,
}
