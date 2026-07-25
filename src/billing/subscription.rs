//! Subscription management for Angavu Intelligence.
//!
//! Manages the four pricing tiers (Free, Starter, Pro, Enterprise),
//! subscription lifecycle (create, upgrade, downgrade, cancel, renew),
//! and per-tier feature gates.

use chrono::{DateTime, Duration, Utc};
use serde::{Deserialize, Serialize};
use sqlx::{FromRow, PgPool};
use uuid::Uuid;

use thiserror::Error;

// ── Errors ─────────────────────────────────────────────────────────────

#[derive(Debug, Error)]
pub enum SubscriptionError {
    #[error("subscription not found: {0}")]
    NotFound(Uuid),
    #[error("subscription already active for org {0}")]
    AlreadyActive(Uuid),
    #[error("invalid tier transition from {from} to {to}")]
    InvalidTransition { from: SubscriptionTier, to: SubscriptionTier },
    #[error("enterprise subscriptions require manual provisioning")]
    EnterpriseRequiresManual,
    #[error("database error: {0}")]
    Database(#[from] sqlx::Error),
}

// ── Tier Definition ────────────────────────────────────────────────────

/// The four billing tiers with their hard limits.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SubscriptionTier {
    Free,
    Starter,
    Pro,
    Enterprise,
}

impl SubscriptionTier {
    /// Monthly price in USD cents.
    pub fn monthly_price_cents(&self) -> Option<u64> {
        match self {
            Self::Free => Some(0),
            Self::Starter => Some(29_900),       // $299.00
            Self::Pro => Some(149_900),           // $1,499.00
            Self::Enterprise => None,             // custom pricing
        }
    }

    /// Maximum queries per billing period. `None` = unlimited.
    pub fn query_limit(&self) -> Option<u64> {
        match self {
            Self::Free => Some(100),
            Self::Starter => Some(5_000),
            Self::Pro => Some(50_000),
            Self::Enterprise => None,
        }
    }

    /// Maximum reports per billing period.
    pub fn report_limit(&self) -> Option<u64> {
        match self {
            Self::Free => Some(2),
            Self::Starter => Some(20),
            Self::Pro => Some(100),
            Self::Enterprise => None,
        }
    }

    /// Maximum data exports per billing period.
    pub fn export_limit(&self) -> Option<u64> {
        match self {
            Self::Free => Some(0),
            Self::Starter => Some(5),
            Self::Pro => Some(50),
            Self::Enterprise => None,
        }
    }

    /// Maximum API keys allowed.
    pub fn max_api_keys(&self) -> u32 {
        match self {
            Self::Free => 1,
            Self::Starter => 3,
            Self::Pro => 10,
            Self::Enterprise => 100,
        }
    }

    /// Rate limit: requests per minute per API key.
    pub fn rate_limit_per_minute(&self) -> u32 {
        match self {
            Self::Free => 10,
            Self::Starter => 60,
            Self::Pro => 300,
            Self::Enterprise => 2_000,
        }
    }

    /// Whether real-time WebSocket streaming is allowed.
    pub fn allows_streaming(&self) -> bool {
        matches!(self, Self::Pro | Self::Enterprise)
    }

    /// Whether custom reports are allowed.
    pub fn allows_custom_reports(&self) -> bool {
        matches!(self, Self::Pro | Self::Enterprise)
    }

    /// Whether the tier supports SLA guarantees.
    pub fn has_sla(&self) -> bool {
        matches!(self, Self::Enterprise)
    }

    /// Allowed intelligence endpoints for this tier.
    pub fn allowed_endpoints(&self) -> Vec<&'static str> {
        match self {
            Self::Free => vec![
                "/api/v1/tools/health",
                "/api/v1/tools/market",
            ],
            Self::Starter => vec![
                "/api/v1/tools/health",
                "/api/v1/tools/market",
                "/api/v1/tools/market/demand",
                "/api/v1/tools/distribution",
                "/api/v1/tools/fmcg",
                "/api/v1/tools/economic",
            ],
            Self::Pro | Self::Enterprise => vec![
                // All endpoints
                "/api/v1/tools/health",
                "/api/v1/tools/credit",
                "/api/v1/tools/market",
                "/api/v1/tools/market/demand",
                "/api/v1/tools/distribution",
                "/api/v1/tools/fmcg",
                "/api/v1/tools/economic",
                "/api/v1/tools/privacy/noise",
                "/api/v1/tools/anonymize",
                "/api/v1/tools/report",
                "/api/v1/tools/alert",
            ],
        }
    }
}

impl std::fmt::Display for SubscriptionTier {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Free => write!(f, "free"),
            Self::Starter => write!(f, "starter"),
            Self::Pro => write!(f, "pro"),
            Self::Enterprise => write!(f, "enterprise"),
        }
    }
}

impl std::str::FromStr for SubscriptionTier {
    type Err = SubscriptionError;
    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s.to_lowercase().as_str() {
            "free" => Ok(Self::Free),
            "starter" => Ok(Self::Starter),
            "pro" => Ok(Self::Pro),
            "enterprise" => Ok(Self::Enterprise),
            _ => Err(SubscriptionError::InvalidTransition {
                from: Self::Free,
                to: Self::Free, // placeholder — we don't know the current tier
            }),
        }
    }
}

// ── Subscription Status ────────────────────────────────────────────────

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SubscriptionStatus {
    Active,
    Trialing,
    PastDue,
    Canceled,
    Paused,
}

// ── Subscription Model ─────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize, FromRow)]
pub struct Subscription {
    pub id: Uuid,
    pub org_id: Uuid,
    pub tier: String,               // stored as text in Postgres
    pub status: String,             // SubscriptionStatus
    pub current_period_start: DateTime<Utc>,
    pub current_period_end: DateTime<Utc>,
    pub cancel_at_period_end: bool,
    pub trial_end: Option<DateTime<Utc>>,
    pub custom_price_cents: Option<u64>,
    pub custom_query_limit: Option<u64>,
    pub metadata: serde_json::Value,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

impl Subscription {
    /// Parse the stored tier string into the enum.
    pub fn tier_enum(&self) -> SubscriptionTier {
        self.tier.parse().unwrap_or(SubscriptionTier::Free)
    }

    /// Parse the stored status string into the enum.
    pub fn status_enum(&self) -> SubscriptionStatus {
        match self.status.as_str() {
            "active" => SubscriptionStatus::Active,
            "trialing" => SubscriptionStatus::Trialing,
            "past_due" => SubscriptionStatus::PastDue,
            "canceled" => SubscriptionStatus::Canceled,
            "paused" => SubscriptionStatus::Paused,
            _ => SubscriptionStatus::Active,
        }
    }

    /// Is this subscription usable right now?
    pub fn is_usable(&self) -> bool {
        matches!(
            self.status_enum(),
            SubscriptionStatus::Active | SubscriptionStatus::Trialing
        ) && self.current_period_end > Utc::now()
    }

    /// Effective query limit (custom override or tier default).
    pub fn effective_query_limit(&self) -> Option<u64> {
        self.custom_query_limit
            .or_else(|| self.tier_enum().query_limit())
    }
}

// ── Subscription Manager ───────────────────────────────────────────────

pub struct SubscriptionManager {
    pool: PgPool,
}

impl SubscriptionManager {
    pub fn new(pool: PgPool) -> Self {
        Self { pool }
    }

    /// Create a new subscription for an organization.
    pub async fn create(
        &self,
        org_id: Uuid,
        tier: SubscriptionTier,
    ) -> Result<Subscription, SubscriptionError> {
        // Check for existing active subscription
        let existing = sqlx::query_as::<_, Subscription>(
            "SELECT * FROM subscriptions WHERE org_id = $1 AND status IN ('active', 'trialing')"
        )
        .bind(org_id)
        .fetch_optional(&self.pool)
        .await?;

        if existing.is_some() {
            return Err(SubscriptionError::AlreadyActive(org_id));
        }

        if matches!(tier, SubscriptionTier::Enterprise) {
            return Err(SubscriptionError::EnterpriseRequiresManual);
        }

        let now = Utc::now();
        let period_end = now + Duration::days(30);

        // Free tier gets a permanent trial; paid tiers get a 14-day trial
        let (status, trial_end) = match tier {
            SubscriptionTier::Free => ("active".to_string(), None),
            _ => ("trialing".to_string(), Some(now + Duration::days(14))),
        };

        let sub = sqlx::query_as::<_, Subscription>(
            r#"
            INSERT INTO subscriptions (id, org_id, tier, status, current_period_start,
                                       current_period_end, cancel_at_period_end, trial_end,
                                       custom_price_cents, custom_query_limit, metadata,
                                       created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, false, $7, NULL, NULL, '{}', $5, $5)
            RETURNING *
            "#,
        )
        .bind(Uuid::new_v4())
        .bind(org_id)
        .bind(tier.to_string())
        .bind(&status)
        .bind(now)
        .bind(period_end)
        .bind(trial_end)
        .fetch_one(&self.pool)
        .await?;

        Ok(sub)
    }

    /// Get the active subscription for an org.
    pub async fn get_for_org(&self, org_id: Uuid) -> Result<Option<Subscription>, SubscriptionError> {
        let sub = sqlx::query_as::<_, Subscription>(
            "SELECT * FROM subscriptions WHERE org_id = $1 AND status IN ('active', 'trialing', 'past_due') ORDER BY created_at DESC LIMIT 1"
        )
        .bind(org_id)
        .fetch_optional(&self.pool)
        .await?;
        Ok(sub)
    }

    /// Get a subscription by ID.
    pub async fn get_by_id(&self, id: Uuid) -> Result<Subscription, SubscriptionError> {
        let sub = sqlx::query_as::<_, Subscription>(
            "SELECT * FROM subscriptions WHERE id = $1"
        )
        .bind(id)
        .fetch_optional(&self.pool)
        .await?
        .ok_or(SubscriptionError::NotFound(id))?;
        Ok(sub)
    }

    /// Upgrade or downgrade a subscription to a new tier.
    pub async fn change_tier(
        &self,
        subscription_id: Uuid,
        new_tier: SubscriptionTier,
    ) -> Result<Subscription, SubscriptionError> {
        let current = self.get_by_id(subscription_id).await?;
        let current_tier = current.tier_enum();

        // Validate transition
        if current_tier == new_tier {
            return Ok(current);
        }

        // Enterprise requires manual provisioning
        if matches!(new_tier, SubscriptionTier::Enterprise) {
            return Err(SubscriptionError::EnterpriseRequiresManual);
        }

        let now = Utc::now();
        let sub = sqlx::query_as::<_, Subscription>(
            r#"
            UPDATE subscriptions
            SET tier = $1, updated_at = $2
            WHERE id = $3
            RETURNING *
            "#,
        )
        .bind(new_tier.to_string())
        .bind(now)
        .bind(subscription_id)
        .fetch_one(&self.pool)
        .await?;

        tracing::info!(
            subscription_id = %subscription_id,
            org_id = %current.org_id,
            from = %current_tier,
            to = %new_tier,
            "Subscription tier changed"
        );

        Ok(sub)
    }

    /// Cancel subscription at the end of the current billing period.
    pub async fn cancel_at_period_end(
        &self,
        subscription_id: Uuid,
    ) -> Result<Subscription, SubscriptionError> {
        let now = Utc::now();
        let sub = sqlx::query_as::<_, Subscription>(
            r#"
            UPDATE subscriptions
            SET cancel_at_period_end = true, updated_at = $1
            WHERE id = $2
            RETURNING *
            "#,
        )
        .bind(now)
        .bind(subscription_id)
        .fetch_one(&self.pool)
        .await?;

        tracing::info!(
            subscription_id = %subscription_id,
            "Subscription marked for cancellation at period end"
        );

        Ok(sub)
    }

    /// Immediately cancel a subscription.
    pub async fn cancel_now(
        &self,
        subscription_id: Uuid,
    ) -> Result<Subscription, SubscriptionError> {
        let now = Utc::now();
        let sub = sqlx::query_as::<_, Subscription>(
            r#"
            UPDATE subscriptions
            SET status = 'canceled', current_period_end = $1, updated_at = $1
            WHERE id = $2
            RETURNING *
            "#,
        )
        .bind(now)
        .bind(subscription_id)
        .fetch_one(&self.pool)
        .await?;

        tracing::info!(
            subscription_id = %subscription_id,
            "Subscription canceled immediately"
        );

        Ok(sub)
    }

    /// Renew a subscription: advance the billing period and reset usage.
    pub async fn renew(
        &self,
        subscription_id: Uuid,
    ) -> Result<Subscription, SubscriptionError> {
        let current = self.get_by_id(subscription_id).await?;

        if current.cancel_at_period_end {
            // Final period — cancel
            return self.cancel_now(subscription_id).await;
        }

        let now = Utc::now();
        let new_period_end = now + Duration::days(30);

        // If trial is over, move to active status
        let new_status = if let Some(trial_end) = current.trial_end {
            if now >= trial_end {
                "active"
            } else {
                &current.status
            }
        } else {
            &current.status
        };

        let sub = sqlx::query_as::<_, Subscription>(
            r#"
            UPDATE subscriptions
            SET status = $1, current_period_start = $2, current_period_end = $3,
                trial_end = CASE WHEN $2 >= trial_end THEN NULL ELSE trial_end END,
                updated_at = $2
            WHERE id = $4
            RETURNING *
            "#,
        )
        .bind(new_status)
        .bind(now)
        .bind(new_period_end)
        .bind(subscription_id)
        .fetch_one(&self.pool)
        .await?;

        tracing::info!(
            subscription_id = %subscription_id,
            new_period_end = %new_period_end,
            "Subscription renewed"
        );

        Ok(sub)
    }

    /// Provision an Enterprise subscription (manual, by admin).
    pub async fn provision_enterprise(
        &self,
        org_id: Uuid,
        price_cents: u64,
        query_limit: Option<u64>,
    ) -> Result<Subscription, SubscriptionError> {
        let now = Utc::now();
        let period_end = now + Duration::days(365); // annual billing for enterprise

        let sub = sqlx::query_as::<_, Subscription>(
            r#"
            INSERT INTO subscriptions (id, org_id, tier, status, current_period_start,
                                       current_period_end, cancel_at_period_end, trial_end,
                                       custom_price_cents, custom_query_limit, metadata,
                                       created_at, updated_at)
            VALUES ($1, $2, 'enterprise', 'active', $3, $4, false, NULL, $5, $6, '{}', $3, $3)
            RETURNING *
            "#,
        )
        .bind(Uuid::new_v4())
        .bind(org_id)
        .bind(now)
        .bind(period_end)
        .bind(price_cents as i64)
        .bind(query_limit.map(|v| v as i64))
        .fetch_one(&self.pool)
        .await?;

        tracing::info!(
            org_id = %org_id,
            price_cents = price_cents,
            "Enterprise subscription provisioned"
        );

        Ok(sub)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn tier_limits_are_consistent() {
        assert_eq!(SubscriptionTier::Free.query_limit(), Some(100));
        assert_eq!(SubscriptionTier::Starter.query_limit(), Some(5_000));
        assert_eq!(SubscriptionTier::Pro.query_limit(), Some(50_000));
        assert_eq!(SubscriptionTier::Enterprise.query_limit(), None);
    }

    #[test]
    fn tier_pricing() {
        assert_eq!(SubscriptionTier::Free.monthly_price_cents(), Some(0));
        assert_eq!(SubscriptionTier::Starter.monthly_price_cents(), Some(29_900));
        assert_eq!(SubscriptionTier::Pro.monthly_price_cents(), Some(149_900));
        assert_eq!(SubscriptionTier::Enterprise.monthly_price_cents(), None);
    }

    #[test]
    fn tier_features() {
        assert!(!SubscriptionTier::Free.allows_streaming());
        assert!(!SubscriptionTier::Starter.allows_streaming());
        assert!(SubscriptionTier::Pro.allows_streaming());
        assert!(SubscriptionTier::Enterprise.allows_streaming());
    }

    #[test]
    fn tier_display_roundtrip() {
        for tier in [SubscriptionTier::Free, SubscriptionTier::Starter, SubscriptionTier::Pro, SubscriptionTier::Enterprise] {
            let s = tier.to_string();
            let parsed: SubscriptionTier = s.parse().unwrap();
            assert_eq!(tier, parsed);
        }
    }
}
