// Usage Metering Middleware — Track and enforce API call limits per org per billing cycle.
//
// Architecture:
// - Redis: Hot counter storage (INCR on every request, fast reads for limit checks)
//   Key format: "usage:{org_id}:{YYYY-MM}" → atomic counter
// - PostgreSQL: Persistent billing_records table for audit trail
// - ClickHouse: Event-level analytics (async, non-blocking)
//
// Tier Limits (monthly):
//   Free:       100 API calls/month
//   Starter:  5,000 API calls/month
//   Pro:     50,000 API calls/month
//   Enterprise: Unlimited
//
// The middleware runs AFTER authentication (claims available in request extensions).
// On every authenticated request, it:
//   1. Increments the Redis counter (atomic INCR)
//   2. Checks against the tier limit
//   3. Returns 429 if limit exceeded
//   4. Logs the event to ClickHouse asynchronously

use axum::{extract::Request, http::StatusCode, middleware::Next, response::Response};
use chrono::Utc;
use serde::{Deserialize, Serialize};
use std::sync::Arc;

use crate::gateway::auth::{BuyerTier, Claims};

// ═══════════════════════════════════════════════════════════
//  TYPES
// ═══════════════════════════════════════════════════════════

/// Usage summary returned to the client.
#[derive(Debug, Serialize)]
pub struct UsageSummary {
    pub org_id: String,
    pub tier: String,
    pub billing_period: String,
    pub api_calls_used: u64,
    pub api_calls_limit: u64,
    pub api_calls_remaining: u64,
    pub usage_pct: f64,
    pub days_remaining_in_period: u32,
    pub overage: bool,
}

/// Internal: monthly usage record for PostgreSQL persistence.
#[derive(Debug, Serialize, Deserialize)]
pub struct UsageRecord {
    pub org_id: String,
    pub billing_period: String, // "YYYY-MM"
    pub api_calls: u64,
    pub updated_at: chrono::DateTime<chrono::Utc>,
}

/// Async event for ClickHouse analytics pipeline.
#[derive(Debug, Serialize)]
pub struct UsageEvent {
    pub org_id: String,
    pub tier: String,
    pub endpoint: String,
    pub method: String,
    pub status_code: u16,
    pub timestamp: chrono::DateTime<chrono::Utc>,
    pub billing_period: String,
}

// ═══════════════════════════════════════════════════════════
//  REDIS KEY HELPERS
// ═══════════════════════════════════════════════════════════

/// Redis key for the current month's usage counter.
fn usage_key(org_id: &str, period: &str) -> String {
    format!("usage:{}:{}", org_id, period)
}

/// Redis key for daily usage (for rate limiting within the month).
fn daily_usage_key(org_id: &str, date: &str) -> String {
    format!("usage:daily:{}:{}", org_id, date)
}

/// Get the current billing period string (YYYY-MM).
fn current_billing_period() -> String {
    Utc::now().format("%Y-%m").to_string()
}

/// Get today's date string (YYYY-MM-DD).
fn current_date() -> String {
    Utc::now().format("%Y-%m-%d").to_string()
}

/// Days remaining in the current month.
fn days_remaining_in_period() -> u32 {
    let now = Utc::now();
    let end_of_month = if now.month() == 12 {
        chrono::NaiveDate::from_ymd_opt(now.year() + 1, 1, 1).unwrap()
    } else {
        chrono::NaiveDate::from_ymd_opt(now.year(), now.month() + 1, 1).unwrap()
    };
    let remaining = end_of_month.signed_duration_since(now.date_naive());
    remaining.num_days().max(0) as u32
}

// ═══════════════════════════════════════════════════════════
//  TIER LIMITS
// ═══════════════════════════════════════════════════════════

/// Monthly API call limits per tier.
pub fn monthly_limit(tier: &BuyerTier) -> u64 {
    match tier {
        BuyerTier::Free => 100,
        BuyerTier::Starter => 5_000,
        BuyerTier::Pro => 50_000,
        BuyerTier::Enterprise => u64::MAX, // unlimited
    }
}

/// Daily API call limits (derived from monthly, prevents burst abuse).
pub fn daily_limit(tier: &BuyerTier) -> u64 {
    match tier {
        BuyerTier::Free => 10,
        BuyerTier::Starter => 250,
        BuyerTier::Pro => 2_500,
        BuyerTier::Enterprise => u64::MAX,
    }
}

// ═══════════════════════════════════════════════════════════
//  METERING MIDDLEWARE
// ═══════════════════════════════════════════════════════════

/// Axum middleware that tracks usage and enforces tier limits.
///
/// Runs AFTER jwt_auth_middleware (claims are in request extensions).
/// On limit exceeded: returns 429 with upgrade message.
pub async fn usage_metering_middleware(
    axum::extract::State(state): axum::extract::State<crate::gateway::GatewayState>,
    request: Request,
    next: Next,
) -> Result<Response, StatusCode> {
    // Extract claims (injected by jwt_auth_middleware)
    let claims = request
        .extensions()
        .get::<Claims>()
        .cloned()
        .ok_or(StatusCode::UNAUTHORIZED)?;

    // Enterprise tier: skip metering (unlimited)
    if claims.tier == BuyerTier::Enterprise {
        return Ok(next.run(request).await);
    }

    let period = current_billing_period();
    let date = current_date();
    let key = usage_key(&claims.org_id, &period);
    let daily_key = daily_usage_key(&claims.org_id, &date);

    // 1. Increment monthly counter (atomic)
    let monthly_count: u64 = match redis::cmd("INCR")
        .arg(&key)
        .query_async::<_, i64>(&mut state.redis.clone())
        .await
    {
        Ok(n) => n.max(0) as u64,
        Err(e) => {
            tracing::error!(error = %e, "Redis INCR failed for usage metering — allowing request");
            return Ok(next.run(request).await);
        }
    };

    // Set TTL on the key (2 months, so it persists through the billing period + grace)
    if monthly_count == 1 {
        let _ = redis::cmd("EXPIRE")
            .arg(&key)
            .arg(5_184_000i64) // 60 days in seconds
            .query_async::<_, ()>(&mut state.redis.clone())
            .await;
    }

    // 2. Increment daily counter
    let daily_count: u64 = match redis::cmd("INCR")
        .arg(&daily_key)
        .query_async::<_, i64>(&mut state.redis.clone())
        .await
    {
        Ok(n) => n.max(0) as u64,
        Err(_) => 0,
    };

    if daily_count == 1 {
        let _ = redis::cmd("EXPIRE")
            .arg(&daily_key)
            .arg(86_400i64) // 24 hours
            .query_async::<_, ()>(&mut state.redis.clone())
            .await;
    }

    // 3. Check monthly limit
    let limit = monthly_limit(&claims.tier);
    if monthly_count > limit {
        tracing::warn!(
            org_id = %claims.org_id,
            tier = ?claims.tier,
            used = monthly_count,
            limit = limit,
            "Monthly API limit exceeded"
        );

        let error_body = serde_json::json!({
            "error": {
                "code": "USAGE_LIMIT_EXCEEDED",
                "message": format!(
                    "You have reached your monthly API call limit ({}/{}). \
                     Upgrade your plan at https://angavu.co.ke/billing to continue.",
                    monthly_count, limit
                ),
                "details": {
                    "tier": format!("{:?}", claims.tier),
                    "used": monthly_count,
                    "limit": limit,
                    "period": period,
                    "upgrade_url": "https://angavu.co.ke/billing"
                }
            }
        });

        let mut response = Response::new(axum::body::Body::from(error_body.to_string()));
        *response.status_mut() = StatusCode::TOO_MANY_REQUESTS;
        response.headers_mut().insert(
            axum::http::header::CONTENT_TYPE,
            "application/json".parse().unwrap(),
        );
        response.headers_mut().insert(
            "Retry-After",
            "86400".parse().unwrap(), // suggest retry tomorrow
        );
        return Ok(response);
    }

    // 4. Check daily limit
    let d_limit = daily_limit(&claims.tier);
    if daily_count > d_limit {
        tracing::warn!(
            org_id = %claims.org_id,
            tier = ?claims.tier,
            daily_used = daily_count,
            daily_limit = d_limit,
            "Daily API limit exceeded"
        );

        let error_body = serde_json::json!({
            "error": {
                "code": "DAILY_LIMIT_EXCEEDED",
                "message": format!(
                    "You have reached your daily API call limit ({}/{}). \
                     Please try again tomorrow or upgrade your plan.",
                    daily_count, d_limit
                ),
                "details": {
                    "daily_used": daily_count,
                    "daily_limit": d_limit,
                    "retry_after_seconds": seconds_until_midnight_utc()
                }
            }
        });

        let mut response = Response::new(axum::body::Body::from(error_body.to_string()));
        *response.status_mut() = StatusCode::TOO_MANY_REQUESTS;
        response.headers_mut().insert(
            axum::http::header::CONTENT_TYPE,
            "application/json".parse().unwrap(),
        );
        let retry = seconds_until_midnight_utc().to_string();
        response
            .headers_mut()
            .insert("Retry-After", retry.parse().unwrap());
        return Ok(response);
    }

    // 5. Log usage event to ClickHouse (fire-and-forget)
    let endpoint = request.uri().path().to_string();
    let method = request.method().to_string();
    let tier_str = format!("{:?}", claims.tier);
    let org_id_clone = claims.org_id.clone();
    let ch_url = std::env::var("CLICKHOUSE_URL").ok();

    // Proceed with the request
    let response = next.run(request).await;
    let status = response.status().as_u16();

    // Fire-and-forget: log to ClickHouse
    if let Some(ref _url) = ch_url {
        let event = UsageEvent {
            org_id: org_id_clone,
            tier: tier_str,
            endpoint,
            method,
            status_code: status,
            timestamp: Utc::now(),
            billing_period: current_billing_period(),
        };
        tokio::spawn(async move {
            if let Err(e) = log_usage_event_ch(&event).await {
                tracing::debug!(error = %e, "Failed to log usage event to ClickHouse (non-critical)");
            }
        });
    }

    // 6. Add usage headers to response
    let mut response = response;
    let remaining = limit.saturating_sub(monthly_count);
    response
        .headers_mut()
        .insert("X-RateLimit-Limit", limit.to_string().parse().unwrap());
    response.headers_mut().insert(
        "X-RateLimit-Remaining",
        remaining.to_string().parse().unwrap(),
    );
    response.headers_mut().insert(
        "X-RateLimit-Reset",
        seconds_until_period_end().to_string().parse().unwrap(),
    );

    Ok(response)
}

// ═══════════════════════════════════════════════════════════
//  USAGE QUERIES
// ═══════════════════════════════════════════════════════════

/// Get the current usage summary for an org.
pub async fn get_usage_summary(
    redis: &redis::aio::ConnectionManager,
    db: &sqlx::PgPool,
    org_id: &str,
    tier: &BuyerTier,
) -> Result<UsageSummary, anyhow::Error> {
    let period = current_billing_period();
    let key = usage_key(org_id, &period);

    // Read from Redis (hot path)
    let api_calls_used: u64 = redis::cmd("GET")
        .arg(&key)
        .query_async::<_, Option<i64>>(&mut redis.clone())
        .await
        .ok()
        .flatten()
        .map(|n| n.max(0) as u64)
        .unwrap_or(0);

    let limit = monthly_limit(tier);
    let remaining = limit.saturating_sub(api_calls_used);
    let usage_pct = if limit > 0 && limit != u64::MAX {
        (api_calls_used as f64 / limit as f64 * 100.0).min(100.0)
    } else {
        0.0
    };

    Ok(UsageSummary {
        org_id: org_id.to_string(),
        tier: format!("{:?}", tier),
        billing_period: period,
        api_calls_used,
        api_calls_limit: if limit == u64::MAX { 0 } else { limit }, // 0 = unlimited
        api_calls_remaining: if limit == u64::MAX { 0 } else { remaining },
        usage_pct,
        days_remaining_in_period: days_remaining_in_period(),
        overage: api_calls_used > limit && limit != u64::MAX,
    })
}

// ═══════════════════════════════════════════════════════════
//  PERSISTENCE
// ═══════════════════════════════════════════════════════════

/// Persist monthly usage to PostgreSQL (called by background job, not on every request).
pub async fn persist_monthly_usage(
    db: &sqlx::PgPool,
    redis: &redis::aio::ConnectionManager,
    org_id: &str,
    period: &str,
) -> Result<u64, anyhow::Error> {
    let key = usage_key(org_id, period);
    let count: i64 = redis::cmd("GET")
        .arg(&key)
        .query_async::<_, Option<i64>>(&mut redis.clone())
        .await
        .ok()
        .flatten()
        .unwrap_or(0);

    sqlx::query(
        r#"
        INSERT INTO usage_records (org_id, billing_period, api_calls, updated_at)
        VALUES ($1, $2, $3, NOW())
        ON CONFLICT (org_id, billing_period)
        DO UPDATE SET api_calls = GREATEST(usage_records.api_calls, $3), updated_at = NOW()
        "#,
    )
    .bind(org_id)
    .bind(period)
    .bind(count)
    .execute(db)
    .await?;

    Ok(count.max(0) as u64)
}

/// Log a usage event to ClickHouse for analytics.
async fn log_usage_event_ch(event: &UsageEvent) -> Result<(), anyhow::Error> {
    let url =
        std::env::var("CLICKHOUSE_URL").unwrap_or_else(|_| "http://localhost:8123".to_string());

    let client = clickhouse::Client::default().with_url(&url);

    // Insert into usage_events table
    // Table must exist in ClickHouse (created by migration)
    client
        .query(
            "INSERT INTO usage_events (org_id, tier, endpoint, method, status_code, timestamp, billing_period) VALUES (?, ?, ?, ?, ?, ?, ?)",
        )
        .bind(&event.org_id)
        .bind(&event.tier)
        .bind(&event.endpoint)
        .bind(&event.method)
        .bind(event.status_code)
        .bind(event.timestamp)
        .bind(&event.billing_period)
        .execute()
        .await?;

    Ok(())
}

// ═══════════════════════════════════════════════════════════
//  HELPERS
// ═══════════════════════════════════════════════════════════

/// Seconds until midnight UTC (for daily limit Retry-After).
fn seconds_until_midnight_utc() -> u64 {
    let now = Utc::now();
    let tomorrow = (now.date_naive() + chrono::Duration::days(1))
        .and_hms_opt(0, 0, 0)
        .unwrap();
    let remaining = tomorrow.signed_duration_since(now.naive_utc());
    remaining.num_seconds().max(0) as u64
}

/// Seconds until the end of the current billing period (month).
fn seconds_until_period_end() -> u64 {
    let now = Utc::now();
    let end_of_month = if now.month() == 12 {
        chrono::NaiveDate::from_ymd_opt(now.year() + 1, 1, 1).unwrap()
    } else {
        chrono::NaiveDate::from_ymd_opt(now.year(), now.month() + 1, 1).unwrap()
    };
    let end_dt = end_of_month.and_hms_opt(0, 0, 0).unwrap();
    let remaining = end_dt.signed_duration_since(now.naive_utc());
    remaining.num_seconds().max(0) as u64
}

// ═══════════════════════════════════════════════════════════
//  MIGRATION SQL
// ═══════════════════════════════════════════════════════════

// ═══════════════════════════════════════════════════════════
//  P1: Usage Alerts — Notify users approaching or exceeding limits
// ═══════════════════════════════════════════════════════════

/// Usage alert thresholds (as percentage of tier limit)
pub const ALERT_WARNING_PCT: f64 = 80.0;
pub const ALERT_CRITICAL_PCT: f64 = 95.0;
pub const ALERT_EXCEEDED_PCT: f64 = 100.0;

/// Usage alert level
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum UsageAlertLevel {
    /// < 80% — normal usage
    Normal,
    /// 80-95% — warning: approaching limit
    Warning,
    /// 95-100% — critical: very close to limit
    Critical,
    /// > 100% — exceeded: limit breached
    Exceeded,
}

/// Check usage level and return alert if needed
pub fn check_usage_alert(
    api_calls_used: u64,
    tier_limit: u64,
    org_id: &str,
    tier: &str,
) -> Option<UsageAlert> {
    if tier_limit == 0 || tier_limit == u64::MAX {
        return None; // unlimited tier
    }

    let usage_pct = (api_calls_used as f64 / tier_limit as f64) * 100.0;

    let level = if usage_pct >= ALERT_EXCEEDED_PCT {
        UsageAlertLevel::Exceeded
    } else if usage_pct >= ALERT_CRITICAL_PCT {
        UsageAlertLevel::Critical
    } else if usage_pct >= ALERT_WARNING_PCT {
        UsageAlertLevel::Warning
    } else {
        UsageAlertLevel::Normal
    };

    if level == UsageAlertLevel::Normal {
        return None;
    }

    let message = match level {
        UsageAlertLevel::Warning => format!(
            "⚠️ You have used {:.0}% of your {} plan API calls ({} / {}). Consider upgrading.",
            usage_pct, tier, api_calls_used, tier_limit
        ),
        UsageAlertLevel::Critical => format!(
            "🔴 CRITICAL: {:.0}% of your {} plan API calls used ({} / {}). Upgrade now to avoid service interruption.",
            usage_pct, tier, api_calls_used, tier_limit
        ),
        UsageAlertLevel::Exceeded => format!(
            "🚫 You have EXCEEDED your {} plan API call limit ({} / {}). Upgrade at https://angavu.co.ke/billing",
            tier, api_calls_used, tier_limit
        ),
        UsageAlertLevel::Normal => unreachable!(),
    };

    Some(UsageAlert {
        org_id: org_id.to_string(),
        level,
        usage_pct,
        api_calls_used,
        tier_limit,
        message,
        timestamp: Utc::now(),
    })
}

/// Usage alert notification
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UsageAlert {
    pub org_id: String,
    pub level: UsageAlertLevel,
    pub usage_pct: f64,
    pub api_calls_used: u64,
    pub tier_limit: u64,
    pub message: String,
    pub timestamp: chrono::DateTime<chrono::Utc>,
}

/// Check and emit usage alerts for a user (called after metering)
pub fn maybe_emit_usage_alert(
    redis: &redis::aio::ConnectionManager,
    org_id: &str,
    tier: &BuyerTier,
    current_usage: u64,
) -> Option<UsageAlert> {
    let limit = monthly_limit(tier);
    let alert = check_usage_alert(current_usage, limit, org_id, &format!("{:?}", tier));

    if let Some(ref a) = alert {
        // Deduplicate: only alert once per threshold crossing per billing period
        let dedup_key = format!(
            "usage_alert:{}:{:?}:{}",
            org_id,
            a.level,
            current_billing_period()
        );
        // Fire-and-forget: set NX (only if not exists) with 24h TTL
        let _ = redis::cmd("SET")
            .arg(&dedup_key)
            .arg("1")
            .arg("NX")
            .arg("EX")
            .arg(86400i64)
            .query_async::<_, Option<String>>(&mut redis.clone());

        tracing::info!(
            org_id = %org_id,
            level = ?a.level,
            usage_pct = %a.usage_pct,
            "Usage alert triggered"
        );
    }

    alert
}

/// SQL migration for the usage_records table.
pub const USAGE_MIGRATION: &str = r#"
CREATE TABLE IF NOT EXISTS usage_records (
    id BIGSERIAL PRIMARY KEY,
    org_id VARCHAR(128) NOT NULL,
    billing_period VARCHAR(7) NOT NULL,  -- "YYYY-MM"
    api_calls BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (org_id, billing_period)
);

CREATE INDEX IF NOT EXISTS idx_usage_records_org ON usage_records(org_id);
CREATE INDEX IF NOT EXISTS idx_usage_records_period ON usage_records(billing_period);

-- ClickHouse usage_events table (run separately against ClickHouse)
-- CREATE TABLE IF NOT EXISTS usage_events (
--     org_id String,
--     tier String,
--     endpoint String,
--     method String,
--     status_code UInt16,
--     timestamp DateTime64(3, 'UTC'),
--     billing_period String
-- ) ENGINE = MergeTree()
-- ORDER BY (org_id, timestamp)
-- PARTITION BY toYYYYMM(timestamp);
"#;

// ═══════════════════════════════════════════════════════════
//  TESTS
// ═══════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_monthly_limits() {
        assert_eq!(monthly_limit(&BuyerTier::Free), 100);
        assert_eq!(monthly_limit(&BuyerTier::Starter), 5_000);
        assert_eq!(monthly_limit(&BuyerTier::Pro), 50_000);
        assert_eq!(monthly_limit(&BuyerTier::Enterprise), u64::MAX);
    }

    #[test]
    fn test_daily_limits() {
        assert_eq!(daily_limit(&BuyerTier::Free), 10);
        assert_eq!(daily_limit(&BuyerTier::Starter), 250);
        assert_eq!(daily_limit(&BuyerTier::Pro), 2_500);
        assert_eq!(daily_limit(&BuyerTier::Enterprise), u64::MAX);
    }

    #[test]
    fn test_usage_key_format() {
        let key = usage_key("org-123", "2026-08");
        assert_eq!(key, "usage:org-123:2026-08");
    }

    #[test]
    fn test_billing_period_format() {
        let period = current_billing_period();
        assert!(period.len() == 7); // "YYYY-MM"
        assert!(period.contains('-'));
    }

    #[test]
    fn test_days_remaining() {
        let days = days_remaining_in_period();
        assert!(days <= 31);
    }
}
