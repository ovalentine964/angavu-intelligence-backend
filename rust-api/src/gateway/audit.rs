// src/gateway/audit.rs

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

        // In production: INSERT INTO audit_log VALUES (...)
        // Using sqlx::query! or similar
        tracing::debug!(count = count, "Audit log flushed to database");

        // For now, just log structured entries
        for entry in &entries {
            tracing::info!(
                org_id = %entry.org_id,
                endpoint = %entry.endpoint,
                method = %entry.method,
                status = entry.status_code,
                latency_ms = entry.response_time_ms,
                "API audit"
            );
        }
    }
}

/// Audit logging middleware
pub async fn audit_middleware(
    State(state): State<super::GatewayState>,
    request: Request,
    next: Next,
) -> Result<Response, StatusCode> {
    let start = std::time::Instant::now();

    let method = request.method().to_string();
    let uri = request.uri().to_string();
    let user_agent = request.headers()
        .get("User-Agent")
        .and_then(|v| v.to_str().ok())
        .map(|s| s.to_string());

    let claims = request.extensions().get::<super::auth::Claims>().cloned();

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
            ip_address: None, // Extract from ConnectInfo in production
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
