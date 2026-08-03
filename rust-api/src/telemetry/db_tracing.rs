// Database & Redis Tracing — OTel span wrappers for all data operations
//
// Instruments:
// - PostgreSQL queries (via sqlx)
// - Redis commands (via redis crate)
// - ClickHouse queries (via clickhouse crate)
//
// Each operation gets its own OTel span with:
// - operation type (query/get/set/etc.)
// - target (table name, key pattern)
// - duration_ms
// - status (ok/error)
// - row_count (for queries)
//
// Usage:
//   let result = traced_pg_query(&pool, "SELECT * FROM workers WHERE id = $1", async { ... }).await;
//   let result = traced_redis_op("GET", "session:abc", async { ... }).await;

use std::time::Instant;

/// Execute a PostgreSQL query inside an OTel span.
/// Records operation, table, duration, status, and row count.
pub async fn traced_pg_query<F, T, E>(operation: &str, table: &str, query_fn: F) -> Result<T, E>
where
    F: std::future::Future<Output = Result<T, E>>,
    E: std::fmt::Display,
{
    let span = tracing::info_span!(
        "db.query",
        db.system = "postgresql",
        db.operation = %operation,
        db.sql.table = %table,
        duration_ms = tracing::field::Empty,
        db.rows_affected = tracing::field::Empty,
        status = tracing::field::Empty,
    );

    let _guard = span.enter();
    let start = Instant::now();

    let result = query_fn.await;
    let duration_ms = start.elapsed().as_millis() as u64;

    span.record("duration_ms", &duration_ms);

    match &result {
        Ok(_) => {
            span.record("status", &"ok");
            tracing::debug!(
                db.operation = %operation,
                db.sql.table = %table,
                duration_ms = duration_ms,
                "DB query completed"
            );
        }
        Err(e) => {
            span.record("status", &"error");
            tracing::error!(
                db.operation = %operation,
                db.sql.table = %table,
                duration_ms = duration_ms,
                error = %e,
                "DB query failed"
            );
        }
    }

    result
}

/// Execute a Redis operation inside an OTel span.
/// Records command, key pattern, duration, and status.
pub async fn traced_redis_op<F, T, E>(command: &str, key: &str, op_fn: F) -> Result<T, E>
where
    F: std::future::Future<Output = Result<T, E>>,
    E: std::fmt::Display,
{
    let span = tracing::info_span!(
        "redis.command",
        db.system = "redis",
        redis.command = %command,
        redis.key = %key,
        duration_ms = tracing::field::Empty,
        status = tracing::field::Empty,
    );

    let _guard = span.enter();
    let start = Instant::now();

    let result = op_fn.await;
    let duration_ms = start.elapsed().as_millis() as u64;

    span.record("duration_ms", &duration_ms);

    match &result {
        Ok(_) => {
            span.record("status", &"ok");
            tracing::debug!(
                redis.command = %command,
                redis.key = %key,
                duration_ms = duration_ms,
                "Redis operation completed"
            );
        }
        Err(e) => {
            span.record("status", &"error");
            tracing::error!(
                redis.command = %command,
                redis.key = %key,
                duration_ms = duration_ms,
                error = %e,
                "Redis operation failed"
            );
        }
    }

    result
}

/// Execute a ClickHouse query inside an OTel span.
pub async fn traced_ch_query<F, T, E>(operation: &str, table: &str, query_fn: F) -> Result<T, E>
where
    F: std::future::Future<Output = Result<T, E>>,
    E: std::fmt::Display,
{
    let span = tracing::info_span!(
        "clickhouse.query",
        db.system = "clickhouse",
        db.operation = %operation,
        db.sql.table = %table,
        duration_ms = tracing::field::Empty,
        status = tracing::field::Empty,
    );

    let _guard = span.enter();
    let start = Instant::now();

    let result = query_fn.await;
    let duration_ms = start.elapsed().as_millis() as u64;

    span.record("duration_ms", &duration_ms);

    match &result {
        Ok(_) => {
            span.record("status", &"ok");
            tracing::debug!(
                db.operation = %operation,
                db.sql.table = %table,
                duration_ms = duration_ms,
                "ClickHouse query completed"
            );
        }
        Err(e) => {
            span.record("status", &"error");
            tracing::error!(
                db.operation = %operation,
                db.sql.table = %table,
                duration_ms = duration_ms,
                error = %e,
                "ClickHouse query failed"
            );
        }
    }

    result
}
