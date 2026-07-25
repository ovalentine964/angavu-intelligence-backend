//! Usage metering for Angavu Intelligence billing.
//!
//! Tracks per-org consumption of billable resources (queries, reports,
//! data exports) within each billing period. Used to enforce tier limits
//! and to generate invoices with overage charges.

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use sqlx::{FromRow, PgPool};
use uuid::Uuid;

use thiserror::Error;

use super::subscription::{Subscription, SubscriptionTier};

// ── Errors ─────────────────────────────────────────────────────────────

#[derive(Debug, Error)]
pub enum UsageError {
    #[error("usage limit exceeded for {metric}: used {used} / limit {limit}")]
    LimitExceeded {
        metric: String,
        used: u64,
        limit: u64,
    },
    #[error("no active subscription for org {0}")]
    NoSubscription(Uuid),
    #[error("database error: {0}")]
    Database(#[from] sqlx::Error),
    #[error("redis error: {0}")]
    Redis(#[from] redis::RedisError),
}

// ── Usage Metrics ──────────────────────────────────────────────────────

/// The types of usage we track and bill for.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum UsageMetric {
    /// Intelligence queries (market, credit, economic, etc.)
    Query,
    /// Generated reports
    Report,
    /// Raw data exports (CSV, JSON, Parquet)
    DataExport,
    /// WebSocket streaming minutes
    StreamingMinute,
    /// Credit scoring API calls
    CreditScore,
}

impl UsageMetric {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Query => "query",
            Self::Report => "report",
            Self::DataExport => "data_export",
            Self::StreamingMinute => "streaming_minute",
            Self::CreditScore => "credit_score",
        }
    }
}

impl std::fmt::Display for UsageMetric {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.as_str())
    }
}

// ── Usage Record ───────────────────────────────────────────────────────

/// A single usage event recorded against an org's subscription.
#[derive(Debug, Clone, Serialize, Deserialize, FromRow)]
pub struct UsageRecord {
    pub id: Uuid,
    pub org_id: Uuid,
    pub subscription_id: Uuid,
    pub api_key_id: Option<Uuid>,
    pub metric: String,
    pub quantity: i64,
    pub unit_cost_cents: i64,
    pub total_cost_cents: i64,
    pub endpoint: Option<String>,
    pub metadata: serde_json::Value,
    pub recorded_at: DateTime<Utc>,
    pub billing_period_start: DateTime<Utc>,
    pub billing_period_end: DateTime<Utc>,
}

/// Aggregated usage for a billing period.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UsageSummary {
    pub org_id: Uuid,
    pub period_start: DateTime<Utc>,
    pub period_end: DateTime<Utc>,
    pub queries_used: u64,
    pub queries_limit: Option<u64>,
    pub reports_used: u64,
    pub reports_limit: Option<u64>,
    pub exports_used: u64,
    pub exports_limit: Option<u64>,
    pub streaming_minutes_used: u64,
    pub credit_scores_used: u64,
    pub total_cost_cents: u64,
}

// ── Unit Pricing (per-use overage) ────────────────────────────────────

/// Cents per unit for overage billing.
pub struct UnitPricing;

impl UnitPricing {
    pub fn cents_per(metric: &UsageMetric, tier: &SubscriptionTier) -> i64 {
        match (metric, tier) {
            // Queries: $0.01–$0.05 per query over limit
            (UsageMetric::Query, SubscriptionTier::Free) => 5,       // $0.05
            (UsageMetric::Query, SubscriptionTier::Starter) => 2,    // $0.02
            (UsageMetric::Query, SubscriptionTier::Pro) => 1,        // $0.01
            (UsageMetric::Query, SubscriptionTier::Enterprise) => 0, // included

            // Reports: $1–$10 per report over limit
            (UsageMetric::Report, SubscriptionTier::Free) => 500,       // $5.00
            (UsageMetric::Report, SubscriptionTier::Starter) => 200,    // $2.00
            (UsageMetric::Report, SubscriptionTier::Pro) => 100,        // $1.00
            (UsageMetric::Report, SubscriptionTier::Enterprise) => 0,

            // Data exports: $0.50–$5.00 per export
            (UsageMetric::DataExport, SubscriptionTier::Starter) => 500, // $5.00
            (UsageMetric::DataExport, SubscriptionTier::Pro) => 100,     // $1.00
            (UsageMetric::DataExport, SubscriptionTier::Enterprise) => 0,
            (UsageMetric::DataExport, SubscriptionTier::Free) => 1000,   // $10.00 (shouldn't happen)

            // Streaming: $0.10 per minute
            (UsageMetric::StreamingMinute, _) => 10,

            // Credit scores: $0.05–$0.50 per score
            (UsageMetric::CreditScore, SubscriptionTier::Pro) => 5,        // $0.05
            (UsageMetric::CreditScore, SubscriptionTier::Enterprise) => 3, // $0.03
            (UsageMetric::CreditScore, _) => 10,                           // $0.10

            _ => 0,
        }
    }
}

// ── Usage Meter ────────────────────────────────────────────────────────

pub struct UsageMeter {
    pool: PgPool,
    redis: redis::aio::ConnectionManager,
}

impl UsageMeter {
    pub fn new(pool: PgPool, redis: redis::aio::ConnectionManager) -> Self {
        Self { pool, redis }
    }

    /// Record a single usage event. Returns the created record.
    pub async fn record(
        &self,
        org_id: Uuid,
        subscription: &Subscription,
        api_key_id: Option<Uuid>,
        metric: UsageMetric,
        quantity: u64,
        endpoint: Option<&str>,
    ) -> Result<UsageRecord, UsageError> {
        let tier = subscription.tier_enum();
        let unit_cost = UnitPricing::cents_per(&metric, &tier);
        let total_cost = unit_cost * quantity as i64;

        let now = Utc::now();

        let record = sqlx::query_as::<_, UsageRecord>(
            r#"
            INSERT INTO usage_records (id, org_id, subscription_id, api_key_id, metric,
                                       quantity, unit_cost_cents, total_cost_cents, endpoint,
                                       metadata, recorded_at, billing_period_start, billing_period_end)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, '{}', $10, $11, $12)
            RETURNING *
            "#,
        )
        .bind(Uuid::new_v4())
        .bind(org_id)
        .bind(subscription.id)
        .bind(api_key_id)
        .bind(metric.as_str())
        .bind(quantity as i64)
        .bind(unit_cost)
        .bind(total_cost)
        .bind(endpoint)
        .bind(now)
        .bind(subscription.current_period_start)
        .bind(subscription.current_period_end)
        .fetch_one(&self.pool)
        .await?;

        // Also increment Redis counters for fast lookups
        self.increment_counter(org_id, &metric, quantity).await?;

        Ok(record)
    }

    /// Check whether a usage event would exceed the subscription's limits.
    /// Returns `Ok(())` if allowed, `Err(LimitExceeded)` if it would go over.
    pub async fn check_limit(
        &self,
        org_id: Uuid,
        subscription: &Subscription,
        metric: UsageMetric,
        additional_quantity: u64,
    ) -> Result<(), UsageError> {
        let tier = subscription.tier_enum();

        // Get current usage
        let current = self.get_current_usage(org_id, subscription, metric).await?;

        let limit: Option<u64> = match metric {
            UsageMetric::Query => tier.query_limit().or(subscription.effective_query_limit()),
            UsageMetric::Report => tier.report_limit(),
            UsageMetric::DataExport => tier.export_limit(),
            UsageMetric::StreamingMinute => None, // no hard limit, just bill per minute
            UsageMetric::CreditScore => tier.query_limit(), // share query pool
        };

        if let Some(limit) = limit {
            if current + additional_quantity > limit {
                return Err(UsageError::LimitExceeded {
                    metric: metric.to_string(),
                    used: current,
                    limit,
                });
            }
        }

        Ok(())
    }

    /// Get current usage for a metric in the active billing period.
    /// Uses Redis for speed, falls back to Postgres.
    pub async fn get_current_usage(
        &self,
        org_id: Uuid,
        subscription: &Subscription,
        metric: UsageMetric,
    ) -> Result<u64, UsageError> {
        // Try Redis first
        let redis_key = format!(
            "usage:{}:{}:{}",
            org_id,
            metric.as_str(),
            subscription.current_period_start.timestamp()
        );

        let mut conn = self.redis.clone();
        let cached: Option<u64> = redis::cmd("GET")
            .arg(&redis_key)
            .query_async(&mut conn)
            .await
            .unwrap_or(None);

        if let Some(count) = cached {
            return Ok(count);
        }

        // Fallback to Postgres
        let row: (Option<i64>,) = sqlx::query_as(
            r#"
            SELECT COALESCE(SUM(quantity), 0)
            FROM usage_records
            WHERE org_id = $1
              AND metric = $2
              AND billing_period_start = $3
            "#,
        )
        .bind(org_id)
        .bind(metric.as_str())
        .bind(subscription.current_period_start)
        .fetch_one(&self.pool)
        .await?;

        let count = row.0.unwrap_or(0) as u64;

        // Cache in Redis
        let _: () = redis::cmd("SETEX")
            .arg(&redis_key)
            .arg(3600) // 1 hour TTL
            .arg(count)
            .query_async(&mut conn)
            .await
            .unwrap_or(());

        Ok(count)
    }

    /// Get a full usage summary for an org's current billing period.
    pub async fn get_summary(
        &self,
        org_id: Uuid,
        subscription: &Subscription,
    ) -> Result<UsageSummary, UsageError> {
        let tier = subscription.tier_enum();

        let queries = self.get_current_usage(org_id, subscription, UsageMetric::Query).await?;
        let reports = self.get_current_usage(org_id, subscription, UsageMetric::Report).await?;
        let exports = self.get_current_usage(org_id, subscription, UsageMetric::DataExport).await?;
        let streaming = self.get_current_usage(org_id, subscription, UsageMetric::StreamingMinute).await?;
        let credit_scores = self.get_current_usage(org_id, subscription, UsageMetric::CreditScore).await?;

        // Total cost from DB
        let cost_row: (Option<i64>,) = sqlx::query_as(
            r#"
            SELECT COALESCE(SUM(total_cost_cents), 0)
            FROM usage_records
            WHERE org_id = $1
              AND billing_period_start = $2
            "#,
        )
        .bind(org_id)
        .bind(subscription.current_period_start)
        .fetch_one(&self.pool)
        .await?;

        Ok(UsageSummary {
            org_id,
            period_start: subscription.current_period_start,
            period_end: subscription.current_period_end,
            queries_used: queries,
            queries_limit: tier.query_limit().or(subscription.effective_query_limit()),
            reports_used: reports,
            reports_limit: tier.report_limit(),
            exports_used: exports,
            exports_limit: tier.export_limit(),
            streaming_minutes_used: streaming,
            credit_scores_used: credit_scores,
            total_cost_cents: cost_row.0.unwrap_or(0) as u64,
        })
    }

    /// Increment the Redis counter for fast rate checks.
    async fn increment_counter(
        &self,
        org_id: Uuid,
        metric: &UsageMetric,
        quantity: u64,
    ) -> Result<(), UsageError> {
        let redis_key = format!("usage:{}:{}", org_id, metric.as_str());
        let mut conn = self.redis.clone();
        let _: () = redis::cmd("INCRBY")
            .arg(&redis_key)
            .arg(quantity)
            .query_async(&mut conn)
            .await
            .unwrap_or(());
        Ok(())
    }

    /// Get usage records for a billing period (for invoice generation).
    pub async fn get_records_for_period(
        &self,
        org_id: Uuid,
        period_start: DateTime<Utc>,
        period_end: DateTime<Utc>,
    ) -> Result<Vec<UsageRecord>, UsageError> {
        let records = sqlx::query_as::<_, UsageRecord>(
            r#"
            SELECT * FROM usage_records
            WHERE org_id = $1
              AND billing_period_start = $2
              AND billing_period_end = $3
            ORDER BY recorded_at
            "#,
        )
        .bind(org_id)
        .bind(period_start)
        .bind(period_end)
        .fetch_all(&self.pool)
        .await?;
        Ok(records)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn unit_pricing_free_tier() {
        assert_eq!(UnitPricing::cents_per(&UsageMetric::Query, &SubscriptionTier::Free), 5);
        assert_eq!(UnitPricing::cents_per(&UsageMetric::Report, &SubscriptionTier::Free), 500);
    }

    #[test]
    fn unit_pricing_enterprise() {
        assert_eq!(UnitPricing::cents_per(&UsageMetric::Query, &SubscriptionTier::Enterprise), 0);
        assert_eq!(UnitPricing::cents_per(&UsageMetric::Report, &SubscriptionTier::Enterprise), 0);
    }

    #[test]
    fn metric_display() {
        assert_eq!(UsageMetric::Query.as_str(), "query");
        assert_eq!(UsageMetric::DataExport.as_str(), "data_export");
        assert_eq!(UsageMetric::StreamingMinute.as_str(), "streaming_minute");
    }
}
