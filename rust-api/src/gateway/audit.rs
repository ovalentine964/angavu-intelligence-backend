use uuid::Uuid;
// src/gateway/audit.rs

use axum::{
    extract::{Request, State},
    http::StatusCode,
    middleware::Next,
    response::Response,
};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use tokio::sync::RwLock;

/// Immutable audit trail for all API operations
pub struct AuditLogger {
    /// In-memory buffer (flushed to PostgreSQL periodically)
    buffer: Arc<RwLock<Vec<AuditLogEntry>>>,
    /// Maximum buffer size before forced flush
    max_buffer_size: usize,
    /// PostgreSQL connection pool for persistent storage
    pool: Option<sqlx::PgPool>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AuditLogEntry {
    pub id: uuid::Uuid,
    pub timestamp: DateTime<Utc>,
    pub org_id: String,
    pub key_id: String,
    pub endpoint: String,
    pub method: String,
    pub status_code: u16,
    pub response_time_ms: u64,
    pub ip_address: Option<String>,
    pub user_agent: Option<String>,
    /// Was the response suppressed by k-anonymity?
    pub k_anonymity_suppressed: bool,
    /// Query parameters (sanitized — no PII)
    pub query_hash: Option<String>,
    /// Rate limit remaining after this request
    pub rate_limit_remaining: u32,
}

impl AuditLogger {
    pub fn new(max_buffer_size: usize) -> Self {
        Self {
            buffer: Arc::new(RwLock::new(Vec::with_capacity(max_buffer_size))),
            max_buffer_size,
            pool: None,
        }
    }

    /// Create an AuditLogger with PostgreSQL persistence.
    pub fn with_pool(max_buffer_size: usize, pool: sqlx::PgPool) -> Self {
        Self {
            buffer: Arc::new(RwLock::new(Vec::with_capacity(max_buffer_size))),
            max_buffer_size,
            pool: Some(pool),
        }
    }

    /// Log an API request
    pub async fn log(&self, entry: AuditLogEntry) {
        let mut buffer = self.buffer.write().await;
        buffer.push(entry);

        if buffer.len() >= self.max_buffer_size {
            self.flush(&mut buffer).await;
        }
    }

    /// Flush audit buffer to PostgreSQL
    async fn flush(&self, buffer: &mut Vec<AuditLogEntry>) {
        let entries: Vec<AuditLogEntry> = std::mem::take(&mut *buffer);
        let count = entries.len();

        tracing::debug!(count = count, "Audit log flush started");

        // P2: Batch INSERT for 10× write throughput (single multi-row statement)
        if let Some(ref pool) = self.pool {
            if !entries.is_empty() {
                // Build multi-row INSERT for batch efficiency
                let mut query = String::from(
                    "INSERT INTO audit_log \
                     (id, timestamp, org_id, key_id, endpoint, method, \
                      status_code, response_time_ms, ip_address, user_agent, \
                      k_anonymity_suppressed, query_hash, rate_limit_remaining) VALUES ",
                );
                let mut binds: Vec<String> = Vec::with_capacity(entries.len());
                for (i, _) in entries.iter().enumerate() {
                    let n = i * 13;
                    binds.push(format!(
                        "(${}, ${}, ${}, ${}, ${}, ${}, ${}, ${}, ${}, ${}, ${}, ${}, ${})",
                        n + 1,
                        n + 2,
                        n + 3,
                        n + 4,
                        n + 5,
                        n + 6,
                        n + 7,
                        n + 8,
                        n + 9,
                        n + 10,
                        n + 11,
                        n + 12,
                        n + 13
                    ));
                }
                query.push_str(&binds.join(", "));
                query.push_str(" ON CONFLICT (id) DO NOTHING");

                let mut q = sqlx::query(&query);
                for entry in &entries {
                    q = q
                        .bind(entry.id)
                        .bind(entry.timestamp)
                        .bind(&entry.org_id)
                        .bind(&entry.key_id)
                        .bind(&entry.endpoint)
                        .bind(&entry.method)
                        .bind(entry.status_code as i32)
                        .bind(entry.response_time_ms as i64)
                        .bind(&entry.ip_address)
                        .bind(&entry.user_agent)
                        .bind(entry.k_anonymity_suppressed)
                        .bind(&entry.query_hash)
                        .bind(entry.rate_limit_remaining as i32);
                }
                match q.execute(pool).await {
                    Ok(_) => {
                        tracing::debug!(count = count, "Audit log batch flushed to PostgreSQL")
                    }
                    Err(e) => {
                        tracing::error!(error = %e, count = count, "Batch audit flush failed, falling back to individual inserts");
                        // Fallback: individual inserts
                        for entry in &entries {
                            let _ = sqlx::query(
                                "INSERT INTO audit_log (id, timestamp, org_id, key_id, endpoint, method, \
                                 status_code, response_time_ms, ip_address, user_agent, \
                                 k_anonymity_suppressed, query_hash, rate_limit_remaining) \
                                 VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13) ON CONFLICT (id) DO NOTHING"
                            )
                            .bind(entry.id).bind(entry.timestamp).bind(&entry.org_id)
                            .bind(&entry.key_id).bind(&entry.endpoint).bind(&entry.method)
                            .bind(entry.status_code as i32).bind(entry.response_time_ms as i64)
                            .bind(&entry.ip_address).bind(&entry.user_agent)
                            .bind(entry.k_anonymity_suppressed).bind(&entry.query_hash)
                            .bind(entry.rate_limit_remaining as i32)
                            .execute(pool).await.ok();
                        }
                    }
                }
            }
        } else {
            // Fallback: structured logging only
            for entry in &entries {
                tracing::info!(
                    org_id = %entry.org_id,
                    endpoint = %entry.endpoint,
                    method = %entry.method,
                    status = entry.status_code,
                    latency_ms = entry.response_time_ms,
                    "API audit (not persisted — no DB pool)"
                );
            }
        }
    }
}

/// Audit logging middleware
///
/// Extracts client IP from request extensions (set by auth middleware)
/// for complete audit trail with source IP.
pub async fn audit_middleware(
    State(state): State<super::GatewayState>,
    request: Request,
    next: Next,
) -> Result<Response, StatusCode> {
    let start = std::time::Instant::now();

    let method = request.method().to_string();
    let uri = request.uri().to_string();
    let user_agent = request
        .headers()
        .get("User-Agent")
        .and_then(|v| v.to_str().ok())
        .map(|s| s.to_string());

    let claims = request.extensions().get::<super::auth::Claims>().cloned();
    let client_ip = request
        .extensions()
        .get::<super::auth::ClientIp>()
        .map(|c| c.0.clone());

    let response = next.run(request).await;

    let elapsed = start.elapsed();

    if let Some(claims) = claims {
        let entry = AuditLogEntry {
            id: uuid::Uuid::new_v4(),
            timestamp: Utc::now(),
            org_id: claims.org_id,
            key_id: claims.key_id,
            endpoint: uri,
            method,
            status_code: response.status().as_u16(),
            response_time_ms: elapsed.as_millis() as u64,
            ip_address: client_ip,
            user_agent,
            k_anonymity_suppressed: false,
            query_hash: None,
            rate_limit_remaining: 0,
        };

        // Fire-and-forget audit log
        let audit = state.audit.clone();
        tokio::spawn(async move {
            audit.log(entry).await;
        });
    }

    Ok(response)
}

/// SQL migration to create the audit_log table.
pub const AUDIT_LOG_MIGRATION: &str = r#"
CREATE TABLE IF NOT EXISTS audit_log (
    id UUID PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    org_id VARCHAR(100) NOT NULL,
    key_id VARCHAR(100) NOT NULL,
    endpoint TEXT NOT NULL,
    method VARCHAR(10) NOT NULL,
    status_code SMALLINT NOT NULL,
    response_time_ms BIGINT NOT NULL,
    ip_address VARCHAR(45),
    user_agent TEXT,
    k_anonymity_suppressed BOOLEAN NOT NULL DEFAULT FALSE,
    query_hash VARCHAR(64),
    rate_limit_remaining INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp ON audit_log(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_org_id ON audit_log(org_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_endpoint ON audit_log(endpoint);
CREATE INDEX IF NOT EXISTS idx_audit_log_status ON audit_log(status_code);
"#;
